"""``tracebi connect`` — point a project at a warehouse the builder already has.

Writes ``connections/<name>.yaml`` (``tracebi.connections``): the type and its
fields, with every secret as a ``${ENV_VAR}`` reference, and puts the secret
itself in the project's ``.env``. With ``--python`` it writes the older
connector module under ``models/_connections/`` instead. Discovery loads only
top-level ``models/*.py`` files that define ``model``
(``model_registry.auto_discover`` is non-recursive and skips names starting
with ``_``), so a connection module beside the models would be reported as a
model that failed to load.

The legacy module calls ``load_dotenv()`` itself and reads ``os.environ[...]``.
This module never loads ``.env``.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KINDS = ("postgres", "mysql", "snowflake", "bigquery", "duckdb")

# Fields the connector constructor requires. ``--dataset`` is required because
# BigQueryConnector takes ``dataset`` with no default. ``--role`` and
# ``--credentials`` are optional and are not prompted.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "postgres": ("url",),
    "mysql": ("url",),
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
# A postgres or mysql connection given as --host ... instead of --url: these
# fields go into the file and the URL is built from them
# (tracebi.connections.build_url), as the app's form writes it.
_PARTS = ("host", "port", "database", "user", "password", "ssl")


def connection_path(models_dir: Path, name: str) -> Path:
    """Where ``tracebi connect <name>`` writes the connector module."""
    return models_dir / "_connections" / f"{name}.py"


def connection_yaml_path(name: str, connections_dir: "Path | None" = None) -> Path:
    """Where ``tracebi connect <name>`` writes the connection file."""
    from tracebi.connections import connections_dir as default_dir

    return Path(connections_dir or default_dir()) / f"{name}.yaml"


# What goes in .env for a declarative connection: only these. Everything else
# is written into the YAML, where it can be read and reviewed.
_ENV_FIELDS = {"postgres": ("url",), "snowflake": ("password",)}


def _scalar(field: str, value: str) -> str:
    import yaml

    return yaml.safe_dump({field: value}, allow_unicode=True, width=10**6).rstrip()


def _project_relative(path: str) -> "str | None":
    """*path* as a path inside the working directory, else None."""
    from tracebi.model.model_spec import _escapes

    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            return None
    rel = p.as_posix()
    return None if _escapes(rel) else rel


def _declared_document(name: str, kind: str, values: dict) -> tuple[str, dict]:
    """``(yaml text, {env key: secret})`` for ``connections/<name>.yaml``."""
    lines = [("name", name), ("type", kind)]
    updates: dict[str, str] = {}

    def literal(field: str) -> None:
        if values.get(field):
            lines.append((field, values[field]))

    def secret(field: str) -> None:
        key = env_var(name, field)
        updates[key] = values[field]
        lines.append((field, "${" + key + "}"))

    if kind in ("postgres", "mysql") and not values.get("url"):
        for field in _PARTS:
            if field == "password" and values.get("password_var"):
                lines.append(("password", "${" + values["password_var"] + "}"))
            elif field == "password" and values.get("password"):
                secret("password")
            else:
                literal(field)
    elif kind in ("postgres", "mysql"):
        secret("url")
    elif kind == "snowflake":
        for field in ("account", "user"):
            literal(field)
        secret("password")
        for field in ("warehouse", "database", "schema", "role"):
            literal(field)
    elif kind == "bigquery":
        for field in ("project", "dataset", "credentials"):
            literal(field)
    else:
        inside = _project_relative(values["database"])
        if inside is None:      # a warehouse outside the project: a path in .env
            secret("database")
        else:
            lines.append(("database", inside))
    body = "\n".join(_scalar(f, v) for f, v in lines)
    head = (f"# Connection {name!r} ({kind}). Written by `tracebi connect`.\n"
            "# ${NAME} is read from the environment, or from .env beside this\n"
            "# folder, when the connection is used. No secret belongs in this file.\n")
    return head + body + "\n", updates


def env_var(name: str, field: str) -> str:
    return f"TRACEBI_{name.upper()}_{field.upper()}"


def connect_command(args) -> int:
    """Test the warehouse (unless ``--no-test``), then write ``.env`` and the module.

    Files are written only after a successful test. An existing ``.env`` key
    or connection file is left untouched unless ``--force``.
    """
    if getattr(args, "list", False):
        return _list_connections(getattr(args, "connections_dir", None))
    name = args.name
    if not name:
        print("missing the connection's name (or --list)", file=sys.stderr)
        return 2
    if not _NAME.fullmatch(name):
        print(
            f"connection name {name!r} must be a Python identifier "
            "(letters, digits, underscore)",
            file=sys.stderr,
        )
        return 2

    agents = getattr(args, "agents", None)
    kind = (args.kind or "").strip().lower()
    # `tracebi connect <name> --agents a,b` on an existing connection changes
    # only which tables agents may read, as ticking them in the app does.
    existing = connection_yaml_path(name, getattr(args, "connections_dir", None))
    if agents is not None and not kind and existing.is_file():
        return _set_agents(existing, agents)
    # `tracebi connect <name> --test` on an existing connection tests it.
    if args.test and not kind and existing.is_file():
        return _test_existing(existing)
    tty = sys.stdin.isatty()
    if not kind:
        if not tty:
            print("missing required flags: --kind", file=sys.stderr)
            return 2
        kind = input("kind (postgres, mysql, snowflake, bigquery, duckdb): ").strip().lower()
    if kind not in _KINDS:
        print(
            f"unknown kind {kind!r}; expected one of: {', '.join(_KINDS)}",
            file=sys.stderr,
        )
        return 2

    required = _REQUIRED[kind]
    structured = kind in ("postgres", "mysql") and not args.url and bool(getattr(args, "host", None))
    if structured:
        required = ("host", "database")
    if getattr(args, "python", False) and (structured or kind == "mysql"):
        print("--python writes a postgres --url, snowflake, bigquery or duckdb "
              "connection; drop it to write connections/<name>.yaml", file=sys.stderr)
        return 2
    fields = required + _OPTIONAL.get(kind, ()) + (_PARTS if structured else ())
    values = {field: getattr(args, field, None) for field in dict.fromkeys(fields)}
    values = {k: (v.strip() if isinstance(v, str) else v) for k, v in values.items()}
    if structured:
        try:
            values.update(_password_flags(args))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    missing = [field for field in required if not values.get(field)]
    if missing:
        if not tty:
            also = " (or --host and --database)" if missing == ["url"] else ""
            print(
                "missing required flags: " + ", ".join(f"--{field}" for field in missing) + also,
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
    python_form = getattr(args, "python", False)
    if python_form:
        conn_path = connection_path(models_dir, name)
        updates = {
            env_var(name, field): values[field]
            for field in list(_REQUIRED[kind]) + list(_OPTIONAL.get(kind, ()))
            if values.get(field)
        }
    else:
        conn_path = connection_yaml_path(name, getattr(args, "connections_dir", None))
        text, updates = _declared_document(name, kind, values)
        if agents is not None and (allow := _allowlist(agents)):
            from tracebi.connections import _yaml_lines
            text += _yaml_lines("agents", allow) + "\n"
    env_path = Path.cwd() / ".env"
    # --store secret puts the secret in the project's encrypted store instead
    # of .env. The legacy module reads os.environ, so it keeps .env.
    to_store = getattr(args, "store", "dotenv") == "secret" and not python_form
    if to_store:
        from tracebi.project_credentials import _read_store

        conflicts = sorted(set(updates) & set(_read_store(Path.cwd())))
        where = "the credential store"
    else:
        conflicts = _env_conflicts(env_path, list(updates))
        where = ".env"
    problems: list[str] = []
    if conflicts and not args.force:
        problems.append(
            f"refusing to overwrite {where} keys without --force: " + ", ".join(conflicts)
        )
    if conn_path.exists() and not args.force:
        problems.append(
            f"refusing to overwrite existing {conn_path}; pass --force to replace"
        )
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    if args.test is not False:
        try:
            summary = _probe(_build_connector(name, kind, values))
        except Exception as exc:  # noqa: BLE001 — the driver's first line is the result
            print(_one_line_error(exc), file=sys.stderr)
            return 1
        print(f"{name}: {summary}")

    conn_path.parent.mkdir(parents=True, exist_ok=True)
    if python_form:
        env_rel = os.path.relpath(env_path, start=conn_path.parent)
        conn_path.write_text(_connection_source(name, kind, env_rel), encoding="utf-8")
    else:
        conn_path.write_text(text, encoding="utf-8")
    print(f"wrote {conn_path}")
    if updates and to_store:
        from tracebi.project_credentials import STORE_FILE, record_change, set_secret

        for key, value in updates.items():
            set_secret(key, value, Path.cwd())
            try:
                record_change(key, "set")
            except Exception:  # noqa: BLE001 — saved is saved; the run store is optional here
                pass
        print(f"wrote {STORE_FILE} (" + ", ".join(updates) + ")")
    elif updates:
        _apply_env(env_path, updates)
        added = _ensure_dotenv_ignored(Path.cwd() / ".gitignore")
        print("wrote .env (" + ", ".join(updates) + ")")
        if added:
            print("added .env to .gitignore")
    return 0


def _allowlist(raw: str) -> "dict | None":
    """``--agents a,b`` or ``--agents all`` as the file's ``agents`` value;
    an empty one is none."""
    from tracebi.connections import agents_allowlist

    raw = raw.strip()
    return agents_allowlist("*" if raw in ("all", "*") else [t.strip() for t in raw.split(",")])


def _agents_said(tables) -> str:
    if not tables:
        return "none"
    return "all" if tables == ["*"] else ", ".join(tables)


def _set_agents(path: Path, raw: str) -> int:
    """Rewrite only the ``agents`` key of an existing connection file."""
    from tracebi.connections import (
        agent_tables_of, read_connection_doc, rewrite_connection_text,
        validate_connection_doc,
    )

    doc = read_connection_doc(path)
    allow = _allowlist(raw)
    doc = {k: v for k, v in doc.items() if k != "agents"} | ({"agents": allow} if allow else {})
    errors = validate_connection_doc(doc)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    path.write_text(rewrite_connection_text(path.read_text(encoding="utf-8"), doc), encoding="utf-8")
    print(f"wrote {path} (agents may read: {_agents_said(agent_tables_of(doc))})")
    return 0


def _list_connections(folder) -> int:
    """``tracebi connect --list``: each connection file, its type, and the
    tables agents may read."""
    from tracebi.connections import (
        SUFFIXES, agent_tables_of, connections_dir, read_connection_doc,
        validate_connection_doc,
    )

    folder = Path(folder or connections_dir())
    paths = sorted(p for p in folder.glob("*") if p.suffix in SUFFIXES
                   and not p.name.startswith(("_", "."))) if folder.is_dir() else []
    if not paths:
        print(f"no connections in {folder}/ (tracebi connect <name> --kind ...)")
        return 0
    for path in paths:
        try:
            doc = read_connection_doc(path)
            errors = validate_connection_doc(doc)
        except Exception as exc:  # noqa: BLE001 — a broken file is listed as broken
            errors, doc = [str(exc)], {}
        if errors:
            print(f"{path.stem}  (does not load: {errors[0]})")
            continue
        print(f"{path.stem}  {doc['type']}  agents may read: {_agents_said(agent_tables_of(doc))}")
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


def _password_flags(args) -> dict:
    """``--password-stdin`` (the value, read from stdin and never echoed) or
    ``--password-var NAME`` (the file says ``${NAME}``; nothing is stored)."""
    from tracebi.project_credentials import NAME

    var = getattr(args, "password_var", None)
    if var and getattr(args, "password_stdin", False):
        raise ValueError("--password-stdin or --password-var, not both")
    if var:
        if not NAME.fullmatch(var):
            raise ValueError(f"--password-var: a variable name, [A-Z_][A-Z0-9_]*; got {var!r}")
        return {"password_var": var, "password": None}
    if getattr(args, "password_stdin", False):
        return {"password": sys.stdin.read().rstrip("\r\n")}
    return {}


def _test_existing(path: Path) -> int:
    """``tracebi connect <name> --test``: open a connection file's
    connection, list its tables, close it."""
    from tracebi.connections import load_connection, server_version
    from tracebi.sources import connection_tables

    try:
        connector = load_connection(path)
    except Exception as exc:  # noqa: BLE001 — a file that will not load is the answer
        print(_one_line_error(exc), file=sys.stderr)
        return 1
    got = connection_tables(connector)
    if not got.get("connected"):
        print(f"{path.stem}: could not connect · {got.get('reason')}", file=sys.stderr)
        return 1
    n = len(got.get("tables") or [])
    version = server_version(load_connection(path))
    print(f"{path.stem}: {n} table{'' if n == 1 else 's'}" + (f" · {version}" if version else ""))
    return 0


def _build_connector(name: str, kind: str, values: dict):
    """Construct the connector from the flags just collected. Does not read ``.env``."""
    if kind in ("postgres", "mysql") and not values.get("url"):
        from tracebi.connections import build_url
        from tracebi.connectors.sql_connector import SQLConnector

        fields = {k: v for k, v in values.items() if k in _PARTS and v}
        if values.get("password_var"):
            from tracebi.project_credentials import resolve
            fields["password"] = resolve(values["password_var"], Path.cwd())[0]
        return SQLConnector(name, url=build_url(kind, fields))
    if kind in ("postgres", "mysql"):
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


# Fact vs dimension, from metadata only: a table is a fact when its name
# starts with fact_, or when it has a numeric non-key column and a *_id/*_key
# column that names another listed table's own key. Everything else is a
# dimension. Own key is <stem>_id or <stem>_key (dim_/fact_ stripped; a
# trailing s dropped — ponytail: not a real pluralizer, so "status" is tried
# whole before "statu"), else id, else the only key-shaped column.


def draft_model_command(args) -> int:
    """Draft ``models/<slug>.yaml`` (``--python``: ``.py``) from
    ``column_schema`` of the named tables.

    No table scan. Guessed lines are marked ``# DRAFT: review``. A connection
    that is the workspace's own warehouse file is written ``type: warehouse``,
    as the reference models are; any other, ``connection: <name>``.
    """
    from tracebi.cli import _slugify

    connection = (args.from_connection or "").strip()
    if not connection:
        print("missing required flags: --from", file=sys.stderr)
        return 2
    if not _NAME.fullmatch(connection):
        print(
            f"connection name {connection!r} must be a Python identifier",
            file=sys.stderr,
        )
        return 2

    tables_arg = args.tables
    if not tables_arg:
        if sys.stdin.isatty():
            tables_arg = input("--tables: ").strip()
        if not tables_arg:
            print("missing required flags: --tables", file=sys.stderr)
            return 2
    tables = []
    for part in tables_arg.split(","):
        name = part.strip()
        if name and name not in tables:
            tables.append(name)
    if not tables:
        print("missing required flags: --tables", file=sys.stderr)
        return 2

    models_dir: Path = args.models_dir
    conn_path = _find_connection(models_dir, connection)
    if conn_path is None:
        print(
            f"connection {connection!r} not found at "
            f"{connection_yaml_path(connection)} — "
            f"run `tracebi connect {connection}` first",
            file=sys.stderr,
        )
        return 1

    slug = _slugify(args.title)
    python = bool(getattr(args, "python", False))
    out_path = models_dir / f"{slug}.{'py' if python else 'yaml'}"
    if out_path.exists() and not args.force:
        print(
            f"refusing to overwrite existing {out_path}; pass --force to replace",
            file=sys.stderr,
        )
        return 1

    schemas = _read_schemas(conn_path, tables)
    if schemas is None:
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    warehouse = False
    if python:
        text = _model_source(args.title, slug, connection, _classify(schemas),
                             declared=conn_path.suffix != ".py")
    else:
        warehouse = _is_workspace_warehouse(conn_path, Path.cwd())
        text = _model_yaml(args.title, slug, connection, _classify(schemas), warehouse)
    out_path.write_text(text, encoding="utf-8")
    print(f"Created {out_path}")
    if not python:
        print("  It reads " + ("the workspace's warehouse (type: warehouse)." if warehouse
                               else f"connection {connection!r} (connection: {connection})."))
    print("  Lines marked # DRAFT: review are guesses — edit and approve them.")
    print("  Edit the file, then use it with:")
    print("    from tracebi.model_registry import get_model")
    print(f'    model = get_model("{slug}")')
    return 0


def _is_workspace_warehouse(conn_path: Path, root: Path) -> bool:
    """A declared DuckDB connection whose file is the workspace's file-tier
    warehouse (``tracebi init`` writes ``connections/warehouse.yaml`` so)."""
    if conn_path.suffix == ".py":
        return False
    try:
        from tracebi.connections import read_connection_doc
        from tracebi.project_config import warehouse

        doc = read_connection_doc(conn_path)
        wh = warehouse(str(root))
    except Exception:  # noqa: BLE001 — unreadable: not provably the warehouse
        return False
    if not isinstance(doc, dict) or doc.get("type") != "duckdb" or wh.tier != "file":
        return False
    database = doc.get("database")
    if not isinstance(database, str) or "${" in database:
        return False
    return os.path.abspath(os.path.join(str(root), database)) == wh.address


def _find_connection(models_dir: Path, name: str) -> "Path | None":
    """The connection's file: ``connections/<name>.yaml``, else the legacy
    ``models/_connections/<name>.py``."""
    from tracebi.connections import connection_file

    declared = connection_file(name)
    if declared is not None:
        return declared
    legacy = connection_path(models_dir, name)
    return legacy if legacy.is_file() else None


def _read_schemas(conn_path: Path, tables: list[str]) -> dict | None:
    import runpy

    try:
        if conn_path.suffix == ".py":
            namespace = runpy.run_path(str(conn_path))
        else:
            from tracebi.connections import load_connection
            namespace = {"connector": load_connection(conn_path, Path.cwd())}
    except Exception as exc:  # noqa: BLE001 — a broken connection is the result
        print(_one_line_error(exc), file=sys.stderr)
        return None
    connector = namespace.get("connector")
    if connector is None:
        print(f"{conn_path} does not define connector", file=sys.stderr)
        return None
    schemas: dict = {}
    try:
        for table in tables:
            try:
                schema = connector.column_schema(table)
            except Exception as exc:  # noqa: BLE001 — first driver line, and no model written
                print(_one_line_error(exc), file=sys.stderr)
                return None
            if not schema:
                print(
                    f"{table}: this connector cannot describe columns without reading rows",
                    file=sys.stderr,
                )
                return None
            schemas[table] = schema
    finally:
        _release(connector)
    return schemas


def _is_key_column(name: str) -> bool:
    low = name.lower()
    return low == "id" or low.endswith("_id") or low.endswith("_key")


def _is_numeric(dtype: str) -> bool:
    head = dtype.split("(", 1)[0].strip().upper()
    if head.endswith("INT"):
        return True
    return head in {
        "FLOAT", "DOUBLE", "REAL", "DECIMAL", "NUMERIC", "NUMBER",
        "FLOAT4", "FLOAT8", "FLOAT64", "FLOAT32",
    } or head.startswith(("DECIMAL", "NUMERIC", "FLOAT"))


def _summable(column: str) -> bool:
    """Sum would be refused for a rate-named or stock-named measure."""
    from tracebi.model.data_model import _RATE_TOKEN, _STOCK_TOKEN

    low = column.lower()
    return not (_RATE_TOKEN.search(low) or _STOCK_TOKEN.search(low))


def _stem_forms(table: str) -> list[str]:
    low = table.lower()
    forms: list[str] = []

    def add(value: str) -> None:
        if value and value not in forms:
            forms.append(value)

    add(low)
    for prefix in ("dim_", "fact_"):
        if low.startswith(prefix):
            add(low[len(prefix):])
            break
    for form in list(forms):
        if form.endswith("s") and not form.endswith("ss") and len(form) > 1:
            add(form[:-1])
    return forms


def _own_key(table: str, columns: list[dict]) -> str | None:
    by_lower: dict[str, str] = {}
    for col in columns:
        by_lower.setdefault(col["name"].lower(), col["name"])
    for form in _stem_forms(table):
        for suffix in ("_id", "_key"):
            hit = by_lower.get(form + suffix)
            if hit:
                return hit
    if "id" in by_lower:
        return by_lower["id"]
    keys = [col["name"] for col in columns if _is_key_column(col["name"])]
    if len(keys) == 1:
        return keys[0]
    return None


def _dim_name(table: str) -> str:
    if table.lower().startswith("dim_"):
        return table
    return "dim_" + table


def _classify(schemas: dict[str, list[dict]]) -> list[dict]:
    own = {table: _own_key(table, columns) for table, columns in schemas.items()}
    drafts = []
    for table, columns in schemas.items():
        fks = []
        for col in columns:
            name = col["name"]
            if name == own[table] or not _is_key_column(name):
                continue
            for other, other_key in own.items():
                if other == table or not other_key:
                    continue
                if other_key.lower() == name.lower():
                    fks.append((name, other, other_key))
                    break
        numeric = [
            col["name"] for col in columns
            if _is_numeric(col["dtype"]) and not _is_key_column(col["name"])
            and col["name"] != own[table]
        ]
        fact = table.lower().startswith("fact_") or bool(numeric and fks)
        drafts.append({
            "table": table,
            "columns": columns,
            "own_key": own[table],
            "fks": fks,
            "numeric": numeric,
            "fact": fact,
        })
    return drafts


def _y(value: str) -> str:
    """A YAML scalar: bare when it is a plain name YAML reads as a string,
    else JSON-quoted (a column named ``on`` or ``null`` is not a bool)."""
    plain = _NAME.fullmatch(value) and value.lower() not in _YAML_WORDS
    return value if plain else json.dumps(value)


_YAML_WORDS = {"y", "n", "yes", "no", "on", "off", "true", "false", "null"}


def _model_yaml(title: str, slug: str, connection: str, drafts: list[dict],
                warehouse: bool) -> str:
    """The draft :func:`_model_source` writes, in the model file's YAML form."""
    heading = title.strip() or slug
    conn = "warehouse" if warehouse else connection
    lines = [
        f"# {heading}",
        "#",
        f"# Drafted by `tracebi new-model --from {connection}` on {date.today().isoformat()}.",
        "# Lines marked `# DRAFT: review` are guesses from column metadata (no rows",
        "# were read). Edit and approve them before a report depends on this model.",
        "#",
        "#     from tracebi.model_registry import get_model",
        f'#     model = get_model("{slug}")',
        "",
        f"name: {slug}",
        f"label: {json.dumps(heading)}",
        "",
        "connectors:",
        f"  - name: {_y(conn)}",
        "    type: warehouse" if warehouse else f"    connection: {_y(connection)}",
        "",
        "tables:",
    ]
    for draft in drafts:
        lines += [f"  - name: {_y(draft['table'])}", f"    connector: {_y(conn)}",
                  f"    source: {_y(draft['table'])}"]
    dim_of = {d["table"]: _dim_name(d["table"]) for d in drafts if not d["fact"]}
    dims = [d for d in drafts if not d["fact"]]
    facts = [d for d in drafts if d["fact"]]
    if dims:
        lines += ["", "dimensions:"]
    for draft in dims:
        key = draft["own_key"] or draft["columns"][0]["name"]
        attrs = [col["name"] for col in draft["columns"] if col["name"] != key]
        lines += ["  # DRAFT: review", f"  - name: {_y(dim_of[draft['table']])}",
                  f"    table: {_y(draft['table'])}", f"    key: {_y(key)}",
                  f"    attributes: [{', '.join(_y(a) for a in attrs)}]"]
    if facts:
        lines += ["", "facts:"]
    for draft in facts:
        measures = [col for col in draft["numeric"] if _summable(col)]
        fks = {dim_of[other]: col for col, other, _right in draft["fks"] if other in dim_of}
        lines += ["  # DRAFT: review", f"  - name: {_y(draft['table'])}",
                  f"    table: {_y(draft['table'])}",
                  f"    measures: [{', '.join(_y(m) for m in measures)}]"]
        if fks:
            lines.append("    foreign_keys:")
            lines += [f"      {_y(dim)}: {_y(col)}" for dim, col in fks.items()]
        for col in draft["numeric"]:
            if col not in measures:
                lines.append(f"    # DRAFT: review — {col!r} looks like a rate or a stock, "
                             "so it is not a sum")
    rels = [(d, col, other, right) for d in drafts for col, other, right in d["fks"]]
    if rels:
        lines += ["", "relationships:"]
    for draft, col, other, right_key in rels:
        lines += ["  # DRAFT: review", f"  - name: {_y(draft['table'] + '__' + col)}",
                  f"    left_table: {_y(draft['table'])}", f"    right_table: {_y(other)}",
                  f"    left_key: {_y(col)}", f"    right_key: {_y(right_key)}"]
    used: set[str] = set()
    sums = []
    for draft in facts:
        for col in draft["numeric"]:
            if not _summable(col):
                continue
            measure = col if col not in used else f"{draft['table']}_{col}"
            used.add(measure)
            sums.append((measure, col))
    if sums:
        lines += ["", "measures:"]
    for measure, col in sums:
        lines += ["  # DRAFT: review", f"  - name: {_y(measure)}", f"    column: {_y(col)}",
                  "    agg: sum"]
    lines.append("")
    return "\n".join(lines)


