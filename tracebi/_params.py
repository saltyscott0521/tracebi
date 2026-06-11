"""
Request parameters — declare defaults in a script, override at run time.

A request script declares its parameters in one line:

    from tracebi import request_params
    params = request_params(period="Q2 2024", top_n=10)

Run standalone (``python requests/x.py``) it returns the defaults. When the
script is executed by ``tracebi run --param`` or the web API, overrides are
injected via a context variable and merged over the defaults, coerced to the
type of each default. Unknown override names raise loudly.

Defaults must be literals (str/int/float/bool) — that keeps them statically
discoverable, so the web UI can render a parameter form without executing
the script (see :func:`discover_params`).
"""

from __future__ import annotations

import ast
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Optional, Union

_overrides: ContextVar[Optional[dict]] = ContextVar(
    "tracebi_request_param_overrides", default=None
)


def _coerce(value: Any, default: Any) -> Any:
    """Coerce a (typically string) override to the type of its default."""
    if isinstance(value, type(default)) and not isinstance(default, bool):
        return value
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("true", "1", "yes", "on"):
            return True
        if str(value).strip().lower() in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"Cannot interpret {value!r} as a boolean.")
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    return str(value)


def request_params(**defaults: Any) -> dict[str, Any]:
    """
    Declare request parameters and return their effective values.

    Returns the defaults merged with any overrides injected by the runner
    (web API, ``tracebi run --param``). Overrides are coerced to the type
    of the corresponding default; unknown names raise ``ValueError``.
    """
    overrides = _overrides.get() or {}
    unknown = sorted(set(overrides) - set(defaults))
    if unknown:
        raise ValueError(
            f"Unknown request parameter(s): {', '.join(unknown)}. "
            f"Declared: {sorted(defaults)}"
        )
    merged = dict(defaults)
    for key, value in overrides.items():
        try:
            merged[key] = _coerce(value, defaults[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Parameter '{key}': cannot coerce {value!r} to "
                f"{type(defaults[key]).__name__}: {exc}"
            ) from exc
    return merged


def set_param_overrides(params: Optional[dict]):
    """Set overrides for the current context; returns a reset token."""
    return _overrides.set(dict(params) if params else None)


def reset_param_overrides(token) -> None:
    _overrides.reset(token)


def discover_params(path: Union[str, Path]) -> list[dict]:
    """
    Statically extract a script's declared parameters without executing it.

    Finds the first ``request_params(...)`` call and returns its literal
    keyword defaults as ``[{"name", "default", "type"}, ...]``. Returns an
    empty list when the script declares no parameters (or uses non-literal
    defaults, which this deliberately does not evaluate).
    """
    path = Path(path)
    if path.suffix == ".ipynb":
        from tracebi._notebook import notebook_to_source
        source = notebook_to_source(path)
    else:
        source = path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == "request_params")
                or (isinstance(node.func, ast.Attribute)
                    and node.func.attr == "request_params")
            )
        ):
            out = []
            for kw in node.keywords:
                if kw.arg is None:
                    continue  # **kwargs — not statically discoverable
                try:
                    default = ast.literal_eval(kw.value)
                except (ValueError, SyntaxError):
                    continue
                out.append({
                    "name":    kw.arg,
                    "default": default,
                    "type":    type(default).__name__,
                })
            return out
    return []
