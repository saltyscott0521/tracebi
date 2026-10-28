"""
Sources as data: ``connections/<name>.yaml``.

A connection is a type and its fields. Any value may be a ``${ENV_VAR}``
reference (the whole value, ``[A-Z_][A-Z0-9_]*``), optionally with a default,
``${ENV_VAR:-default}``, used when the name is set nowhere; a
credential-bearing field (a password, a URL that carries one) *must* be a
reference, and a default must pass the same check as a literal, so a secret
is never in the file. The schema is closed, and the file loads with ``yaml.safe_load``
semantics and a repeated key is an error (``tracebi.model.model_spec``'s
loader).

Loading is lazy twice over. Reading the file builds a connector object and
resolves nothing; the connector reads its environment variables when it
actually connects, so a missing variable is an error naming it at that
moment, not at discovery. ``describe()`` and ``storage()`` (what the Sources
page shows) never resolve a credential: a referenced secret appears as
``${NAME}``.

``${NAME}`` is looked up in the process environment, then in the project's
``.env`` (where ``tracebi connect`` put the secret), then in the project's
credential store (``tracebi secret set``; :mod:`tracebi.project_credentials`,
the one resolver). Only referenced names are read, and nothing is copied into
``os.environ``.

A ``postgres`` or ``mysql`` connection is one ``url`` or its fields (``host``,
``port``, ``database``, ``user``, ``password: ${NAME}``, ``ssl``, ...), never
both; :func:`build_url` and :func:`parse_url` map one to the other, and the
loader builds the URL from the fields when the connection is used.

``agents: {tables: [a, b] | "*"}`` says which tables an agent may read;
:func:`agent_may_read` is the one check. The app writes these files too
(:func:`plan_connection`, :func:`connection_text`,
:func:`rewrite_connection_text`), a secret typed into its form going to the
store, never into the file.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from tracebi.model.model_spec import (
    ModelSpecError, _escapes, _NAME, _unknown, _unique_key_loader,
)
from tracebi.project_credentials import REF as _REF

SUFFIXES = (".yaml", ".yml")
_SECRET_QUERY = re.compile(r"pass|pwd|secret|token|key", re.I)

# type -> (connector class name, required fields, optional fields)
_TYPES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "duckdb": ("DuckDBConnector", ("database",), ("directory",)),
    "csv": ("CSVConnector", ("directory",), ("encoding",)),
    "sql": ("SQLConnector", ("url",), ()),
    "postgres": ("SQLConnector", ("url",), ()),
    "mysql": ("SQLConnector", ("url",), ()),
    "snowflake": ("SnowflakeConnector",
                  ("account", "user", "warehouse", "database"),
                  ("password", "schema", "role", "authenticator", "private_key_path")),
    "bigquery": ("BigQueryConnector", ("project", "dataset"),
                 ("credentials", "credentials_json")),
    "upload": ("UploadConnector", ("file",), ()),
}
# A Postgres or MySQL connection is said as one ``url``, or as these fields
# (required, optional), from which the loader builds the URL
# (:func:`build_url`); a file says one or the other, never a mix.
_URL_PARTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "postgres": (("host", "database"),
                 ("port", "user", "password", "ssl", "options", "connect_timeout")),
    "mysql": (("host", "database"),
              ("port", "user", "password", "ssl", "options", "connect_timeout")),
}
# The driver a URL built from fields names, and the schemes a pasted URL may
# use to be said as fields. psycopg 3 is what the postgres extra installs; a
# URL naming another driver stays a URL.
_SCHEME = {"postgres": "postgresql+psycopg", "mysql": "mysql+pymysql", "snowflake": "snowflake"}
_SCHEMES = {"postgres": ("postgresql+psycopg", "postgresql", "postgres"),
            "mysql": ("mysql+pymysql", "mysql"), "snowflake": ("snowflake",)}
_DEFAULT_PORT = {"postgres": "5432", "mysql": "3306"}
# ssl, as each type says it: postgres's sslmode; mysql on or off.
_SSL = {"postgres": ("disable", "prefer", "require", "verify-full"), "mysql": ("on", "off")}
# How a Snowflake user signs in. ``key_pair`` reads private_key_path.
_AUTHENTICATORS = ("password", "externalbrowser", "key_pair")
# Fields that are a whole number when literal.
_NUMBER_FIELDS = {"port", "connect_timeout"}
# A literal value is never allowed: the field holds a credential.
_MUST_REFERENCE = {"password", "credentials_json"}
# A literal is allowed only when it carries no credential (see _url_problem).
_URL_FIELDS = {"url"}
# Paths a literal may only name inside the project.
_PATH_FIELDS = {"database": ("duckdb",), "directory": ("duckdb", "csv"),
                "file": ("upload",)}
# An uploaded file is a CSV or Parquet file under inputs/, where the app's
# upload puts it (POST /api/inputs), so it is reviewed with the project.
UPLOAD_SUFFIXES = (".csv", ".parquet")

# What the app's Add a connection form asks for, per type: a name for people,
# one line, the group its card is under, and each field's label, kind (text |
# number | secret | url | path | choice) and help. The form is drawn from this
# (GET /api/connections/types), so a type added to _TYPES is offered once it
# is described here. A ``secret`` field's value goes to the project's store,
# and a ``url`` one's too when it carries a credential; the file holds
# ``${NAME}`` for either.
_TYPE_INFO: dict[str, tuple[str, str, str]] = {
    "postgres": ("Postgres", "A Postgres database: its host, database and user, or one URL.",
                 "Databases"),
    "mysql": ("MySQL", "A MySQL or MariaDB database: its host, database and user, or one URL.",
              "Databases"),
    "sql": ("SQLite or another SQL database",
            "Any SQLAlchemy URL: a SQLite file in the workspace, SQL Server, Oracle.", "Databases"),
    "duckdb": ("DuckDB", "A DuckDB database file in the workspace.", "Databases"),
    "snowflake": ("Snowflake", "A Snowflake warehouse: a password, a browser sign-in or a key pair.",
                  "Warehouses"),
    "bigquery": ("BigQuery", "A BigQuery dataset, read with a service account.", "Warehouses"),
    "csv": ("A folder of CSV files", "Every CSV or Excel file in one folder of the workspace.", "Files"),
    "upload": ("An uploaded file", "One CSV or Parquet file, uploaded into inputs/.", "Files"),
}
_FIELD_INFO: dict[str, tuple[str, str, str]] = {
    # field: (label, kind, help)
    "url": ("URL", "url", "A SQLAlchemy URL. One that carries a password is kept "
                          "in the workspace's encrypted store, not in the file."),
    "host": ("Host", "text", "The server's name or address, e.g. db.example.com."),
    "port": ("Port", "number", ""),
    "database": ("Database", "text", ""),
    "directory": ("Folder", "path", "A folder inside the workspace, e.g. inputs/."),
    "encoding": ("Encoding", "text", "The files' text encoding; utf-8 when empty."),
    "account": ("Account", "text", "The account identifier, e.g. xy12345.eu-west-1."),
    "user": ("User", "text", ""),
    "password": ("Password", "secret", "Kept in the workspace's encrypted store, never in the file."),
    "ssl": ("SSL", "choice", ""),
    "options": ("Extra options", "text", "More connection parameters as a query string, "
                                         "e.g. application_name=tracebi. No credential."),
    "connect_timeout": ("Connect timeout (s)", "number",
                        "Seconds to wait for the server; the driver's default when empty."),
    "warehouse": ("Warehouse", "text", ""),
    "schema": ("Schema", "text", "PUBLIC when empty."),
    "role": ("Role", "text", ""),
    "authenticator": ("Sign-in", "choice", "password when empty. externalbrowser opens the "
                                           "identity provider's page on the server; key_pair "
                                           "reads a private key file."),
    "private_key_path": ("Private key file", "path",
                         "The key pair's private key (.p8) on the server. Only with key_pair."),
    "project": ("Project", "text", "The Google Cloud project id."),
    "dataset": ("Dataset", "text", ""),
    "credentials": ("Service-account file", "path", "A path to the JSON key file on the server."),
    "credentials_json": ("Service-account JSON", "secret",
                         "Or paste the key file's JSON: it is kept in the encrypted store "
                         "and the file names it."),
    "file": ("File", "path", "The uploaded file under inputs/ (.csv or .parquet)."),
}
# Where a field's words differ by type.
_FIELD_BY_TYPE: dict[tuple[str, str], tuple[str, str, str]] = {
    ("duckdb", "database"): ("Database file", "path",
                             "A .duckdb file inside the workspace, e.g. inputs/sales.duckdb."),
    ("postgres", "url"): ("URL", "url", "postgresql+psycopg://user@host:5432/db. "
                                        "A password in it is kept in the encrypted store."),
    ("mysql", "url"): ("URL", "url", "mysql+pymysql://user@host:3306/db. "
                                     "A password in it is kept in the encrypted store."),
    ("sql", "url"): ("URL", "url", "sqlite:///inputs/bank.sqlite for a file in the workspace, "
                                   "or any SQLAlchemy URL."),
    ("postgres", "ssl"): ("SSL mode", "choice", "require encrypts the connection; verify-full "
                                                "also checks the server's certificate."),
    ("mysql", "ssl"): ("SSL", "choice", "on encrypts the connection."),
    ("snowflake", "password"): ("Password", "secret",
                                "Kept in the workspace's encrypted store, never in the file. "
                                "Only with the password sign-in."),
}
# The fields under the form's Advanced disclosure.
_ADVANCED = {"ssl", "options", "connect_timeout", "role", "encoding"}
# The order the form asks in, where it is not required-then-optional.
_FORM_ORDER = {
    "postgres": ("host", "port", "database", "user", "password", "ssl", "options",
                 "connect_timeout"),
    "mysql": ("host", "port", "database", "user", "password", "ssl", "options",
              "connect_timeout"),
    "snowflake": ("account", "user", "authenticator", "password", "private_key_path",
                  "warehouse", "database", "schema", "role"),
}


def _field_info(ctype: str, field: str) -> tuple[str, str, str]:
    return _FIELD_BY_TYPE.get((ctype, field), _FIELD_INFO[field])


def _choices(ctype: str, field: str) -> Optional[tuple[str, ...]]:
    if field == "ssl":
        return _SSL[ctype]
    if field == "authenticator":
        return _AUTHENTICATORS
    return None


def connection_types() -> list[dict]:
    """The types a connection may have, each with its fields, for the app's
    form: ``[{type, label, line, group, url_scheme, fields: [{name, label,
    kind, required, help, advanced, choices?, default?}]}]``, in the order the
    form offers them. A type with a ``url_scheme`` has two views of one
    connection, its fields and one URL (:func:`build_url`, :func:`parse_url`);
    a postgres or mysql file may store either, a snowflake one its fields."""
    out = []
    for ctype, (label, line, group) in _TYPE_INFO.items():
        _cls, required, optional = _TYPES[ctype]
        if ctype in _URL_PARTS:
            required, optional = _URL_PARTS[ctype]
        names = _FORM_ORDER.get(ctype, required + optional)
        fields = []
        for field in names:
            flabel, kind, help_ = _field_info(ctype, field)
            row = {"name": field, "label": flabel, "kind": kind,
                   "required": field in required, "help": help_,
                   "advanced": field in _ADVANCED}
            if choices := _choices(ctype, field):
                row["choices"] = list(choices)
            if field == "port" and ctype in _DEFAULT_PORT:
                row["default"] = _DEFAULT_PORT[ctype]
            fields.append(row)
        out.append({"type": ctype, "label": label, "line": line, "group": group,
                    "url_scheme": _SCHEME.get(ctype), "fields": fields})
    return out


# ── A connection's URL, from its fields and back ───────────────────────────
#
# The app's form shows a SQL connection two ways, its fields and one URL, and
# typing in either changes the other (DBeaver's Main and URL tabs). These two
# are that mapping. A value that is a whole ${NAME} stays one, unencoded, so a
# URL built from a connection file carries the reference, never the value; a
# literal user, password or database is percent-encoded.

def _query_pieces(query: str) -> list[tuple[str, str, str]]:
    """``[(key, value, raw piece)]`` of a query string, in order."""
    out = []
    for piece in query.split("&"):
        if piece:
            key, _sep, value = piece.partition("=")
            out.append((unquote(key), unquote(value), piece))
    return out


def _quoted(value: str) -> str:
    return value if _REF.fullmatch(value) else quote(value, safe="")


def build_url(ctype: str, fields: dict) -> str:
    """The URL a ``postgres``, ``mysql`` or ``snowflake`` connection's fields
    say: ``postgresql+psycopg://user:password@host:5432/db?sslmode=require``,
    ``snowflake://user@account/db/schema?warehouse=wh&role=r``. Empty fields
    are left out. Pure: resolves nothing."""
    if ctype not in _SCHEME:
        raise ValueError(f"a {ctype} connection has no URL form")
    f = {k: v.strip() for k, v in fields.items() if isinstance(v, str) and v.strip()}
    auth = ""
    if f.get("user"):
        auth = _quoted(f["user"])
        if f.get("password"):
            auth += ":" + _quoted(f["password"])
        auth += "@"
    query: list[str] = []
    if ctype == "snowflake":
        where = f.get("account", "")
        path = "/".join(_quoted(f[k]) for k in ("database", "schema") if f.get(k))
        for key in ("warehouse", "role"):
            if f.get(key):
                query.append(f"{key}={quote(f[key], safe='')}")
        if f.get("authenticator") == "externalbrowser":
            query.append("authenticator=externalbrowser")
        elif f.get("authenticator") == "key_pair":
            query.append("authenticator=snowflake_jwt")
            if f.get("private_key_path"):
                query.append(f"private_key_file={quote(f['private_key_path'], safe='/')}")
    else:
        where = f.get("host", "") + (f":{f['port']}" if f.get("port") else "")
        path = _quoted(f["database"]) if f.get("database") else ""
        ssl = f.get("ssl")
        if ssl and ctype == "postgres":
            query.append(f"sslmode={ssl}")
        elif ssl == "on":
            query.append("ssl_check_hostname=true")
        if f.get("connect_timeout"):
            query.append(f"connect_timeout={f['connect_timeout']}")
        if f.get("options"):
            query.append(f["options"].lstrip("?&"))
    url = f"{_SCHEME[ctype]}://{auth}{where}" + (f"/{path}" if path else "")
    return url + ("?" + "&".join(query) if query else "")


def parse_url(ctype: str, url: str) -> dict:
    """The fields a ``postgres``, ``mysql`` or ``snowflake`` URL says, the
    inverse of :func:`build_url`: ``{host, port, database, user, password,
    ssl, connect_timeout, options}`` (only those present; values decoded).
    ``ValueError`` for a URL these fields cannot say: another database or
    driver, or no host. Pure: resolves nothing."""
    if ctype not in _SCHEMES:
        raise ValueError(f"a {ctype} connection has no URL form")
    scheme, sep, rest = url.strip().partition("://")
    if not sep or scheme.lower() not in _SCHEMES[ctype]:
        raise ValueError(f"a {ctype} URL starts {_SCHEME[ctype]}://, got {scheme or url!r}")
    rest = rest.partition("#")[0]
    rest, _q, query = rest.partition("?")
    netloc, _slash, path = rest.partition("/")
    userinfo, at, hostport = netloc.rpartition("@")
    out: dict[str, str] = {}
    if at:
        user, colon, password = userinfo.partition(":")
        if user:
            out["user"] = unquote(user)
        if colon and password:
            out["password"] = unquote(password)
    if ctype == "snowflake":
        if not hostport:
            raise ValueError("a snowflake URL names the account after the @")
        out["account"] = hostport
        for key, value in zip(("database", "schema"), [unquote(p) for p in path.split("/") if p]):
            out[key] = value
        for key, value, _raw in _query_pieces(query):
            if key in ("warehouse", "role"):
                out[key] = value
            elif key == "authenticator":
                out[key] = "key_pair" if value.lower() == "snowflake_jwt" else value.lower()
            elif key == "private_key_file":
                out["private_key_path"] = value
        return out
    host, colon, port = hostport.rpartition(":")
    if not colon or not port.isdigit():
        host, port = hostport, ""
    if not host:
        raise ValueError(f"a {ctype} URL names its host after the @")
    out["host"] = host
    if port:
        out["port"] = port
    if path:
        out["database"] = unquote(path)
    options = []
    for key, value, raw in _query_pieces(query):
        if ctype == "postgres" and key == "sslmode":
            out["ssl"] = value
        elif ctype == "mysql" and key == "ssl_check_hostname" and value.lower() == "true":
            out["ssl"] = "on"
        elif key == "connect_timeout":
            out["connect_timeout"] = value
        else:
            options.append(raw)
    if options:
        out["options"] = "&".join(options)
    return out


def _said_as_fields(ctype: str, url: str) -> Optional[dict]:
    """The fields a URL sent for a postgres or mysql connection becomes when
    it carries a password, so the password can be its own ``${NAME}``: None
    when it carries none, or says something the fields cannot (another
    driver, a credential among its options)."""
    if ctype not in _URL_PARTS:
        return None
    try:
        fields = parse_url(ctype, url)
    except ValueError:
        return None
    if not fields.get("password") or _REF.fullmatch(fields["password"]):
        return None
    if any(_SECRET_QUERY.search(k) for k, _v, _r in _query_pieces(fields.get("options", ""))):
        return None
    return fields


class ConnectionConfigError(ValueError):
    """A connection that cannot be built: bad file, or an unset variable.
    ``variable`` names the unset variable when that is the reason, so a page
    can say which one to set without parsing the message."""

    variable: Optional[str] = None


def connections_dir(root: "str | os.PathLike[str] | None" = None) -> Path:
    """``TRACEBI_CONNECTIONS_DIR``, else ``<root>/connections`` (root: cwd)."""
    env = os.environ.get("TRACEBI_CONNECTIONS_DIR")
    if env:
        return Path(env)
    return Path(root if root is not None else ".") / "connections"


def connection_file(name: str, root: "str | os.PathLike[str] | None" = None) -> Optional[Path]:
    """The declarative file for connection *name*, if there is one."""
    base = connections_dir(root)
    for suffix in SUFFIXES:
        path = base / f"{name}{suffix}"
        if path.is_file():
            return path
    return None


def read_connection_doc(path: "str | os.PathLike[str]") -> Any:
    path = Path(path)
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("YAML connections need PyYAML: pip install pyyaml") from exc
    try:
        return yaml.load(path.read_text(encoding="utf-8"),  # noqa: S506 — a SafeLoader subclass
                         Loader=_unique_key_loader())
    except yaml.YAMLError as exc:
        raise ModelSpecError(path.name, [f"not valid YAML ({' '.join(str(exc).split())})"]) from exc


# A SQLite URL names a file: ``sqlite:///inputs/bank.sqlite`` (relative) or
# ``sqlite:////abs/bank.sqlite``. SQLAlchemy reads a relative one against the
# process's working directory, so it is resolved against the project root.
_SQLITE = re.compile(r"^(sqlite(?:\+\w+)?:///)([^?]*)(\?.*)?$")


def _sqlite_file(url: str) -> Optional[str]:
    """The file a SQLite URL names, or None (another dialect, or memory)."""
    match = _SQLITE.match(url)
    if match is None or match.group(2) in ("", ":memory:"):
        return None
    return match.group(2)


def _url_problem(url: str) -> Optional[str]:
    path = _sqlite_file(url)
    if path is not None and _escapes(path):
        return (f"a literal SQLite file must stay inside the workspace (no absolute "
                f"path, no '..'), got {path!r}; use ${{ENV_VAR}} to point elsewhere")
    try:
        parts = urlsplit(url)
        query = parse_qsl(parts.query)
        password = parts.password
    except ValueError:
        return "is not a parseable URL"
    if password or any(_SECRET_QUERY.search(k) for k, _ in query):
        return ("carries a credential; write the whole url as ${ENV_VAR} "
                "and put the value in .env")
    return None


def _agents_problems(agents: Any) -> list[str]:
    """``agents: {tables: [a, b] | "*"}``: which tables agents may read."""
    shape = 'agents: {tables: [a, b]} or {tables: "*"}'
    if not isinstance(agents, dict) or set(agents) != {"tables"}:
        return [f"{shape}, got {agents!r}"]
    tables = agents["tables"]
    if tables == "*":
        return []
    if not isinstance(tables, list) or not all(isinstance(t, str) and t for t in tables):
        return [f"{shape}: tables is a list of table names, or \"*\" for all"]
    if len(set(tables)) != len(tables):
        return ["agents: a table is named twice"]
    return []


def agent_tables_of(doc: dict) -> Optional[list[str]]:
    """The allowlist a validated document states: its table names, ``["*"]``
    for every table, None when it states none (agents read nothing)."""
    agents = doc.get("agents")
    if not agents:
        return None
    tables = agents["tables"]
    return ["*"] if tables == "*" else list(tables)


def agent_may_read(connection: Any, table: str) -> bool:
    """Whether an agent may read *table* of *connection*: the one check the
    gateway and a model's live read ask. *connection* is a connector (its
    ``agent_tables``) or a connection's name (its ``connections/<name>.yaml``
    is read). No allowlist means none; TraceBi's own tables never."""
    from tracebi.sources import is_framework_table

    if isinstance(connection, str):
        path = connection_file(connection)
        if path is None:
            return False
        connection = load_connection(path)
    allowed = getattr(connection, "agent_tables", None)
    if not allowed or is_framework_table(table):
        return False
    return allowed == ["*"] or table in allowed