def _model_source(title: str, slug: str, connection: str, drafts: list[dict],
                  declared: bool = False) -> str:
    model_name = title.strip().replace(" ", "") or slug
    if declared:
        wire = [
            "import os",
            "",
            "from tracebi import DataModel",
            "from tracebi.connections import connection_file, load_connection",
            "",
            "ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))",
            f"connector = load_connection(connection_file({connection!r}, ROOT), ROOT)",
        ]
    else:
        wire = [
            "import os",
            "import runpy",
            "",
            "from tracebi import DataModel",
            "",
            "_conn = runpy.run_path(os.path.join(",
            "    os.path.dirname(os.path.abspath(__file__)),",
            f"    {f'_connections/{connection}.py'!r}))",
            'connector = _conn["connector"]',
        ]
    lines = [
        '"""',
        title.strip() or slug,
        "=" * len(title.strip() or slug),
        "",
        f"DataModel drafted by ``tracebi new-model --from {connection}`` on {date.today().isoformat()}.",
        "",
        "Lines marked ``# DRAFT: review`` are guesses from column metadata",
        "(no rows were read). Edit and approve them before a report depends",
        "on this model.",
        "",
        "    from tracebi.model_registry import get_model",
        f'    model = get_model("{slug}")',
        '"""',
        "",
        *wire,
        "",
        "# Importing this file must not query the warehouse. A query connects.",
        "",
        f"model = DataModel({model_name!r})",
        "model.add_connector(connector)",
    ]
    for draft in drafts:
        table = draft["table"]
        lines.append(
            f"model.add_table({table!r}, connector={connection!r}, source={table!r})"
        )
    dim_of = {
        draft["table"]: _dim_name(draft["table"])
        for draft in drafts if not draft["fact"]
    }
    for draft in drafts:
        if draft["fact"]:
            continue
        table = draft["table"]
        key = draft["own_key"] or draft["columns"][0]["name"]
        attrs = [col["name"] for col in draft["columns"] if col["name"] != key]
        lines.append("# DRAFT: review")
        lines.append(
            f"model.add_dimension({dim_of[table]!r}, table_name={table!r}, "
            f"key_col={key!r}, attributes={attrs!r})"
        )
    for draft in drafts:
        if not draft["fact"]:
            continue
        measures = [col for col in draft["numeric"] if _summable(col)]
        skipped = [col for col in draft["numeric"] if col not in measures]
        fks = {
            dim_of[other]: col
            for col, other, _right in draft["fks"] if other in dim_of
        }
        lines.append("# DRAFT: review")
        lines.append(
            f"model.add_fact({draft['table']!r}, table_name={draft['table']!r}, "
            f"measures={measures!r}, foreign_keys={fks!r})"
        )
        for col in skipped:
            lines.append(
                f"# DRAFT: review — {col!r} looks like a rate or a stock, so it is not a sum"
            )
    used: set[str] = set()
    for draft in drafts:
        for col, other, right_key in draft["fks"]:
            lines.append("# DRAFT: review")
            rel_name = f"{draft['table']}__{col}"
            lines.append(
                "model.add_relationship("
                f"name={rel_name!r}, "
                f"left_table={draft['table']!r}, right_table={other!r}, "
                f"left_key={col!r}, right_key={right_key!r})"
            )
        if not draft["fact"]:
            continue
        for col in draft["numeric"]:
            if not _summable(col):
                continue
            measure = col if col not in used else f"{draft['table']}_{col}"
            used.add(measure)
            lines.append("# DRAFT: review")
            lines.append(
                f"model.add_measure({measure!r}, column={col!r}, agg='sum')"
            )
    lines.append("")
    return "\n".join(lines)
