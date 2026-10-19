"""``tracebi.yaml``: the project's own settings file, at the project root.

One reader, cached per path (and re-read when the file changes), so every
caller sees the same answer. It holds two blocks: ``engine``, the limits
of the DuckDB connections that answer model queries
(:mod:`tracebi.model.engine`)::

    engine:
      memory_limit: 1GB          # past it, DuckDB spills to temp_directory
      threads: 4                 # default: min(4, CPUs)
      temp_directory: data/.duckdb-tmp   # relative to the project root
      query_timeout_s: 30        # Explore, Ask and agent queries stop here

and ``warehouse``, where phase ① sinks and phase ② reads (:func:`warehouse`,
:mod:`tracebi.warehouse`)::

    warehouse:
      tier: object               # file (default) | object | remote
      location: s3://bucket/project
      key_id: ${AWS_ACCESS_KEY_ID}
      secret: ${AWS_SECRET_ACCESS_KEY}

A missing file, or a missing key, means the default. A malformed file is an
error naming the file, never a silent default: a limit an operator wrote must
be the limit that applies.

Reference: ``docs/reference/tracebi-yaml.md``.
"""

from __future__ import annotations

import os
import re
import threading
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tracebi.warehouse import SinkTarget, Warehouse

#: The file name, at the project root (the working directory).
CONFIG_FILE = "tracebi.yaml"

_ENGINE_KEYS = {"memory_limit", "threads", "temp_directory", "query_timeout_s"}
# DuckDB's own size spelling: a number and a unit (1GB, 512MB, 2GiB).
_SIZE = re.compile(r"^\s*\d+(\.\d+)?\s*(B|KB|MB|GB|TB|KiB|MiB|GiB|TiB)\s*$", re.I)

_cache: dict[str, tuple[Any, dict]] = {}
_lock = threading.Lock()


def config_path(project_root: Optional[str] = None) -> str:
    return os.path.join(os.path.abspath(project_root or os.getcwd()), CONFIG_FILE)