def validate_connection_doc(doc: Any) -> list[str]:
    """Structural errors in a connection document, each led by its field."""
    if not isinstance(doc, dict):
        return ["the file must hold one object (a mapping at the top level)"]
    ctype = doc.get("type")
    if ctype not in _TYPES:
        return [f"type: required, one of {', '.join(_TYPES)}; got {ctype!r}"]
    _cls, required, optional = _TYPES[ctype]
    parts = _URL_PARTS.get(ctype, ((), ()))
    errors = _unknown(doc, {"name", "type", "label", "agents", *required, *optional,
                            *parts[0], *parts[1]}, "connection")
    said = [f for f in (*parts[0], *parts[1]) if f in doc]
    if "url" in doc and said:
        errors.append(f"url: a {ctype} connection is one url or its fields "
                      f"({', '.join(said)}), not both")
    elif ctype in _URL_PARTS and "url" not in doc:
        if not said:
            return errors + [f"url: required for type '{ctype}', or its fields: "
                             f"{', '.join(parts[0])}"]
        required, optional = parts
    errors += _form_problems(ctype, doc)
    if not isinstance(doc.get("name"), str) or not _NAME.fullmatch(doc.get("name") or ""):
        errors.append("name: required, letters, digits and underscores")
    if "label" in doc and (not isinstance(doc["label"], str) or not doc["label"].strip()):
        errors.append("label: a name for people, a non-empty string")
    if "agents" in doc:
        errors += _agents_problems(doc["agents"])
    if ctype == "upload" and isinstance(doc.get("file"), str) and not _REF.fullmatch(doc["file"]):
        path = doc["file"].replace("\\", "/")
        if not path.startswith("inputs/") or not path.lower().endswith(UPLOAD_SUFFIXES):
            errors.append(f"file: a .csv or .parquet file under inputs/, got {doc['file']!r}")
    for field in required + optional:
        if field not in doc:
            if field in required:
                errors.append(f"{field}: required for type '{ctype}'")
            continue
        value = doc[field]
        if not isinstance(value, str) or not value:
            errors.append(f"{field}: must be a non-empty string")
            continue
        ref = _REF.fullmatch(value)
        if ref and ref.group(2) is None:
            continue
        if ref:
            # A default is a literal that ships in the file: it is checked as
            # one below, so a secret cannot hide behind ${NAME:-...}.
            value = ref.group(2)
            if not value:
                errors.append(f"{field}: the default after ':-' is empty; drop it "
                              f"or write a value")
                continue
            if field in _MUST_REFERENCE:
                errors.append(f"{field}: a credential has no default; write "
                              f"${{ENV_VAR}} alone and set the value on the server")
                continue
        if "${" in value:
            errors.append(f"{field}: ${{ENV_VAR}} must be the whole value "
                          f"([A-Z_][A-Z0-9_]*), got {value!r}")
        elif field in _MUST_REFERENCE:
            errors.append(f"{field}: a credential; write it as ${{ENV_VAR}} "
                          f"and put the value in .env, never in this file")
        elif field in _URL_FIELDS and (why := _url_problem(value)):
            errors.append(f"{field}: {why}")
        elif ctype in _PATH_FIELDS.get(field, ()) and value != ":memory:" and _escapes(value):
            errors.append(f"{field}: a literal path must stay inside the workspace "
                          f"(no absolute path, no '..'), got {value!r}; use "
                          f"${{ENV_VAR}} to point elsewhere")
        elif field in _NUMBER_FIELDS and not value.isdigit():
            errors.append(f"{field}: a whole number, got {value!r}")
        elif (choices := _choices(ctype, field)) and value not in choices:
            errors.append(f"{field}: one of {', '.join(choices)}; got {value!r}")
        elif field == "options" and (why := _options_problem(value)):
            errors.append(f"options: {why}")
    return errors


