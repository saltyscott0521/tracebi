"""
The credentials a project's connections need, and a store people can manage.

A connection keeps its secret out of the file as ``${NAME}``
(``connections/<name>.yaml``, and ``key_id`` / ``secret`` in ``tracebi.yaml``).
This module is the one place such a reference is parsed and resolved:

* :data:`REF` is the syntax: ``${NAME}``, or ``${NAME:-default}`` where the
  default is a literal used when the name resolves nowhere. A default is
  checked like any literal of its field (``validate_connection_doc``), so a
  secret cannot hide in one.
* :func:`resolve` looks a name up in the process environment, then the
  project's ``.env``, then the store. The environment stays first so a
  deployment's own configuration always wins over anything saved through
  the app, and a project with no store behaves exactly as before.
* :func:`required` lists every name the project's files reference, and
  :func:`status` says where each one is set, never what it is.

The store is ``.tracebi/secrets.json``: ``{NAME: {"value": <Fernet token>,
"updated_at", "updated_by"}}``, mode 0600. The key is ``TRACEBI_SECRET_KEY``
(several workers must share it) or ``.tracebi/secret.key``, generated 0600 on
the first write. A store read under another key fails naming the file
(:class:`CredentialKeyMismatch`), never as "not set". Nothing is copied into
``os.environ``.

This is the project's credentials; :mod:`tracebi.credentials` is a person's
sign-in to a server, kept on their own machine.

Reference: ``docs/reference/credentials.md``.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

#: ``${NAME}`` or ``${NAME:-default}``, as the whole value. Group 1 is the
#: name; group 2 the default, None when there is none.
REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")
NAME = re.compile(r"[A-Z_][A-Z0-9_]*")

STORE_FILE = os.path.join(".tracebi", "secrets.json")
KEY_FILE = os.path.join(".tracebi", "secret.key")

_lock = threading.Lock()


class CredentialError(Exception):
    """Something about a credential the person can act on; the message says what."""


class Missing(CredentialError, LookupError):
    """*name* is set nowhere: not in the environment, ``.env`` or the store."""

    def __init__(self, name: str) -> None:
        super().__init__(f"{name} is not set")
        self.name = name


class CredentialKeyMismatch(CredentialError):
    """The store was written under a key other than the one this process has."""


def parse(raw: str) -> Optional[tuple[str, Optional[str]]]:
    """``(name, default)`` when *raw* is a whole-value reference, else None."""
    ref = REF.fullmatch(raw) if isinstance(raw, str) else None
    return (ref.group(1), ref.group(2)) if ref else None


# ── The store ─────────────────────────────────────────────────────────────

def store_path(root) -> Path:
    return Path(root) / STORE_FILE


def _fernet_class():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:
        raise ImportError(
            "The credential store (.tracebi/secrets.json) needs the cryptography "
            "package: pip install 'tracebi[web]'") from exc
    return Fernet, InvalidToken


def key_source(root) -> str:
    """``env`` when ``TRACEBI_SECRET_KEY`` is set, else ``file``."""
    return "env" if os.environ.get("TRACEBI_SECRET_KEY", "").strip() else "file"


def _key(root, create: bool) -> Optional[bytes]:
    env = os.environ.get("TRACEBI_SECRET_KEY", "").strip()
    if env:
        return env.encode()
    path = Path(root) / KEY_FILE
    try:
        return path.read_bytes().strip()
    except FileNotFoundError:
        if not create:
            return None
    Fernet, _ = _fernet_class()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    try:
        # O_EXCL: two processes generating at once must not each keep a key
        # the other's values cannot be read with. The loser reads the winner's.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes().strip()
    with os.fdopen(fd, "wb") as fh:
        fh.write(key + b"\n")
    return key


def _fernet(root, create: bool = False):
    Fernet, _ = _fernet_class()
    key = _key(root, create)
    if key is None:
        raise CredentialKeyMismatch(
            f"{store_path(root)} holds credentials but there is no key to read them: "
            f"neither TRACEBI_SECRET_KEY nor {Path(root) / KEY_FILE}. Restore the key "
            f"the store was written with, or unset and set each credential again.")
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        where = "TRACEBI_SECRET_KEY" if key_source(root) == "env" else str(Path(root) / KEY_FILE)
        raise CredentialError(
            f"{where} is not a Fernet key (32 url-safe base64-encoded bytes); "
            f"make one with: python -c \"from cryptography.fernet import Fernet; "
            f"print(Fernet.generate_key().decode())\"") from exc


def _read_store(root) -> dict:
    path = store_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise CredentialError(f"{path} cannot be read ({exc}); fix or delete it") from exc
    if not isinstance(data, dict):
        raise CredentialError(f"{path} is not a TraceBi credential store; fix or delete it")
    return data


def _write_store(root, data: dict) -> None:
    path = store_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates the file 0600, so there is no moment it is readable.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".secrets-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def stored(name: str, root) -> Optional[str]:
    """The store's value for *name*, decrypted, or None when it holds none."""
    entry = _read_store(root).get(name)
    if not isinstance(entry, dict) or not entry.get("value"):
        return None
    _, InvalidToken = _fernet_class()
    try:
        return _fernet(root).decrypt(entry["value"].encode()).decode("utf-8")
    except InvalidToken:
        where = "TRACEBI_SECRET_KEY" if key_source(root) == "env" else str(Path(root) / KEY_FILE)
        raise CredentialKeyMismatch(
            f"{store_path(root)} was written under a different key than {where}: "
            f"{name} cannot be read. Restore the key the store was written with, "
            f"or set {name} again.") from None


