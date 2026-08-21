"""The Parquet embed transport preserves the content fingerprint exactly.

This is the load-bearing invariant behind switching the artifact's embedded data
from CSV to Parquet (docs/large-detail-artifacts.md, Phase 2/3): because the
receipt is the frame's ``{columns, dtypes, csv}`` fingerprint — not the embedded
bytes — a frame that round-trips through Parquet keeps the *same* fingerprint, so
no ``fingerprint_algo`` change is needed and receipts issued under the CSV embed
stay valid. If a future dtype ever fails to round-trip, this suite fails loudly
before the change reaches an artifact.
"""

from decimal import Decimal

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
    # ── The dtypes that a DuckDB-based round-trip silently rewrote ──────────
    # Each of these turned an untouched artifact into a FILE ALTERED verdict
    # (tz-aware also made the verdict depend on the VERIFIER'S timezone). They
    # are pinned here so a future writer swap cannot quietly reintroduce it.
    "tz_aware_utc": pd.DataFrame(
        {"t": pd.to_datetime(["2024-01-15 10:00", "2024-06-30 12:00"], utc=True)}
    ),
    "tz_aware_zone": pd.DataFrame(
        {"t": pd.to_datetime(["2024-01-15 10:00", "2024-06-30 12:00"]).tz_localize(
            "US/Eastern"
        )}
    ),
    "timedelta": pd.DataFrame({"d": pd.to_timedelta(["1 days", "2 days", "3 days"])}),
    "category": pd.DataFrame({"c": pd.Categorical(["a", "b", "a", None])}),
    "nullable_int": pd.DataFrame({"x": pd.array([1, None, 3], dtype="Int64")}),
    "big_int64": pd.DataFrame(
        {"x": pd.array([2**53 + 1, 2**53 + 3, -(2**53) - 1], dtype="int64")}
    ),
    "decimal": pd.DataFrame(
        {"m": [Decimal("1234567.89"), Decimal("0.07"), Decimal("-42.42")]}
    ),
    "unicode_and_quotes": pd.DataFrame(
        {"s": ['a,b', 'he said "hi"', "line\nbreak", "café ☕", None]}
    ),
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


# ── automatic format selection (one format per artifact, chosen by size) ──────