def _literal(doc: dict, field: str) -> Optional[str]:
    """*field*'s literal value, or None when absent or a ``${NAME}``."""
    value = doc.get(field)
    return value if isinstance(value, str) and not _REF.fullmatch(value) else None


def _form_problems(ctype: str, doc: dict) -> list[str]:
    """What one field asks of another: a Snowflake sign-in and what it reads,
    one BigQuery credential."""
    errors = []
    if ctype == "snowflake":
        auth = _literal(doc, "authenticator") or "password"
        if auth == "password" and "password" not in doc:
            errors.append("password: required for the password sign-in "
                          "(authenticator: externalbrowser or key_pair needs none)")
        if auth == "key_pair" and "private_key_path" not in doc:
            errors.append("private_key_path: required with authenticator: key_pair")
        if auth != "key_pair" and "private_key_path" in doc and "authenticator" in doc:
            errors.append("private_key_path: only with authenticator: key_pair")
    if ctype == "bigquery" and "credentials" in doc and "credentials_json" in doc:
        errors.append("credentials: a file path or credentials_json, not both")
    return errors


def _options_problem(options: str) -> Optional[str]:
    """Extra query parameters carry no credential and do not restate a field."""
    keys = [k for k, _v, _r in _query_pieces(options.lstrip("?&"))]
    if any(_SECRET_QUERY.search(k) for k in keys):
        return ("carries a credential; a password is its own field, "
                "written as ${ENV_VAR}")
    if said := [k for k in keys if k in ("sslmode", "ssl_check_hostname", "connect_timeout")]:
        return f"{', '.join(said)} is its own field (ssl, connect_timeout)"
    return None