def set_secret(name: str, value: str, root, actor: Optional[str] = None) -> bool:
    """Save *value* for *name* in the store. True when the name was new."""
    if not NAME.fullmatch(name or ""):
        raise CredentialError(f"{name!r} is not a credential name ([A-Z_][A-Z0-9_]*)")
    if not isinstance(value, str) or not value:
        raise CredentialError(f"{name}: the value is empty")
    with _lock:
        data = _read_store(root)
        fernet = _fernet(root, create=True)
        new = name not in data
        data[name] = {"value": fernet.encrypt(value.encode("utf-8")).decode("ascii"),
                      "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "updated_by": actor}
        _write_store(root, data)
    return new


def unset_secret(name: str, root) -> bool:
    """Remove *name* from the store. True when it was there. An environment
    or ``.env`` value is not touched."""
    with _lock:
        data = _read_store(root)
        if name not in data:
            return False
        del data[name]
        _write_store(root, data)
    return True


# ── Resolution ────────────────────────────────────────────────────────────

def resolve(name: str, root) -> tuple[str, str]:
    """``(value, source)`` for *name*, *source* one of ``environment``,
    ``dotenv``, ``store``. Raises :class:`Missing` when it is set nowhere,
    :class:`CredentialKeyMismatch` when the store holds it under another key.
    An empty value counts as unset, as it always has."""
    from tracebi.connections import _read_dotenv

    value = os.environ.get(name)
    if value:
        return value, "environment"
    value = _read_dotenv(Path(root) / ".env").get(name)
    if value:
        return value, "dotenv"
    value = stored(name, root)
    if value:
        return value, "store"
    raise Missing(name)


def expand(raw: str, root) -> tuple[str, Optional[str]]:
    """A field's value: a literal as written (source None), a reference
    resolved (:func:`resolve`), or its default when the name is set nowhere
    (source ``default``)."""
    ref = parse(raw)
    if ref is None:
        return raw, None
    name, default = ref
    try:
        return resolve(name, root)
    except Missing:
        if default:
            return default, "default"
        raise


# ── Which names a project needs ───────────────────────────────────────────

def required(root) -> list[dict]:
    """Every ``${NAME}`` the project's files reference: ``[{name, used_by:
    [{kind: connection|warehouse, name, field, default: bool}]}]``, by name.
    A file that will not parse contributes what it can; ``tracebi validate``
    is where it is reported."""
    from tracebi.connections import SUFFIXES, connections_dir, read_connection_doc

    uses: dict[str, list[dict]] = {}

    def add(value, kind: str, owner: str, field: str) -> None:
        ref = parse(value)
        if ref:
            uses.setdefault(ref[0], []).append(
                {"kind": kind, "name": owner, "field": field, "default": bool(ref[1])})

    cdir = connections_dir(root)
    files = sorted(p for p in cdir.iterdir()
                   if p.suffix in SUFFIXES and not p.name.startswith("_")) \
        if cdir.is_dir() else []
    for path in files:
        try:
            doc = read_connection_doc(path)
        except Exception:  # noqa: BLE001 — a broken file names nothing
            continue
        if not isinstance(doc, dict):
            continue
        for field, value in doc.items():
            if field not in ("name", "type"):
                add(value, "connection", path.stem, field)
    try:
        from tracebi.project_config import read_config
        block = read_config(str(root)).get("warehouse")
    except Exception:  # noqa: BLE001 — a malformed tracebi.yaml is reported where it is read
        block = None
    if isinstance(block, dict):
        for field, value in block.items():
            add(value, "warehouse", "warehouse", field)
    return [{"name": n, "used_by": uses[n]} for n in sorted(uses)]


def status(root) -> list[dict]:
    """:func:`required` joined with where each name resolves, never with its
    value: ``{name, used_by, set, source, stored, updated_at?, updated_by?,
    problem?}``. *source* is ``environment``, ``dotenv``, ``store``,
    ``default`` or None. A name only the store holds is listed too (with no
    ``used_by``), so it can be removed."""
    rows = required(root)
    try:
        store = _read_store(root)
    except CredentialError as exc:
        store, broken = {}, str(exc)
    else:
        broken = None
    listed = {r["name"] for r in rows}
    rows += [{"name": n, "used_by": []} for n in sorted(store) if n not in listed]
    out = []
    for row in rows:
        name = row["name"]
        entry = store.get(name) if isinstance(store.get(name), dict) else None
        item = {**row, "set": False, "source": None, "stored": entry is not None}
        try:
            _, item["source"] = resolve(name, root)
            item["set"] = True
        except Missing:
            if any(u["default"] for u in row["used_by"]):
                item["set"], item["source"] = True, "default"
        except CredentialError as exc:
            item["source"], item["problem"] = "store", str(exc)
        if broken:
            item["problem"] = broken
        if entry is not None:
            item["updated_at"] = entry.get("updated_at")
            item["updated_by"] = entry.get("updated_by")
        out.append(item)
    return out


def redact(text: str, root) -> str:
    """*text* with every value a referenced name resolves to replaced by
    ``***``: a driver's error can echo what it was given."""
    for row in required(root):
        with contextlib.suppress(CredentialError):
            value, _ = resolve(row["name"], root)
            if len(value) >= 4:
                text = text.replace(value, "***")
    return text


def record_change(name: str, status: str) -> None:
    """One ``tracebi_runs`` row (``kind: credential``, ``target: NAME``,
    ``status: set | unset``), attributed to the actor in the audit context.
    Never the value."""
    from tracebi.state import install_extra, record_run

    now = datetime.now(timezone.utc).isoformat()
    with install_extra("web"):
        record_run(kind="credential", target=name, status=status, started=now, finished=now)
