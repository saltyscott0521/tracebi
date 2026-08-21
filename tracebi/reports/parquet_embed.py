"""Parquet embed transport for the artifact data layer.

The artifact embeds a figure's data as **Parquet** — compact (≈8–17× smaller
than the same CSV), and the format the client-side worker engine decodes in the
browser. See ``docs/large-detail-artifacts.md``.

The receipt is **unchanged** by this. The fingerprint is still the frame's
content triple — ``{columns, dtypes, csv}`` via
:func:`tracebi.model.dataset.frame_fingerprint` — and a frame written here and
read back has the *identical* content fingerprint, so no ``fingerprint_algo``
change is needed and every receipt issued under the CSV embed stays valid.
``verify`` simply gains a decode step: read the embedded Parquet, then recompute
and compare the same triple it always did.

**Why pyarrow and not DuckDB.** That round-trip guarantee is the whole point, and
it is a property of the *writer*. pyarrow is Parquet's reference implementation
and records pandas' own dtype metadata in the file, so it restores a frame
exactly — timezone-aware timestamps keep their zone and unit, timedeltas keep
their unit, categoricals stay categorical. DuckDB is a database: it maps Parquet
through *its* SQL type system and hands pandas back a generically-converted
frame, which silently rewrote ``datetime64[ns, UTC]`` to
``datetime64[us, <the reader's local zone>]``. That made the recomputed
fingerprint differ from the recorded one — so an untouched artifact verified as
ALTERED, and *differently in different timezones*. Exactly the false accusation
``verify --file`` exists to prevent. DuckDB remains the warehouse and the query
engine; it is simply the wrong tool for preserving a pandas frame verbatim.
``tests/test_parquet_embed.py`` locks the round-trip across the dtypes that
broke, so a future swap cannot quietly reintroduce this.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd


def _require_pyarrow():
    """Import pyarrow, or fail loudly naming the extras key (invariant 4)."""
    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Reading or writing a Parquet-embedded artifact requires PyArrow. "
            "Install with: pip install 'tracebi[reports]'"
        ) from exc


def to_parquet_bytes(df: "pd.DataFrame") -> bytes:
    """Serialize *df* to Parquet (ZSTD) bytes for embedding.

    Parquet is transport only: the receipt is the frame's content fingerprint,
    which :func:`from_parquet_bytes` recovers exactly. The Parquet bytes
    themselves are never hashed (Parquet is not byte-reproducible across writers,
    and does not need to be).
    """
    _require_pyarrow()
    buf = io.BytesIO()
    # index=False: the fingerprint covers columns/dtypes/values, never the index.
    df.to_parquet(buf, engine="pyarrow", compression="zstd", index=False)
    return buf.getvalue()


def from_parquet_bytes(data: bytes) -> "pd.DataFrame":
    """Decode embedded Parquet *data* back to a DataFrame — verify's decode step.

    The recovered frame has the same content fingerprint as the original, so
    verify recomputes ``{columns, dtypes, csv}`` from it and matches the stored
    ``embedded_sha256`` without any special-casing.
    """
    _require_pyarrow()
    import pandas as pd

    return pd.read_parquet(io.BytesIO(data), engine="pyarrow")