# ── Reading the environment ────────────────────────────────────────────────

def _read_dotenv(path: Path) -> dict[str, str]:
    """``KEY=value`` lines, as ``tracebi connect`` writes them. Not loaded
    into ``os.environ``; callers ask for the names they reference."""
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("export "):
            raw = raw[len("export "):].strip()
        key, sep, value = raw.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1),
                           value[1:-1])
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


# ── The connector ──────────────────────────────────────────────────────────

class _Declared:
    """Mixed into the real connector class. The fields that hold ``${REF}``
    (or a path to resolve) read through ``_value`` on access, so nothing is
    resolved before the connector is used."""

    _decl: "Declaration"

    def __getattribute__(self, item: str):
        if not item.startswith("_"):
            decl = object.__getattribute__(self, "__dict__").get("_decl")
            if decl is not None and decl.provides(item):
                return decl.value(item)
        return object.__getattribute__(self, item)

    @property
    def declared_in(self) -> Optional[str]:
        return self._decl.source

    def describe(self) -> dict:
        return self._decl.describe(self)

    def storage(self) -> dict:
        if "url" in self._decl.fields or self._decl.structured:
            return self._decl.url_storage()
        try:
            return super().storage()
        except ConnectionConfigError as exc:
            return {"kind": "unknown", "where": f"unresolved: {exc}",
                    "exists": None, "size": None}

    def disconnect(self) -> None:
        release = getattr(super(), "disconnect", None)
        if release is None:
            return
        try:
            release()
        except ConnectionConfigError:
            pass  # the variables were never readable, so nothing was opened