def _frame(rows):
    return pd.DataFrame({
        "region": ["North", "South", "East", "West"] * (rows // 4),
        "revenue": [1705495.22, 250000.0, 99999.99, 42000.5] * (rows // 4),
    })


def test_small_report_stays_csv_and_ships_no_engine():
    """A KPI-shaped dashboard must not pay megabytes for an engine: below the
    crossover the CSV artifact is genuinely smaller."""
    from tracebi.reports.embed import (
        EMBED_FORMAT_CSV, choose_embed_format, data_blocks_html, stamp_frame,
    )
    from tracebi.reports.stack import stack_tail

    stamped = [stamp_frame(_frame(40), name="d")]
    assert choose_embed_format(stamped) == EMBED_FORMAT_CSV
    blocks = data_blocks_html(stamped)
    assert '"csv"' in blocks
    assert 'id="tracebi-engine-worker"' not in stack_tail(libs=(),
                                                          data_blocks_html=blocks)


def test_large_report_switches_to_parquet_and_gets_smaller():
    """Past the crossover Parquet wins outright — the engine pays for itself."""
    from tracebi.reports.embed import (
        EMBED_FORMAT_PARQUET, choose_embed_format, data_blocks_html, stamp_frame,
    )
    from tracebi.reports.stack import stack_tail

    stamped = [stamp_frame(_frame(400_000), name="d")]
    assert choose_embed_format(stamped) == EMBED_FORMAT_PARQUET
    blocks = data_blocks_html(stamped)
    assert '"parquet"' in blocks
    # smaller than the CSV it replaced, and the engine now ships
    assert len(blocks) < len(stamped[0].triple["csv"])
    assert 'id="tracebi-engine-worker"' in stack_tail(libs=(),
                                                      data_blocks_html=blocks)


def test_one_format_per_artifact_never_a_mix():
    """The engine is a per-file cost, so once any binding justifies it every
    block uses it — a file never carries both formats."""
    from tracebi.reports.embed import data_blocks_html, stamp_frame

    blocks = data_blocks_html([
        stamp_frame(_frame(400_000), name="big"),
        stamp_frame(_frame(8), name="tiny"),
    ])
    assert blocks.count('"format": "parquet"') == 2
    assert '"csv"' not in blocks


def test_format_choice_never_changes_the_receipt():
    """The whole point: transport is not trust. Both formats fingerprint the
    same, so crossing the threshold cannot make a report more or less
    verifiable."""
    from tracebi.reports.embed import embed_block, embedded_record, stamp_frame
    from tracebi.verify import _extract_data_blocks

    stamped = stamp_frame(_frame(400), name="d")
    expected = embedded_record(stamped)["embedded_sha256"]
    for fmt in ("csv", "parquet"):
        (_name, triple), = _extract_data_blocks(embed_block(stamped, fmt=fmt))
        assert _fp(triple) == expected


def test_undecodable_parquet_block_is_reported_not_dropped():
    """A present-but-corrupt Parquet block must be REPORTED as unreadable, never
    dropped: dropping lets a block the checker cannot read slip past every check
    as though it were not there. It is reported with a triple that can never
    match a recorded fingerprint, so the binding always fails."""
    import base64

    from tracebi.reports.embed import embed_json
    from tracebi.verify import _extract_data_blocks

    bad = base64.b64encode(b"not a parquet file").decode("ascii")
    html = embed_json(
        {"name": "x", "format": "parquet", "parquet_b64": bad}, "tracebi-data-x"
    )
    blocks = _extract_data_blocks(html)
    assert len(blocks) == 1 and blocks[0][0] == "x"
    assert _fp(blocks[0][1]) != "anything a real frame could hash to"


def test_a_block_carrying_both_formats_is_refused():
    """The forgery shape: the runtime draws from the Parquet payload while the
    hash would come from the inline CSV triple, so such a block displays one set
    of numbers and vouches for another. It must never verify."""
    import json as _json

    from tracebi.reports.embed import (
        embed_block, embed_block_parquet, embed_json, stamp_frame,
    )
    from tracebi.verify import _extract_data_blocks

    honest = stamp_frame(_CASES["realistic"], name="d")
    evil = _CASES["realistic"].copy()
    evil.loc[0, "revenue"] = 999_999.99

    def _payload(block):
        return _json.loads(block.split('">', 1)[1].rsplit("</script>", 1)[0])

    forged = _payload(embed_block(honest, fmt="csv"))          # legit triple
    forged["format"] = "parquet"                                # …but drawn from
    forged["parquet_b64"] = _payload(                           # attacker data
        embed_block_parquet(stamp_frame(evil, name="d")))["parquet_b64"]

    (_name, triple), = _extract_data_blocks(embed_json(forged, "tracebi-data-d"))
    assert _fp(triple) != honest.fingerprint


def test_unsafe_column_labels_fall_back_to_csv():
    """Parquet column names must be unique strings. A frame whose labels are not
    (a report.py pivot() yields integer labels; a careless join yields
    duplicates) must stay on CSV rather than come back with rewritten names — a
    changed fingerprint would read as a false FILE ALTERED."""
    from tracebi.reports.embed import (
        EMBED_FORMAT_CSV, choose_embed_format, stamp_frame,
    )

    big = 200_000
    int_labels = pd.DataFrame({1: range(big), 2: range(big)})
    dupes = pd.DataFrame(
        {"a": range(big), "b": range(big)}
    ).rename(columns={"b": "a"})

    for df in (int_labels, dupes):
        stamped = [stamp_frame(df, name="d")]
        # large enough that size alone would have chosen Parquet
        assert len(stamped[0].triple["csv"]) > 1_000_000
        assert choose_embed_format(stamped) == EMBED_FORMAT_CSV


def test_untrusted_parquet_decode_is_bounded():
    """verify --file runs on a file someone was SENT, so its embedded data is
    attacker-controllable: a small compressed block can declare an enormous
    frame. The decode must refuse from metadata, before reading any data."""
    import tracebi.reports.parquet_embed as pe

    data = pe.to_parquet_bytes(pd.DataFrame({"x": range(1000)}))
    original = pe.MAX_DECODE_ROWS
    try:
        pe.MAX_DECODE_ROWS = 10
        with pytest.raises(pe.ParquetTooLarge):
            pe.from_parquet_bytes(data)
    finally:
        pe.MAX_DECODE_ROWS = original
    # and a normal block still decodes
    assert len(pe.from_parquet_bytes(data)) == 1000


# ── The invariant that actually matters ───────────────────────────────────────
# Not "these dtypes round-trip" (three attempts to enumerate that missed cases),
# but: WHATEVER format is chosen, the receipt verifies. choose_embed_format
# proves the round-trip for the exact data in hand and falls back to CSV when it
# does not hold, so a false FILE ALTERED is impossible by construction — for
# dtypes nobody has thought of yet.

def _big(extra, n=400_000):
    base = {"region": ["North", "South", "East", "West"] * (n // 4),
            "rev": [1705495.22, 250000.0, 99999.99, 42000.5] * (n // 4)}
    base.update(extra)
    return pd.DataFrame(base)


_HOSTILE = {
    "string_categorical": {"c": pd.Categorical(["a", "b", "c", "d"] * 100_000)},
    "int_categorical": {"c": pd.Categorical([1, 2, 3, 4] * 100_000)},
    "object_of_ints": {"q": pd.Series([1, 2, 3, 4] * 100_000, dtype=object)},
    "object_with_none": {"q": pd.Series([1, None, 3, 4] * 100_000, dtype=object)},
    "datetime_seconds": {
        "d": pd.Series(pd.to_datetime(["2024-01-15"] * 400_000)).dt.as_unit("s")
    },
    "plain_int64": {"q": pd.array(list(range(4)) * 100_000, dtype="int64")},
    "all_null_column": {"q": pd.Series([None] * 400_000, dtype=object)},
    "bools": {"q": pd.Series([True, False, True, False] * 100_000)},
}


@pytest.mark.parametrize("name", list(_HOSTILE))
def test_whatever_format_is_chosen_the_receipt_verifies(name):
    from tracebi.reports.embed import (
        data_blocks_html, embedded_record, stamp_frame,
    )
    from tracebi.verify import _extract_data_blocks

    stamped = stamp_frame(_big(_HOSTILE[name]), name="d")
    (_n, triple), = _extract_data_blocks(data_blocks_html([stamped]))
    assert _fp(triple) == embedded_record(stamped)["embedded_sha256"], (
        f"{name}: a freshly built artifact would verify as FILE ALTERED — the "
        f"format choice must fall back to CSV when the round-trip does not "
        f"preserve the fingerprint."
    )
