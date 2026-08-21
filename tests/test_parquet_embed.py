"""The Parquet embed transport preserves the content fingerprint exactly.

This is the load-bearing invariant behind switching the artifact's embedded data
from CSV to Parquet (docs/large-detail-artifacts.md, Phase 2/3): because the
receipt is the frame's ``{columns, dtypes, csv}`` fingerprint — not the embedded
bytes — a frame that round-trips through Parquet keeps the *same* fingerprint, so
no ``fingerprint_algo`` change is needed and receipts issued under the CSV embed
stay valid. If a future dtype ever fails to round-trip, this suite fails loudly
before the change reaches an artifact.
"""

import pandas as pd
import pytest

from tracebi.model.dataset import frame_fingerprint
from tracebi.reports.parquet_embed import from_parquet_bytes, to_parquet_bytes

# The dtypes a DataModel query result actually carries. Includes the trust-model
# audit's float edge cases (0.1+0.2, -0.0), nulls, and a realistic mixed frame.
_CASES = {
    "int64": pd.DataFrame({"x": pd.array([1, 2, 3], dtype="int64")}),
    "float64": pd.DataFrame({"x": [0.1 + 0.2, -0.0, 1 / 3]}),
    "float32": pd.DataFrame({"x": pd.array([1.5, 2.5, 3.5], dtype="float32")}),
    "object_str": pd.DataFrame({"x": ["a", "b", None]}),
    "bool": pd.DataFrame({"x": [True, False, True]}),
    "datetime": pd.DataFrame(
        {"x": pd.to_datetime(["2024-01-15", "2024-06-30", None])}
    ),
    # A zero-row result is real (a filter matching nothing) — every empty-column
    # dtype, including object/string, must keep its fingerprint.
    "empty": pd.DataFrame({
        "region": pd.Series([], dtype="object"),
        "rev": pd.Series([], dtype="float64"),
        "qty": pd.Series([], dtype="int64"),
        "flag": pd.Series([], dtype="bool"),
        "d": pd.Series([], dtype="datetime64[ns]"),
    }),
    "realistic": pd.DataFrame(
        {
            "region": ["North", "South", "East", None],
            "revenue": [1705495.22, 0.0, 1 / 3, 9999999.99],
            "qty": pd.array([10, 20, 30, 40], dtype="int64"),
            "order_date": pd.to_datetime(
                ["2024-01-15", "2024-06-30", "2024-12-31", None]
            ),
        }
    ),
}


@pytest.mark.parametrize("name", list(_CASES))
def test_parquet_roundtrip_preserves_fingerprint(name):
    df = _CASES[name]
    recovered = from_parquet_bytes(to_parquet_bytes(df))
    assert frame_fingerprint(recovered) == frame_fingerprint(df), (
        f"{name}: embedding as Parquet changed the content fingerprint — the "
        f"receipt would break. Round-trip is not lossless for this dtype."
    )


def test_row_order_is_preserved():
    # The fingerprint is order-dependent (rows in engine order); Parquet must not
    # reorder, or a correct receipt would read as ALTERED.
    df = pd.DataFrame({"k": ["z", "a", "m", "b"], "v": [4, 1, 3, 2]})
    recovered = from_parquet_bytes(to_parquet_bytes(df))
    assert list(recovered["k"]) == list(df["k"])


def test_parquet_is_more_compact_than_csv_for_wide_data():
    # The reason for the switch: Parquet is the compact transport.
    df = pd.DataFrame(
        {"a": range(5000), "b": [i * 1.5 for i in range(5000)], "c": ["xyz"] * 5000}
    )
    assert len(to_parquet_bytes(df)) < len(df.to_csv(index=False).encode())


# ── verify path: a Parquet-embedded block checks out exactly like a CSV block ──

def _fp(triple):
    from tracebi.reports.embed import fingerprint_triple

    return fingerprint_triple(triple)


def test_parquet_block_verifies_like_the_csv_block():
    """embed_block_parquet + verify's decode branch recompute the SAME
    fingerprint as the CSV embed — so verify_file reads FILE INTACT."""
    from tracebi.reports.embed import embed_block, embed_block_parquet, stamp_frame
    from tracebi.verify import _extract_data_blocks

    stamped = stamp_frame(_CASES["realistic"], name="revenue")
    csv_blocks = _extract_data_blocks(embed_block(stamped))
    pq_blocks = _extract_data_blocks(embed_block_parquet(stamped))
    assert len(csv_blocks) == len(pq_blocks) == 1
    assert csv_blocks[0][0] == pq_blocks[0][0] == "revenue"
    assert _fp(pq_blocks[0][1]) == _fp(csv_blocks[0][1]) == stamped.fingerprint


def test_tampered_parquet_data_is_caught():
    """A changed value in a Parquet block recomputes to a different fingerprint
    than the binding recorded — verify_file would read FILE ALTERED."""
    from tracebi.reports.embed import embed_block_parquet, stamp_frame
    from tracebi.verify import _extract_data_blocks

    original = stamp_frame(_CASES["realistic"], name="revenue")
    tampered = _CASES["realistic"].copy()
    tampered.loc[0, "revenue"] = 999999.99
    blocks = _extract_data_blocks(
        embed_block_parquet(stamp_frame(tampered, name="revenue"))
    )
    assert _fp(blocks[0][1]) != original.fingerprint


def test_undecodable_parquet_block_is_not_a_pass():
    """A present-but-corrupt Parquet block is skipped (its binding reads
    MISSING → a failure), never silently accepted."""
    import base64

    from tracebi.reports.embed import embed_json
    from tracebi.verify import _extract_data_blocks

    bad = base64.b64encode(b"not a parquet file").decode("ascii")
    html = embed_json(
        {"name": "x", "format": "parquet", "parquet_b64": bad}, "tracebi-data-x"
    )
    assert _extract_data_blocks(html) == []