class Declaration:
    """A parsed connection file: its fields, and how each one resolves."""

    def __init__(self, name: str, ctype: str, fields: dict[str, str],
                 root: Path, source: Optional[str]) -> None:
        self.name, self.ctype, self.fields = name, ctype, fields
        self.root, self.source = root, source
        self._lock = threading.Lock()
        # A postgres or mysql connection said as fields: its url is built.
        self.structured = ctype in _URL_PARTS and "url" not in fields

    def provides(self, item: str) -> bool:
        """Whether the connector's attribute *item* reads from the file: a
        field, the url its fields build, or BigQuery credentials from pasted
        JSON."""
        return item in self.fields or (item == "url" and self.structured) \
            or (item == "credentials" and "credentials_json" in self.fields)

    def is_ref(self, field: str) -> bool:
        return bool(_REF.fullmatch(self.fields[field]))

    def shown(self, field: str) -> str:
        """The field as the file wrote it; a reference stays ``${NAME}``."""
        return self.fields[field]

    def _env(self, raw: str, field: str) -> str:
        from tracebi.project_credentials import CredentialError, Missing, expand

        try:
            return expand(raw, self.root)[0]
        except Missing as exc:
            var = exc.name
            err = ConnectionConfigError(
                f"connection '{self.name}': environment variable {var} "
                f"(field '{field}') is not set; set it in the environment or "
                f"in {self.root / '.env'}")
            err.variable = var
            raise err from None
        except CredentialError as exc:
            raise ConnectionConfigError(f"connection '{self.name}': {exc}") from None

    def value(self, field: str) -> Any:
        if field == "url" and self.structured:
            # Each field resolves as it is read, so an unset password's
            # variable is named here, when the connection is used.
            return build_url(self.ctype, {f: self.value(f) for f in self.fields})
        if field == "credentials" and "credentials_json" in self.fields:
            return _bq_info_credentials(self.value("credentials_json"))
        raw = self.fields[field]
        value = self._env(raw, field) if _REF.fullmatch(raw) else raw
        if field in _PATH_FIELDS and self.ctype in _PATH_FIELDS[field] \
                and value != ":memory:" and not os.path.isabs(value):
            return str((self.root / value).resolve())
        if field in _URL_FIELDS:
            return self._rooted(value)
        if field == "credentials" and self.ctype == "bigquery":
            from tracebi.connect import _bq_credentials
            return _bq_credentials(value)
        if field == "private_key_path" and not os.path.isabs(value):
            return str((self.root / value).resolve())
        return value

    def _rooted(self, url: str) -> str:
        """A relative SQLite URL resolved against the project root."""
        path = _sqlite_file(url)
        if path is None or os.path.isabs(path):
            return url
        match = _SQLITE.match(url)
        return f"{match.group(1)}{(self.root / path).resolve()}{match.group(3) or ''}"

    def _literal_url(self) -> Optional[str]:
        """The URL as the file states it, with no credential read: a literal,
        or a ``${NAME:-default}``'s default while *NAME* is set nowhere. None
        when a variable supplies it, since saying where would mean reading
        the secret."""
        from tracebi.project_credentials import CredentialError, Missing, parse, resolve

        raw = self.fields["url"]
        ref = parse(raw)
        if ref is None:
            return raw
        name, default = ref
        if not default:
            return None
        try:
            resolve(name, self.root)    # only whether it is set; the value is dropped
        except Missing:
            return default
        except CredentialError:
            pass                        # the store holds it, unreadably: still set
        return None

    def url_storage(self) -> dict:
        """Where a ``url`` connection's data lives, without reading a
        credential: the file or host its literal URL names, else which
        variable sets it."""
        from tracebi.connectors.sql_connector import url_storage

        if self.structured:
            # Host and database as the file says them; the password is left
            # out, so nothing is resolved.
            return url_storage(build_url(self.ctype, {
                k: v for k, v in self.fields.items() if k not in ("user", "password")}))
        literal = self._literal_url()
        if literal is not None:
            return url_storage(self._rooted(literal))
        name = _REF.fullmatch(self.fields["url"]).group(1)
        return {"kind": "database", "where": f"set by {name}", "variable": name,
                "exists": None, "size": None}

    def dialect(self) -> Optional[str]:
        """What kind of database a ``url`` connection is: from the URL the
        file states, else from its type (``postgres``)."""
        from tracebi.connectors.sql_connector import url_dialect

        literal = None if self.structured else self._literal_url()
        if literal is not None:
            return url_dialect(literal)
        return {"postgres": "postgresql", "mysql": "mysql"}.get(self.ctype)

    def describe(self, connector) -> dict:
        out = {"name": self.name, "type": type(connector).__name__}
        if connector.label:
            out["label"] = connector.label
        if self.source:
            out["declared_in"] = self.source
        # The file's own words, for the app's Edit form: a reference stays
        # ${NAME}, and a literal is never a credential (the validator refuses
        # one), so nothing here is a secret.
        out["connection_type"] = self.ctype
        out["fields"] = {k: v for k, v in self.fields.items() if k != "label"}
        out["agent_tables"] = getattr(connector, "agent_tables", None)
        for field in ("database", "directory", "file"):
            if field in self.fields and self.ctype in _PATH_FIELDS[field]:
                try:
                    out[field] = self.value(field)
                except ConnectionConfigError:
                    out[field] = self.shown(field)
        if "url" in self.fields:
            if self.is_ref("url"):
                out["url"] = self.shown("url")
            else:
                out["url"] = connector._redacted_url()
            if dialect := self.dialect():
                out["dialect"] = dialect
        elif self.structured:
            # The URL the fields build, as the file says them: the password
            # stays ${NAME}, so the app's URL view never carries the value.
            out["url"] = build_url(self.ctype, self.fields)
            out["dialect"] = self.dialect()
        return out