def read_config(project_root: Optional[str] = None) -> dict:
    """The parsed ``tracebi.yaml`` of *project_root* (default: the working
    directory), or ``{}`` when there is none."""
    path = config_path(project_root)
    try:
        st = os.stat(path)
    except OSError:
        return {}
    stamp = (st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _cache.get(path)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    import yaml

    with open(path, encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    with _lock:
        _cache[path] = (stamp, data)
    return data


def engine_settings(project_root: Optional[str] = None) -> dict:
    """The ``engine`` block with every default filled in and every value checked.

    ``{"memory_limit": str, "threads": int, "temp_directory": abs path,
    "query_timeout_s": float}``.
    """
    root = os.path.abspath(project_root or os.getcwd())
    raw = read_config(root).get("engine") or {}
    where = config_path(root)
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: 'engine' must be a mapping")
    unknown = sorted(set(raw) - _ENGINE_KEYS)
    if unknown:
        raise ValueError(
            f"{where}: unknown engine key(s) {unknown}; known: {sorted(_ENGINE_KEYS)}")

    memory = str(raw.get("memory_limit", "1GB"))
    if not _SIZE.match(memory):
        raise ValueError(f"{where}: engine.memory_limit {memory!r} is not a size like 1GB")
    threads = raw.get("threads", min(4, os.cpu_count() or 1))
    if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
        raise ValueError(f"{where}: engine.threads must be a whole number of at least 1")
    temp = str(raw.get("temp_directory", os.path.join("data", ".duckdb-tmp")))
    if not os.path.isabs(temp):
        temp = os.path.join(root, temp)
    timeout = raw.get("query_timeout_s", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError(f"{where}: engine.query_timeout_s must be a number of seconds above 0")
    return {"memory_limit": memory.strip(), "threads": threads,
            "temp_directory": temp, "query_timeout_s": float(timeout)}


def warehouse(project_root: Optional[str] = None) -> "Warehouse":
    """The ``warehouse`` block, checked: where phase ① sinks and phase ② reads.

    No block means the file tier at ``data/warehouse.duckdb``. Every value is
    a string; any but ``tier`` and ``location`` may be ``${VAR}`` (the whole
    value), resolved from the environment, then the project's ``.env``, when
    a connection is made, as ``connections/*.yaml`` does it. ``key_id`` and
    ``secret`` MUST be: a literal credential is refused, naming the key. The
    tier and location stay literal so loading a model never reads the
    environment. See :mod:`tracebi.warehouse`.
    """
    from urllib.parse import urlsplit

    from tracebi.connections import _REF, _url_problem
    from tracebi.warehouse import (
        DEFAULT_LOCATION, OBJECT_KEYS, OBJECT_SCHEMES, SECRET_KEYS, TIERS, Warehouse,
    )

    root = os.path.abspath(project_root or os.getcwd())
    raw = read_config(root).get("warehouse")
    where = config_path(root)
    if raw is None:
        return Warehouse("file", DEFAULT_LOCATION, root)
    if not isinstance(raw, dict):
        raise ValueError(f"{where}: 'warehouse' must be a mapping")
    unknown = sorted(set(raw) - {"tier", "location", *OBJECT_KEYS})
    if unknown:
        raise ValueError(f"{where}: unknown warehouse key(s) {unknown}; known: "
                         f"{sorted({'tier', 'location', *OBJECT_KEYS})}")
    for key, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{where}: warehouse.{key} must be a non-empty string")
    tier = raw.get("tier", "file")
    if tier not in TIERS:
        raise ValueError(f"{where}: warehouse.tier must be one of {', '.join(TIERS)}, got {tier!r}")
    if tier != "file" and "location" not in raw:
        raise ValueError(f"{where}: warehouse.location is required for the {tier} tier")
    location = raw.get("location", DEFAULT_LOCATION)
    if "${" in location:
        raise ValueError(f"{where}: warehouse.location must be written out, not "
                         f"${{VAR}}: a model reads it when it loads. Put a "
                         f"credential in key_id / secret, or for the remote tier in "
                         f"a connections/<name>.yaml and name that here")
    scheme = urlsplit(location).scheme
    if tier == "object" and "://" in location and scheme not in (*OBJECT_SCHEMES, "file"):
        raise ValueError(f"{where}: warehouse.location for the object tier is s3://, "
                         f"gs:// or a local directory, got {location!r}")
    if tier == "file" and "://" in location:
        raise ValueError(f"{where}: warehouse.location for the file tier is a path to "
                         f"a .duckdb file; {location!r} belongs to the object or remote tier")
    if tier == "remote" and (why := _url_problem(location)) and "credential" in why:
        raise ValueError(f"{where}: warehouse.location {why.split(';')[0]}; keep it "
                         f"in a connections/<name>.yaml and name that connection here")
    options = {k: v for k, v in raw.items() if k in OBJECT_KEYS}
    if options and tier != "object":
        raise ValueError(f"{where}: warehouse.{sorted(options)[0]} applies to the object "
                         f"tier only (this one is {tier})")
    for key, value in options.items():
        if _REF.fullmatch(value):
            continue
        if "${" in value:
            raise ValueError(f"{where}: warehouse.{key}: ${{VAR}} must be the whole "
                             f"value ([A-Z_][A-Z0-9_]*), got {value!r}")
        if key in SECRET_KEYS:
            raise ValueError(f"{where}: warehouse.{key} is a credential; write it as "
                             f"${{ENV_VAR}} and put the value in .env, never in this file")
        if key == "url_style" and value not in ("path", "vhost"):
            raise ValueError(f"{where}: warehouse.url_style must be path or vhost, got {value!r}")
    return Warehouse(tier, location, root, tuple(sorted(options.items())), where)


def sink_target(project_root: Optional[str] = None) -> "SinkTarget":
    """What a transform writes to: the DuckDB file's path on the file tier, the
    ``s3://…`` (or local directory) prefix on the object tier, the attach
    string on the remote tier. A string that remembers its warehouse, so
    ``DuckDBConnector(name, database=sink_target(root)).write(df, table)`` and
    ``contract(name, warehouse=sink_target(root))`` follow the tier.

    SQL transforms (S-3) substitute ``{{ sink }}`` with ``str(sink_target())``
    and write through ``sink_target().warehouse.connect(write=True)``.
    """
    return warehouse(project_root).sink
