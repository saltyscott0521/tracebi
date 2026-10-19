"""``tracebi.yaml``: the project's own settings file, at the project root.

One reader, cached per path (and re-read when the file changes), so every
caller sees the same answer. Today it holds one block, ``engine``, the limits
of the DuckDB connections that answer model queries
(:mod:`tracebi.model.engine`)::

    engine:
      memory_limit: 1GB          # past it, DuckDB spills to temp_directory
      threads: 4                 # default: min(4, CPUs)
      temp_directory: data/.duckdb-tmp   # relative to the project root
      query_timeout_s: 30        # Explore, Ask and agent queries stop here

A missing file, or a missing key, means the default. A malformed file is an
error naming the file, never a silent default: a limit an operator wrote must
be the limit that applies.

Reference: ``docs/reference/tracebi-yaml.md``.
"""

from __future__ import annotations

import os
import re
import threading
from typing import Any, Optional

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