def _bq_info_credentials(text: str):
    """BigQuery credentials from a service account's JSON, pasted into the
    form and kept in the store (``credentials_json``)."""
    import json

    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise ImportError(
            "google-cloud-bigquery is required to read a service account.\n"
            "Install with: pip install 'tracebi[bigquery]'") from exc
    try:
        info = json.loads(text)
    except ValueError:
        raise ConnectionConfigError("credentials_json: not a service account's JSON") from None
    return service_account.Credentials.from_service_account_info(info)


_UPLOAD_CLASS = None


def _upload_connector_class():
    """``UploadConnector``: one CSV or Parquet file as one table, named by
    the file's stem. Built on first use, so reading connection files does not
    import pandas."""
    global _UPLOAD_CLASS
    if _UPLOAD_CLASS is not None:
        return _UPLOAD_CLASS
    import pandas as pd

    from tracebi.connectors.base import BaseConnector, _on_disk

    class UploadConnector(BaseConnector):
        def __init__(self, name: str, file: Optional[str] = None) -> None:
            super().__init__(name)
            self.file = file

        def _table(self) -> str:
            return Path(self.file).stem

        def _check(self, source: str) -> str:
            if source != self._table():
                raise KeyError(f"connection '{self.name}' holds one table, "
                               f"'{self._table()}', not {source!r}")
            return self.file

        def connect(self) -> None:
            if not os.path.isfile(self.file):
                raise FileNotFoundError(f"connection '{self.name}': file not found: {self.file}")

        def describe(self) -> dict:
            return {**super().describe(), "file": self.file}

        def storage(self) -> dict:
            return _on_disk("file", str(self.file))

        def list_tables(self) -> list[str]:
            self.connect()
            return [self._table()]

        def column_schema(self, source: str) -> list[dict[str, str]]:
            path = self._check(source)
            if path.lower().endswith(".parquet"):
                import pyarrow.parquet as pq
                schema = pq.read_schema(path)
                return [{"name": f.name, "dtype": str(f.type)} for f in schema]
            df = pd.read_csv(path, nrows=0)
            return [{"name": str(c), "dtype": str(df.dtypes[c])} for c in df.columns]

        def load(self, source: str, filter=None, columns=None) -> "pd.DataFrame":
            path = self._check(source)
            if path.lower().endswith(".parquet"):
                df = pd.read_parquet(path, columns=columns or None)
            else:
                df = pd.read_csv(path, usecols=columns or None)
            return self._apply_pandas_pushdown(df, filter, columns)

    UploadConnector.__module__ = __name__
    _UPLOAD_CLASS = UploadConnector
    return UploadConnector


def _connector_class(ctype: str):
    cls_name = _TYPES[ctype][0]
    if cls_name == "UploadConnector":
        base = _upload_connector_class()
        return type(cls_name, (_Declared, base), {"__module__": base.__module__})
    import importlib
    mod = {"DuckDBConnector": "duckdb_connector", "CSVConnector": "csv_connector",
           "SQLConnector": "sql_connector", "SnowflakeConnector": "snowflake_connector",
           "BigQueryConnector": "bigquery_connector"}[cls_name]
    base = getattr(importlib.import_module(f"tracebi.connectors.{mod}"), cls_name)
    # Same __name__ as the real class: code that tells a DuckDB warehouse
    # apart by type(c).__name__ keeps working.
    return type(cls_name, (_Declared, base), {"__module__": base.__module__})


def build_connection(doc: dict, root: "str | os.PathLike[str]",
                     source: Optional[str] = None):
    """The connector for a validated document. Resolves nothing."""
    ctype = doc["type"]
    fields = {k: v for k, v in doc.items() if k not in ("name", "type", "agents")}
    decl = Declaration(doc["name"], ctype, fields, Path(root).resolve(), source)
    cls = _connector_class(ctype)
    # The real constructor stores its arguments and does no work; the
    # placeholders are never read, _Declared answers for them.
    args = {
        "bigquery": {"project": None, "dataset": None},
        "sql": {"url": None}, "postgres": {"url": None}, "mysql": {"url": None},
        "snowflake": {"account": None, "user": None, "password": None,
                      "warehouse": None, "database": None},
        "csv": {"directory": "."},
        "duckdb": {"database": ":memory:"},
        "upload": {"file": None},
    }[ctype]
    connector = cls(doc["name"], **args)
    connector.label = doc.get("label")
    # Which tables agents may read (agent_may_read): None reads nothing.
    connector.agent_tables = agent_tables_of(doc)
    # Installed after construction, so the constructor above does not resolve.
    connector.__dict__["_decl"] = decl
    return connector


def load_connection(path: "str | os.PathLike[str]",
                    root: "str | os.PathLike[str] | None" = None):
    """Compile ``connections/<name>.yaml`` into a connector. Reads no
    environment and opens nothing. *root* (default: the folder above
    ``connections/``) is what relative paths and ``.env`` resolve against."""
    path = Path(path)
    doc = read_connection_doc(path)
    errors = validate_connection_doc(doc)
    if not errors and doc["name"] != path.stem:
        errors.append(f"name: must equal the file name '{path.stem}', got {doc['name']!r}")
    if errors:
        raise ModelSpecError(path.name, errors)
    root = Path(root) if root is not None else path.resolve().parent.parent
    try:
        shown = os.path.relpath(path.resolve(), Path.cwd())
    except ValueError:
        shown = str(path)
    return build_connection(doc, root, shown)


