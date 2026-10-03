"""``tracebi connect`` — point a project at a warehouse the builder already has.

Writes the secret to the project's ``.env`` and a connector module under
``models/_connections/``. Discovery loads only top-level ``models/*.py``
files that define ``model`` (``model_registry.auto_discover`` is
non-recursive and skips names starting with ``_``), so a connection module
beside the models would be reported as a model that failed to load.

The generated module calls ``load_dotenv()`` itself and reads
``os.environ[...]``. This module never loads ``.env``.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KINDS = ("postgres", "snowflake", "bigquery", "duckdb")

# Fields the connector constructor requires. ``--dataset`` is required because
# BigQueryConnector takes ``dataset`` with no default. ``--role`` and
# ``--credentials`` are optional and are not prompted.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "postgres": ("url",),
    "snowflake": ("account", "user", "password", "warehouse", "database", "schema"),
    "bigquery": ("project", "dataset"),
    "duckdb": ("database",),
}
_OPTIONAL: dict[str, tuple[str, ...]] = {
    "snowflake": ("role",),
    "bigquery": ("credentials",),
}
# Echoing these would put the secret on the screen.
_SECRET = {"url", "password"}


def connection_path(models_dir: Path, name: str) -> Path:
    """Where ``tracebi connect <name>`` writes the connector module."""
    return models_dir / "_connections" / f"{name}.py"


def env_var(name: str, field: str) -> str:
    return f"TRACEBI_{name.upper()}_{field.upper()}"


def connect_command(args) -> int:
    """Test the warehouse (unless ``--no-test``), then write ``.env`` and the module.

    Files are written only after a successful test. An existing ``.env`` key
    or connection file is left untouched unless ``--force``.
    """
    name = args.name
    if not _NAME.fullmatch(name):
        print(
            f"connection name {name!r} must be a Python identifier "
            "(letters, digits, underscore)",
            file=sys.stderr,
        )
        return 2

    kind = (args.kind or "").strip().lower()
    tty = sys.stdin.isatty()
    if not kind:
        if not tty:
            print("missing required flags: --kind", file=sys.stderr)
            return 2
        kind = input("kind (postgres, snowflake, bigquery, duckdb): ").strip().lower()
    if kind not in _KINDS:
        print(
            f"unknown kind {kind!r}; expected one of: {', '.join(_KINDS)}",
            file=sys.stderr,
        )
        return 2

    values = {field: getattr(args, field, None) for field in _REQUIRED[kind] + _OPTIONAL.get(kind, ())}
    values = {k: (v.strip() if isinstance(v, str) else v) for k, v in values.items()}
    missing = [field for field in _REQUIRED[kind] if not values.get(field)]
    if missing:
        if not tty:
            print(
                "missing required flags: " + ", ".join(f"--{field}" for field in missing),
                file=sys.stderr,
            )
            return 2
        for field in missing:
            entered = _prompt(field)
            if not entered:
                print(f"missing required flags: --{field}", file=sys.stderr)
                return 2
            values[field] = entered

    models_dir: Path = args.models_dir
    conn_path = connection_path(models_dir, name)
    updates = {
        env_var(name, field): values[field]
        for field in list(_REQUIRED[kind]) + list(_OPTIONAL.get(kind, ()))
        if values.get(field)
    }
    env_path = Path.cwd() / ".env"
    conflicts = _env_conflicts(env_path, list(updates))
    problems: list[str] = []
    if conflicts and not args.force:
        problems.append(
            "refusing to overwrite .env keys without --force: " + ", ".join(conflicts)
        )
    if conn_path.exists() and not args.force:
        problems.append(
            f"refusing to overwrite existing {conn_path}; pass --force to replace"
        )
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    if args.test:
        try:
            summary = _probe(_build_connector(name, kind, values))
        except Exception as exc:  # noqa: BLE001 — the driver's first line is the result
            print(_one_line_error(exc), file=sys.stderr)
            return 1
        print(f"{name}: {summary}")

    conn_path.parent.mkdir(parents=True, exist_ok=True)
    env_rel = os.path.relpath(env_path, start=conn_path.parent)
    conn_path.write_text(_connection_source(name, kind, env_rel), encoding="utf-8")
    _apply_env(env_path, updates)
    added = _ensure_dotenv_ignored(Path.cwd() / ".gitignore")
    print(f"wrote {conn_path}")
    print("wrote .env (" + ", ".join(updates) + ")")
    if added:
        print("added .env to .gitignore")
    return 0


def _prompt(field: str) -> str:
    import getpass

    label = f"--{field}: "
    if field in _SECRET:
        return getpass.getpass(label).strip()
    return input(label).strip()


def _one_line_error(exc: BaseException) -> str:
    message = str(exc).splitlines()[0] if str(exc) else ""
    line = f"{type(exc).__name__}: {message}"
    return line.rstrip(": ") if not message else line


def _build_connector(name: str, kind: str, values: dict):
    """Construct the connector from the flags just collected. Does not read ``.env``."""
    if kind == "postgres":
        from tracebi.connectors.sql_connector import SQLConnector
        return SQLConnector(name, url=values["url"])
    if kind == "duckdb":
        from tracebi.connectors.duckdb_connector import DuckDBConnector
        return DuckDBConnector(name, database=values["database"])
    if kind == "snowflake":
        from tracebi.connectors.snowflake_connector import SnowflakeConnector
        kwargs = {
            "account": values["account"],
            "user": values["user"],
            "password": values["password"],
            "warehouse": values["warehouse"],
            "database": values["database"],
            "schema": values["schema"],
        }
        if values.get("role"):
            kwargs["role"] = values["role"]
        return SnowflakeConnector(name, **kwargs)
    from tracebi.connectors.bigquery_connector import BigQueryConnector
    return BigQueryConnector(
        name,
        project=values["project"],
        dataset=values["dataset"],
        credentials=_bq_credentials(values.get("credentials")),
    )


def _bq_credentials(path: str | None):
    if not path:
        return None
    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise ImportError(
            "google-cloud-bigquery is required to load a service-account file.\n"
            "Install with: pip install 'tracebi[bigquery]'"
        ) from exc
    return service_account.Credentials.from_service_account_file(path)


def _probe(connector) -> str:
    """Cheapest metadata call: connect, then ``list_tables`` (what ``warehouse tables`` uses)."""
    try:
        connector.connect()
        tables = connector.list_tables()
    finally:
        _release(connector)
    if tables is None:
        return "connected; this connector cannot list tables"
    n = len(tables)
    return f"{n} table" if n == 1 else f"{n} tables"


def _release(connector) -> None:
    disc = getattr(connector, "disconnect", None)
    if not callable(disc):
        return
    try:
        disc()
    except Exception:  # noqa: BLE001 — releasing a probe must not hide the probe's own error
        pass


def _line_key(line: str) -> str | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    if raw.startswith("export "):
        raw = raw[len("export "):].strip()
    key, sep, _value = raw.partition("=")
    if not sep:
        return None
    return key.strip() or None


def _env_conflicts(path: Path, keys: list[str]) -> list[str]:
    if not path.is_file():
        return []
    present = {key for line in path.read_text(encoding="utf-8").splitlines() if (key := _line_key(line))}
    return [key for key in keys if key in present]


def _quote_env(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _apply_env(path: Path, updates: dict[str, str]) -> None:
    """Insert or replace keys. Every other line stays as it was."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    index = {}
    for i, line in enumerate(lines):
        key = _line_key(line)
        if key:
            index[key] = i
    for key, value in updates.items():
        rendered = f"{key}={_quote_env(value)}"
        if key in index:
            lines[index[key]] = rendered
        else:
            lines.append(rendered)
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _ensure_dotenv_ignored(path: Path) -> bool:
    """Append ``.env`` when the project's gitignore does not already name it.

    ``tracebi init`` writes the line. A project that skipped init still
    should not commit the file this command just filled with a secret.
    Returns whether a line was added.
    """
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if any(line.strip() == ".env" for line in text.splitlines()):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + ".env\n", encoding="utf-8")
    return True


