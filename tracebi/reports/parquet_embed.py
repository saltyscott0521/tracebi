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


#: Decode bounds for untrusted Parquet. ``verify --file`` runs against a file
#: someone was *sent*, so its embedded data is attacker-controllable: Parquet is
#: compressed and columnar, so a small block can describe an enormous frame, and
#: an unbounded decode would let a tiny .html exhaust the checker's memory. These
#: caps sit far above any artifact a browser could render (the artifact is itself
#: bounded by what the page can hold) and are checked against the file's own
#: metadata, before any data is read.
MAX_DECODE_ROWS = 50_000_000
MAX_DECODE_UNCOMPRESSED_BYTES = 2 * 1024**3  # 2 GiB


class ParquetTooLarge(ValueError):
    """An embedded Parquet block declares more data than we will decode."""


def from_parquet_bytes(data: bytes) -> "pd.DataFrame":
    """Decode embedded Parquet *data* back to a DataFrame — verify's decode step.

    The recovered frame has the same content fingerprint as the original, so
    verify recomputes ``{columns, dtypes, csv}`` from it and matches the stored
    ``embedded_sha256`` without any special-casing.

    Refuses a block whose own metadata declares more than :data:`MAX_DECODE_ROWS`
    rows or :data:`MAX_DECODE_UNCOMPRESSED_BYTES` of data, so a hostile file
    cannot turn the checker into a decompression bomb.
    """
    _require_pyarrow()
    import pandas as pd
    import pyarrow.parquet as pq

    buf = io.BytesIO(data)
    # Read the footer only: this is metadata, not the column data itself.
    md = pq.ParquetFile(buf).metadata
    if md.num_rows > MAX_DECODE_ROWS:
        raise ParquetTooLarge(
            f"embedded data declares {md.num_rows:,} rows, above the "
            f"{MAX_DECODE_ROWS:,} decode limit"
        )
    total = sum(md.row_group(i).total_byte_size for i in range(md.num_row_groups))
    if total > MAX_DECODE_UNCOMPRESSED_BYTES:
        raise ParquetTooLarge(
            f"embedded data declares {total:,} uncompressed bytes, above the "
            f"{MAX_DECODE_UNCOMPRESSED_BYTES:,} decode limit"
        )
    buf.seek(0)
    return pd.read_parquet(buf, engine="pyarrow")