def validate_connection_file(path: "str | os.PathLike[str]") -> list[str]:
    try:
        load_connection(path)
    except ModelSpecError as exc:
        return exc.errors
    except Exception as exc:  # noqa: BLE001 — the answer is the message
        return [str(exc)]
    return []


def server_version(connector) -> Optional[str]:
    """``PostgreSQL 16.4``: the database's own version, from a SQL
    connection's dialect, read on one short-lived connection; None where the
    driver does not say or it cannot be read."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from tracebi.connectors.sql_connector import SQLConnector

    if not isinstance(connector, SQLConnector):
        return None
    try:
        engine = create_engine(connector.url, poolclass=NullPool)
        try:
            with engine.connect():
                info = engine.dialect.server_version_info
            dialect = engine.dialect
        finally:
            engine.dispose()
    except Exception:  # noqa: BLE001 — the test already answered; this is extra
        return None
    if not info:
        return None
    name = "MariaDB" if getattr(dialect, "is_mariadb", False) else {
        "postgresql": "PostgreSQL", "mysql": "MySQL", "sqlite": "SQLite",
        "mssql": "SQL Server", "oracle": "Oracle"}.get(dialect.name, dialect.name)
    return f"{name} {'.'.join(str(p) for p in info if isinstance(p, int))}"


# ── Writing a connection file (the app's Add a connection, and Edit) ───────

def _yaml_lines(key: str, value: Any) -> str:
    import yaml

    return yaml.safe_dump({key: value}, allow_unicode=True, width=10**6,
                          sort_keys=False, default_flow_style=False).rstrip()


def secret_name(name: str, field: str) -> str:
    """The ``${NAME}`` a connection's secret field is stored under:
    ``TRACEBI_<CONNECTION>_<FIELD>``, as ``tracebi connect`` names it."""
    return f"TRACEBI_{name.upper()}_{field.upper()}"


def _goes_to_store(ctype: str, field: str, value: str) -> bool:
    """Whether a value typed for *field* is a secret: a ``secret`` field
    always, a ``url`` one when it carries a credential."""
    kind = _FIELD_BY_TYPE.get((ctype, field), _FIELD_INFO.get(field, ("", "text", "")))[1]
    if kind == "secret":
        return True
    return kind == "url" and (_url_problem(value) or "").startswith("carries a credential")


def _url_or_fields(ctype: str, fields: dict, existing: Optional[dict]):
    """``(fields, existing, (required, optional))`` for a postgres or mysql
    connection, in the one form it is written in: its fields when any is
    sent (or a URL sent carries a password), else its url when one is sent
    or the file has one, else its fields."""
    parts = _URL_PARTS[ctype]
    structured = (*parts[0], *parts[1])
    existing = existing or {}

    def sent(field: str) -> bool:
        return isinstance(fields.get(field), str) and bool(fields[field].strip())

    url = (fields.get("url") or "").strip()
    if url and not any(sent(f) for f in structured) and (split := _said_as_fields(ctype, url)):
        fields = split
    if any(sent(f) for f in structured):
        form = "fields"
    elif url or "url" in existing:
        form = "url"
    else:
        form = "fields"
    if form == "url":
        return ({"url": fields.get("url")} if "url" in fields else {},
                {k: v for k, v in existing.items() if k not in structured}, (("url",), ()))
    # A file that was one url keeps none of it: the fields say it all now.
    return ({k: v for k, v in fields.items() if k != "url"},
            {k: v for k, v in existing.items() if k != "url"}, parts)


def plan_connection(name: str, ctype: str, fields: dict[str, Optional[str]],
                    label: Optional[str] = None, agents: Any = None,
                    existing: Optional[dict] = None) -> tuple[dict, dict[str, str]]:
    """``(document, {NAME: secret})`` for a connection the app saves.

    *fields* are what the form sent. A value that is a whole ``${NAME}``
    stays a reference (the person pointed at a variable); a secret typed in
    is replaced by ``${TRACEBI_<CONNECTION>_<FIELD>}`` (or the name the file
    already uses) and returned to be saved in the store, so the file never
    holds it. On an edit (*existing*, the current document), a field not
    sent keeps what the file says, and so does a secret or URL sent empty (a
    masked field reads empty); any other field sent empty is removed. The
    caller validates the document.

    A postgres or mysql connection is written the way the form said it: its
    fields, or one ``url``. A URL whose password is in it is written as its
    fields (:func:`parse_url`), so the file and the store come out the same
    as had the fields been typed: the password its own ``${NAME}``."""
    if ctype not in _TYPES:
        raise ModelSpecError(f"{name}.yaml", [f"type: one of {', '.join(_TYPES)}; got {ctype!r}"])
    _cls, required, optional = _TYPES[ctype]
    if ctype in _URL_PARTS:
        fields, existing, (required, optional) = _url_or_fields(ctype, fields, existing)
    doc: dict[str, Any] = {"name": name, "type": ctype}
    if label:
        doc["label"] = label
    secrets: dict[str, str] = {}
    names = [f for f in _FORM_ORDER.get(ctype, ()) if f in required + optional]
    for field in names or required + optional:
        value = fields.get(field)
        value = value.strip() if isinstance(value, str) else value
        before = (existing or {}).get(field)
        if not value:
            kind = _field_info(ctype, field)[1]
            if before and (field not in fields or kind in ("secret", "url")):
                doc[field] = before
            continue
        if _REF.fullmatch(value) or not _goes_to_store(ctype, field, value):
            doc[field] = value
            continue
        ref = _REF.fullmatch(before) if isinstance(before, str) else None
        key = ref.group(1) if ref and ref.group(2) is None else secret_name(name, field)
        secrets[key] = value
        doc[field] = "${" + key + "}"
    if agents:
        doc["agents"] = agents
    return doc, secrets


def connection_text(doc: dict) -> str:
    """A new ``connections/<name>.yaml``: a header that says where secrets
    are, then one line per field."""
    head = (f"# Connection {doc['name']!r} ({doc['type']}). Written by the app's "
            "Add a connection.\n"
            "# ${NAME} is read from the environment, .env or the workspace's store\n"
            "# when the connection is used. No secret belongs in this file.\n")
    return head + "\n".join(_yaml_lines(k, v) for k, v in doc.items()) + "\n"


_TOP_KEY = re.compile(r"^([A-Za-z_]\w*)\s*:")


def rewrite_connection_text(text: str, doc: dict) -> str:
    """*text* (an existing file) changed to say *doc*: each top-level key's
    block is replaced where it stands, a key *doc* drops is removed, a new one
    is added at the end. Comments and the order a person chose are kept."""
    lines = text.splitlines()
    blocks: list[tuple[Optional[str], list[str]]] = []
    for line in lines:
        m = _TOP_KEY.match(line)
        if m:
            blocks.append((m.group(1), [line]))
        elif blocks and blocks[-1][0] is not None and (line[:1] in (" ", "\t", "-") or not line.strip()):
            blocks[-1][1].append(line)
        else:
            blocks.append((None, [line]))
    out, seen = [], set()
    for key, body in blocks:
        if key is None:
            out += body
            continue
        seen.add(key)
        if key not in doc:
            continue
        trailing = [ln for ln in reversed(body) if not ln.strip()]
        out += _yaml_lines(key, doc[key]).splitlines() + trailing
    out += [ln for k, v in doc.items() if k not in seen for ln in _yaml_lines(k, v).splitlines()]
    return "\n".join(out).rstrip("\n") + "\n"


def agents_allowlist(tables: Any) -> Optional[dict]:
    """The ``agents`` value for *tables*: ``"*"`` or ``"all"`` for every
    table, a list for those, None (the key removed) for none."""
    if tables in ("*", "all") or tables == ["*"]:
        return {"tables": "*"}
    tables = [t for t in (tables or []) if t]
    return {"tables": list(dict.fromkeys(tables))} if tables else None


# ── Migrating a connection module ──────────────────────────────────────────

class ConnectionMigrationError(ValueError):
    """A connection module that cannot be written as YAML, with the reason."""


class _Marker(dict):
    """Stands in for ``os.environ`` while a legacy connection module runs:
    every name reads back as ``${NAME}``, so the connector it builds holds the
    references, not anyone's secrets."""

    def __getitem__(self, key):
        return "${" + str(key) + "}"

    def get(self, key, default=None):
        return "${" + str(key) + "}"

    def __contains__(self, key):
        return True

    def __setitem__(self, key, value):
        pass