def _connection_source(name: str, kind: str, env_rel: str) -> str:
    """Python source for the connector module. Secrets appear only as env keys."""
    load = (
        "try:\n"
        "    from dotenv import load_dotenv\n"
        "except ImportError as exc:\n"
        "    raise ImportError(\n"
        '        "python-dotenv is required to load this connection.\\n"\n'
        "        \"Install with: pip install 'tracebi[analyst]'\"\n"
        "    ) from exc\n"
        "\n"
        "load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)),\n"
        f"                        {env_rel!r}))\n"
    )
    body = {
        "postgres": _postgres_body,
        "snowflake": _snowflake_body,
        "bigquery": _bigquery_body,
        "duckdb": _duckdb_body,
    }[kind](name)
    return (
        f'"""Connection {name!r} ({kind}). Written by ``tracebi connect``.\n'
        "\n"
        "The framework does not load ``.env``. This file does, then builds the\n"
        "connector from ``os.environ``.\n"
        '"""\n'
        "\n"
        "import os\n"
        "\n"
        f"{load}\n"
        f"{body}"
    )


def _postgres_body(name: str) -> str:
    key = env_var(name, "url")
    return (
        "from tracebi.connectors.sql_connector import SQLConnector\n"
        "\n"
        f"connector = SQLConnector({name!r}, url=os.environ[{key!r}])\n"
    )


def _duckdb_body(name: str) -> str:
    key = env_var(name, "database")
    return (
        "from tracebi.connectors.duckdb_connector import DuckDBConnector\n"
        "\n"
        "connector = DuckDBConnector(\n"
        f"    {name!r}, database=os.environ[{key!r}])\n"
    )


def _snowflake_body(name: str) -> str:
    fields = ("account", "user", "password", "warehouse", "database", "schema")
    lines = ["    " + f"{field}=os.environ[{env_var(name, field)!r}]," for field in fields]
    role = env_var(name, "role")
    return (
        "from tracebi.connectors.snowflake_connector import SnowflakeConnector\n"
        "\n"
        "_kwargs = dict(\n"
        + "\n".join(lines) + "\n"
        ")\n"
        f"_role = os.environ.get({role!r})\n"
        "if _role:\n"
        '    _kwargs["role"] = _role\n'
        f"connector = SnowflakeConnector({name!r}, **_kwargs)\n"
    )


def _bigquery_body(name: str) -> str:
    creds = env_var(name, "credentials")
    project = env_var(name, "project")
    dataset = env_var(name, "dataset")
    return (
        "def _credentials():\n"
        f"    path = os.environ.get({creds!r}, \"\").strip()\n"
        "    if not path:\n"
        "        return None\n"
        "    try:\n"
        "        from google.oauth2 import service_account\n"
        "    except ImportError as exc:\n"
        "        raise ImportError(\n"
        '            "google-cloud-bigquery is required to load a service-account file.\\n"\n'
        "            \"Install with: pip install 'tracebi[bigquery]'\"\n"
        "        ) from exc\n"
        "    return service_account.Credentials.from_service_account_file(path)\n"
        "\n"
        "from tracebi.connectors.bigquery_connector import BigQueryConnector\n"
        "\n"
        "connector = BigQueryConnector(\n"
        f"    {name!r},\n"
        f"    project=os.environ[{project!r}],\n"
        f"    dataset=os.environ[{dataset!r}],\n"
        "    credentials=_credentials(),\n"
        ")\n"
    )
