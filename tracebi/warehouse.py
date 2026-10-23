"""The warehouse: where phase ① sinks and phase ② reads, on one of three tiers.

``tracebi.yaml`` names it once (:func:`tracebi.project_config.warehouse`)::

    warehouse:
      tier: file                       # file | object | remote
      location: data/warehouse.duckdb

- **file** (the default): one DuckDB file. The model attaches it read-only.
- **object**: one Parquet file per table under a prefix, ``s3://bucket/prefix``
  or ``gs://bucket/prefix`` (R2 and MinIO through ``s3://`` and an
  ``endpoint``), or a local directory. A transform's ``write(df, table)``
  lands ``<location>/<table>.parquet``; the model's tables are views over
  ``read_parquet`` of those files. Remote prefixes go through DuckDB's
  ``httpfs`` extension and a ``CREATE TEMPORARY SECRET`` built from the
  block's ``key_id`` / ``secret`` / ``region`` / ``endpoint``, each resolved
  from ``${VAR}`` when a connection is made, never stored.
- **remote**: a DuckDB database to ``ATTACH`` (``md:my_db`` on MotherDuck, a
  path, or the name of a ``connections/<name>.yaml`` of type duckdb). The
  model attaches it read-only; a transform writes into it.

The freeze point is the same on every tier; only its address moves. What a
transform writes to is :attr:`Warehouse.sink`, a string (the file path, the
prefix, the attach string) that remembers its warehouse, so
``DuckDBConnector(name, database=sink)`` and ``contract(name, warehouse=sink)``
follow the tier without the transform naming one.

The model's query connection (:mod:`tracebi.model.engine`) stays locked on
every tier. :meth:`Warehouse.attach` does what a locked connection cannot,
before the lock: loads ``httpfs``, creates the secret, defines the views, and
returns the exact files the views read so the engine can allow those and
nothing else.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urlsplit

TIERS = ("file", "object", "remote")
#: The file tier's location when ``tracebi.yaml`` names none.
DEFAULT_LOCATION = os.path.join("data", "warehouse.duckdb")
#: Prefixes the object tier reads through httpfs. R2 and MinIO are s3://
#: with an ``endpoint``.
OBJECT_SCHEMES = ("s3", "gs", "gcs")
#: The keys only the object tier takes; key_id and secret must be ${VAR}.
OBJECT_KEYS = ("endpoint", "region", "key_id", "secret", "url_style")
SECRET_KEYS = ("key_id", "secret")
#: The certificate's name inside an object-tier prefix (no .parquet suffix,
#: so it is never mistaken for a table).
OBJECT_CERTIFICATE = "_contracts.json"


class WarehouseConfigError(ValueError):
    """A warehouse that cannot be reached: a bad block or an unset variable."""


def _lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


class SinkTarget(str):
    """A warehouse address (path, prefix or attach string) that remembers its
    :class:`Warehouse`. It is a plain string everywhere a string is expected;
    the connector and the contracts read ``.warehouse`` to follow the tier."""

    warehouse: "Warehouse"

    def __new__(cls, value: str, warehouse: "Warehouse") -> "SinkTarget":
        obj = super().__new__(cls, value)
        obj.warehouse = warehouse
        return obj

    def __reduce__(self):
        return (SinkTarget, (str(self), self.warehouse))


def as_warehouse(target, root: Optional[str] = None) -> "Warehouse":
    """The :class:`Warehouse` of *target*: a :class:`Warehouse`, a
    :class:`SinkTarget`, or a plain path (the file tier, as before tiers)."""
    if isinstance(target, Warehouse):
        return target
    wh = getattr(target, "warehouse", None)
    if isinstance(wh, Warehouse):
        return wh
    return Warehouse("file", os.path.abspath(str(target)),
                     os.path.abspath(root or os.getcwd()))


@dataclass(frozen=True)
class Warehouse:
    """One project's warehouse. Built by :func:`tracebi.project_config.warehouse`,
    which has already checked the block's shape; ``${VAR}`` values resolve
    when a connection is made."""

    tier: str
    location: str
    root: str
    options: tuple = ()               # ((key, value as written), ...), object tier
    source: Optional[str] = None      # the tracebi.yaml it came from, for messages

    # ── Addresses ─────────────────────────────────────────────────────────

    @property
    def is_url(self) -> bool:
        """An object tier on remote storage (s3://, gs://), read through httpfs."""
        return self.tier == "object" and urlsplit(self.location).scheme in OBJECT_SCHEMES

    @property
    def address(self) -> str:
        """The location, made absolute: a path for the file tier and a local
        object directory, the prefix (no trailing slash) for remote storage,
        the attach string as written for the remote tier."""
        loc = self.location
        if self.tier == "remote":
            return loc
        if self.is_url:
            return loc.rstrip("/")
        if loc.startswith("file://"):
            loc = loc[len("file://"):]
        return os.path.abspath(os.path.join(self.root, loc)).rstrip(os.sep) or os.sep

    @property
    def sink(self) -> SinkTarget:
        """What a transform writes to (see :func:`tracebi.project_config.sink_target`)."""
        return SinkTarget(self.address, self)

    def table_path(self, table: str) -> str:
        """Object tier: where *table* lands, ``<location>/<table>.parquet``."""
        return f"{self.address}/{table}.parquet"

    @property
    def certificate(self) -> str:
        """Where the sink contracts' certificate lives: beside the file on the
        file tier, inside the prefix on the object tier, and in the project's
        ``data/`` on the remote tier (a remote database holds only tables)."""
        if self.tier == "file":
            return os.path.splitext(self.address)[0] + ".contracts.json"
        if self.tier == "object":
            return f"{self.address}/{OBJECT_CERTIFICATE}"
        return os.path.join(self.root, "data", "remote_warehouse.contracts.json")

    def describe(self) -> dict:
        """The tier and where it is, for people. Never a credential."""
        return {"tier": self.tier, "location": self.address}

    # ── ${VAR} resolution, as connections/*.yaml does it ──────────────────

    def _option(self, key: str) -> Optional[str]:
        from tracebi.project_credentials import CredentialError, Missing, expand

        raw = dict(self.options).get(key)
        if raw is None:
            return None
        try:
            return expand(raw, self.root)[0]
        except Missing as exc:
            raise WarehouseConfigError(
                f"{self.source or 'tracebi.yaml'}: warehouse.{key}: environment "
                f"variable {exc.name} is not set; set it in the environment or in "
                f"{os.path.join(self.root, '.env')}") from None
        except CredentialError as exc:
            raise WarehouseConfigError(
                f"{self.source or 'tracebi.yaml'}: warehouse.{key}: {exc}") from None

    # ── Connections ───────────────────────────────────────────────────────

    def connect(self, write: bool = False):
        """An UNLOCKED DuckDB connection in which the warehouse's tables
        resolve by their plain names: the transform side (``write()``, the
        sink contracts) and the connector's own reads. The project's
        ``engine`` limits apply (limits are not a lock). Not for answering a
        reader: that is :func:`tracebi.model.engine.query_connection`."""
        import duckdb

        if self.tier == "file":
            if write:
                os.makedirs(os.path.dirname(self.address) or ".", exist_ok=True)
            con = duckdb.connect(self.address, read_only=not write)
        else:
            con = duckdb.connect(":memory:")
        try:
            apply_limits(con, self.root)
            if self.tier == "object":
                self._prepare(con, install=True)
                if write and not self.is_url:
                    os.makedirs(self.address, exist_ok=True)
                if not write:
                    self._create_views(con, "main")
            elif self.tier == "remote":
                con.execute(self._attach_sql("wh0", read_only=not write))
                con.execute("USE wh0")
        except BaseException:
            con.close()
            raise
        return con

    def attach(self, con, alias: str) -> list[str]:
        """Make the warehouse the catalog *alias* of a query connection that
        is about to be locked; return the files the lock must still allow.

        File and remote tiers attach READ_ONLY, so nothing needs allowing. The
        object tier attaches an empty in-memory catalog and defines one view
        per Parquet file in it; a locked connection reads only the files
        returned here (``allowed_paths``), and the engine refuses ``COPY`` and
        ``ATTACH`` on such a connection, since an allowed path is writable."""
        if self.tier == "file":
            con.execute(f"ATTACH {_lit(self.address)} AS {_ident(alias)} (READ_ONLY)")
            return []
        if self.tier == "remote":
            con.execute(self._attach_sql(alias, read_only=True))
            return []
        self._prepare(con, install=False)
        con.execute(f"ATTACH ':memory:' AS {_ident(alias)}")
        return self._create_views(con, f"{_ident(alias)}.main")

    def _attach_sql(self, alias: str, read_only: bool) -> str:
        """``ATTACH`` for the remote tier: the location as written, or the
        database of the ``connections/<name>.yaml`` (type duckdb) it names,
        whose ``${VAR}`` resolves now, as that connection's own would."""
        from tracebi.connections import connection_file, load_connection

        target = self.location
        declared = connection_file(self.location, self.root) \
            if "/" not in self.location and ":" not in self.location else None
        if declared is not None:
            conn = load_connection(declared, self.root)
            if conn._decl.ctype != "duckdb":
                raise WarehouseConfigError(
                    f"{self.source or 'tracebi.yaml'}: warehouse.location names "
                    f"connections/{declared.name}, a {conn._decl.ctype} connection; "
                    f"the remote tier attaches a DuckDB database (a duckdb "
                    f"connection, md:…, or a path)")
            target = conn.database
        suffix = " (READ_ONLY)" if read_only else ""
        return f"ATTACH {_lit(target)} AS {_ident(alias)}{suffix}"

    def _prepare(self, con, install: bool) -> None:
        """Object tier on remote storage: httpfs and the secret. A query
        connection only LOADs (the extension is pre-installed, as the Docker
        image does); a transform connection may INSTALL it once."""
        if not self.is_url:
            return
        import duckdb

        try:
            con.execute("LOAD httpfs")
        except duckdb.Error as exc:
            if not install:
                raise WarehouseConfigError(
                    "the object tier reads through DuckDB's httpfs extension, "
                    "which is not installed here; run a transform once (it "
                    "installs it) or: python -c \"import duckdb; "
                    "duckdb.connect().execute('INSTALL httpfs')\"") from exc
            try:
                con.execute("INSTALL httpfs")
                con.execute("LOAD httpfs")
            except duckdb.Error as exc2:
                raise WarehouseConfigError(
                    f"the object tier needs DuckDB's httpfs extension and it could "
                    f"not be installed ({exc2}); on an air-gapped machine copy it "
                    f"into ~/.duckdb/extensions") from exc2
        con.execute(self.secret_sql())

    def secret_sql(self) -> str:
        """``CREATE TEMPORARY SECRET`` for the prefix, from the resolved fields.
        Scoped to the prefix, held by this connection only, never persisted."""
        scheme = urlsplit(self.address).scheme
        parts = [f"TYPE {'gcs' if scheme in ('gs', 'gcs') else 's3'}"]
        for key, name in (("key_id", "KEY_ID"), ("secret", "SECRET"),
                          ("region", "REGION"), ("url_style", "URL_STYLE")):
            value = self._option(key)
            if value is not None:
                parts.append(f"{name} {_lit(value)}")
        endpoint = self._option("endpoint")
        if endpoint is not None:
            split = urlsplit(endpoint if "://" in endpoint else f"https://{endpoint}")
            parts.append(f"ENDPOINT {_lit(split.netloc)}")
            parts.append(f"USE_SSL {'false' if split.scheme == 'http' else 'true'}")
        parts.append(f"SCOPE {_lit(self.address + '/')}")
        return f"CREATE OR REPLACE TEMPORARY SECRET tracebi_warehouse ({', '.join(parts)})"

    def _files(self, con) -> list[str]:
        """The Parquet files under the prefix, one per table."""
        rows = con.execute(
            f"SELECT file FROM glob({_lit(self.address + '/*.parquet')}) ORDER BY file"
        ).fetchall()
        return [str(r[0]) for r in rows]

    def _create_views(self, con, schema: str) -> list[str]:
        files = self._files(con)
        for path in files:
            table = os.path.basename(urlsplit(path).path if self.is_url else path)[:-len(".parquet")]
            con.execute(f"CREATE OR REPLACE VIEW {schema}.{_ident(table)} AS "
                        f"SELECT * FROM read_parquet({_lit(path)})")
        return files

    def exists(self) -> bool:
        """Is there anything to read yet?"""
        if self.tier == "file":
            return os.path.isfile(self.address)
        if self.tier == "object" and not self.is_url:
            return os.path.isdir(self.address) and any(
                n.endswith(".parquet") for n in os.listdir(self.address))
        try:
            con = self.connect()
        except Exception:  # noqa: BLE001 — unreachable is "not there", here
            return False
        try:
            return bool(self.tier == "remote" or self._files(con))
        finally:
            con.close()

    # ── Versions: what a silent rewrite changes ───────────────────────────

    def stamp(self) -> Optional[tuple]:
        """A key that changes whenever any table is rewritten: each file's size
        and modification time. None on the remote tier, which cannot say."""
        if self.tier == "remote":
            return None
        if self.tier == "file":
            out = []
            for p in (self.address, self.address + ".wal"):
                try:
                    st = os.stat(p)
                    out.append((st.st_mtime_ns, st.st_size))
                except OSError:
                    out.append(None)
            return tuple(out)
        if not self.is_url:
            try:
                names = sorted(n for n in os.listdir(self.address) if n.endswith(".parquet"))
            except OSError:
                return ()
            out = []
            for n in names:
                try:
                    st = os.stat(os.path.join(self.address, n))
                except OSError:
                    continue
                out.append((n, st.st_mtime_ns, st.st_size))
            return tuple(out)
        con = self.connect()
        try:
            return tuple(con.execute(
                f"SELECT filename, size, CAST(last_modified AS VARCHAR) "
                f"FROM read_blob({_lit(self.address + '/*.parquet')}) ORDER BY filename"
            ).fetchall())
        finally:
            con.close()

    def object_version(self, table: str) -> dict:
        """Object tier: what the certificate records about *table*'s file so a
        rewrite reads stale. ``etag`` when the store gives one (a signed HEAD
        on s3:// and gs://), else ``None``; always ``size`` and
        ``last_modified``; ``version_by`` says which of the two decides."""
        path = self.table_path(table)
        out: dict = {"path": path, "etag": None, "size": None, "last_modified": None}
        if not self.is_url:
            try:
                st = os.stat(path)
            except OSError:
                return {**out, "version_by": "missing"}
            out["size"] = st.st_size
            out["last_modified"] = datetime.fromtimestamp(
                st.st_mtime_ns / 1e9, timezone.utc).isoformat(timespec="microseconds")
            return {**out, "version_by": "size+last_modified"}
        con = self.connect()
        try:
            row = con.execute(
                f"SELECT size, CAST(last_modified AS VARCHAR) FROM read_blob({_lit(path)})"
            ).fetchone()
        except Exception:  # noqa: BLE001 — a missing object is a result
            row = None
        finally:
            con.close()
        if row is None:
            return {**out, "version_by": "missing"}
        out["size"], out["last_modified"] = int(row[0]), str(row[1])
        try:
            out["etag"] = self._head_etag(path)
        except Exception:  # noqa: BLE001 — no ETag is recorded as such
            out["etag"] = None
        return {**out, "version_by": "etag" if out["etag"] else "size+last_modified"}

    def _head_etag(self, path: str) -> Optional[str]:
        """The object's ETag from a HEAD request signed with AWS Signature V4
        (S3, R2, MinIO, and GCS's interoperable XML API with HMAC keys).
        Standard library only; the secret never leaves this process."""
        import urllib.request

        split = urlsplit(path)
        bucket, key = split.netloc, split.path.lstrip("/")
        region = self._option("region") or ("auto" if split.scheme != "s3" else "us-east-1")
        endpoint = self._option("endpoint")
        style = self._option("url_style") or ("path" if endpoint else "vhost")
        if endpoint:
            ep = urlsplit(endpoint if "://" in endpoint else f"https://{endpoint}")
            scheme, host = ep.scheme, ep.netloc
        elif split.scheme == "s3":
            scheme, host = "https", f"s3.{region}.amazonaws.com"
        else:
            scheme, host, style = "https", "storage.googleapis.com", "path"
        if style == "vhost":
            host, uri = f"{bucket}.{host}", "/" + quote(key, safe="/-_.~")
        else:
            uri = "/" + quote(f"{bucket}/{key}", safe="/-_.~")
        headers = {}
        key_id, secret = self._option("key_id"), self._option("secret")
        if key_id and secret:
            headers = _sigv4_headers("HEAD", host, uri, region, key_id, secret)
        req = urllib.request.Request(f"{scheme}://{host}{uri}", method="HEAD",
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — the configured store
            etag = resp.headers.get("ETag")
        return etag.strip() if etag else None

    # ── The certificate's bytes ───────────────────────────────────────────

    def read_text(self, path: str) -> Optional[str]:
        if not (self.is_url and "://" in path):
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except OSError:
                return None
        con = self.connect()
        try:
            row = con.execute(f"SELECT content FROM read_text({_lit(path)})").fetchone()
        except Exception:  # noqa: BLE001 — no certificate yet
            row = None
        finally:
            con.close()
        return None if row is None else str(row[0])

    def write_text(self, path: str, text: str) -> None:
        if not (self.is_url and "://" in path):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return
        # DuckDB writes the object: one CSV "row" with no quoting, no header
        # and a delimiter JSON never contains unescaped, so the bytes are the
        # text plus a newline.
        con = self.connect(write=True)
        try:
            con.execute(f"COPY (SELECT ? AS c) TO {_lit(path)} (FORMAT CSV, HEADER false, "
                        f"QUOTE '', ESCAPE '', DELIMITER '\x1f')", [text])
        finally:
            con.close()


def apply_limits(con, root: Optional[str] = None) -> None:
    """The project's ``engine`` limits (memory, threads, spill directory) on
    any DuckDB connection: the query connection and the transform's alike."""
    from tracebi.project_config import engine_settings

    settings = engine_settings(root)
    con.execute(f"SET memory_limit = {_lit(settings['memory_limit'])}")
    con.execute(f"SET threads = {int(settings['threads'])}")
    con.execute(f"SET temp_directory = {_lit(settings['temp_directory'])}")


def _sigv4_headers(method: str, host: str, uri: str, region: str,
                   key_id: str, secret: str, service: str = "s3") -> dict:
    """AWS Signature Version 4 headers for a request with an empty body."""
    now = datetime.now(timezone.utc)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload = hashlib.sha256(b"").hexdigest()
    signed = "host;x-amz-content-sha256;x-amz-date"
    canonical = "\n".join([
        method, uri, "",
        f"host:{host}\nx-amz-content-sha256:{payload}\nx-amz-date:{amz_date}\n",
        signed, payload])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    key = ("AWS4" + secret).encode()
    for part in (day, region, service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return {"x-amz-date": amz_date, "x-amz-content-sha256": payload,
            "Authorization": f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, "
                             f"SignedHeaders={signed}, Signature={signature}"}