class _PathCredentials:
    def __init__(self, path: str) -> None:
        self.path = path


def _run_legacy(path: Path):
    """Run a ``models/_connections/<x>.py`` module under :class:`_Marker`."""
    import runpy
    import sys
    import types

    service_account = types.ModuleType("google.oauth2.service_account")
    service_account.Credentials = types.SimpleNamespace(
        from_service_account_file=lambda p: _PathCredentials(p))
    stubs = {"google": types.ModuleType("google"),
             "google.oauth2": types.ModuleType("google.oauth2"),
             "google.oauth2.service_account": service_account}
    stubs["google"].oauth2 = stubs["google.oauth2"]
    stubs["google.oauth2"].service_account = service_account
    saved_modules = {k: sys.modules.get(k) for k in stubs}
    saved_environ = os.environ
    sys.modules.update(stubs)
    os.environ = _Marker()  # type: ignore[assignment]
    try:
        return runpy.run_path(str(path)).get("connector")
    finally:
        os.environ = saved_environ
        for key, module in saved_modules.items():
            if module is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = module


def _migrated_fields(connector) -> dict:
    from tracebi.connectors import (
        BigQueryConnector, CSVConnector, DuckDBConnector, SnowflakeConnector,
        SQLConnector,
    )

    if getattr(connector, "declared_in", None):
        raise ConnectionMigrationError("it is already declarative")
    if isinstance(connector, DuckDBConnector):
        out = {"type": "duckdb", "database": connector.database}
        if connector.directory:
            out["directory"] = connector.directory
        return out
    if isinstance(connector, CSVConnector):
        out = {"type": "csv", "directory": connector.directory}
        if connector.encoding != "utf-8":
            out["encoding"] = connector.encoding
        return out
    if isinstance(connector, SQLConnector):
        if connector._engine_kwargs:
            raise ConnectionMigrationError(
                "it passes extra engine arguments to SQLConnector, which a "
                "connection file cannot carry")
        return {"type": "sql", "url": connector.url}
    if isinstance(connector, SnowflakeConnector):
        out = {"type": "snowflake", "account": connector.account,
               "user": connector.user, "password": connector.password,
               "warehouse": connector.warehouse, "database": connector.database}
        if connector.schema != "PUBLIC":
            out["schema"] = connector.schema
        if connector.role:
            out["role"] = connector.role
        return out
    if isinstance(connector, BigQueryConnector):
        out = {"type": "bigquery", "project": connector.project,
               "dataset": connector.dataset}
        if isinstance(connector.credentials, _PathCredentials):
            out["credentials"] = connector.credentials.path
        elif connector.credentials is not None:
            raise ConnectionMigrationError(
                "its credentials are built in code, not read from a file path")
        return out
    raise ConnectionMigrationError(
        f"{type(connector).__name__} has no connection type (the types are "
        f"{', '.join(_TYPES)}); it stays Python")


def connection_to_yaml(path: "str | os.PathLike[str]") -> str:
    """The ``connections/<name>.yaml`` text for a legacy
    ``models/_connections/<name>.py``, or :class:`ConnectionMigrationError`
    naming what cannot be expressed. The module is run with every environment
    variable reading back as ``${NAME}``, so a secret is never read."""
    import yaml

    path = Path(path)
    try:
        connector = _run_legacy(path)
    except Exception as exc:  # noqa: BLE001 — a module that will not run is the answer
        raise ConnectionMigrationError(
            f"the module did not run ({type(exc).__name__}: {exc})") from exc
    if connector is None:
        raise ConnectionMigrationError("it does not define 'connector'")
    if connector.name != path.stem:
        raise ConnectionMigrationError(
            f"it builds a connector named {connector.name!r} but the file is "
            f"{path.stem!r}; a connection's name is its file name")
    fields = _migrated_fields(connector)
    root = Path.cwd().resolve()
    for key in ("database", "directory"):
        value = fields.get(key)
        if key in fields and fields["type"] in _PATH_FIELDS[key] \
                and isinstance(value, str) and not _REF.fullmatch(value) \
                and value != ":memory:" and os.path.isabs(value):
            try:
                fields[key] = Path(value).resolve().relative_to(root).as_posix()
            except ValueError:
                raise ConnectionMigrationError(
                    f"{key} {value!r} is outside the workspace; put it in an "
                    f"environment variable and read it as ${{ENV_VAR}}") from None
    doc = {"name": path.stem, **fields}
    errors = validate_connection_doc(doc)
    if errors:
        raise ConnectionMigrationError("; ".join(errors))
    body = "\n".join(yaml.safe_dump({k: v}, allow_unicode=True, width=10**6).rstrip()
                     for k, v in doc.items())
    return (f"# Connection {path.stem!r} ({doc['type']}), migrated from "
            f"models/_connections/{path.stem}.py.\n"
            "# ${NAME} is read from the environment, or from .env beside this\n"
            "# folder, when the connection is used. No secret belongs in this file.\n"
            + body + "\n")
