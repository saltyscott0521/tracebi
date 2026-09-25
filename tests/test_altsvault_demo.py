"""
The demo app's AltsVault pipeline: pull → transform → build.

Everything runs offline against small fixture CSVs, in a subprocess: importing
any part of tracebi.web.demo_app wires the whole demo registry, and that must
not leak into this test process (see test_phase5's serve-isolation test).
"""

import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytest.importorskip("duckdb")


def _run(tmp_path, code: str, env_extra=None) -> dict:
    env = {**os.environ, "TRACEBI_ALTSVAULT_DIR": str(tmp_path / "av")}
    env.pop("ALTSVAULT_API_KEY", None)
    env.update(env_extra or {})
    out = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=240,
    )
    assert out.returncode == 0, out.stdout[-3000:] + out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def _fixture(tmp_path):
    """Two funds with two reporting periods each; only the latest should land."""
    raw = tmp_path / "av" / "inputs"
    raw.mkdir(parents=True)
    old, new = "2025-12-31T00:00:00.000Z", "2026-03-31T00:00:00.000Z"
    positions = []
    for slug, fvs in (("fund-a", [100.0, 50.0]), ("fund-b", [80.0])):
        for period, bump in ((old, 0.9), (new, 1.0)):
            for i, fv in enumerate(fvs):
                positions.append({
                    "slug": slug, "period_end": period, "position_seq": i,
                    "issuer_key": f"iss-{slug}-{i}" if i else None,
                    "mark_band": "UNSTRESSED" if i == 0 else None,
                    "seniority": "FIRST_LIEN" if i == 0 else None,
                    "is_debt_proxy": i == 0, "fair_value": fv * bump,
                    "cost": "100.000000000000", "mark_cost": str(fv * bump / 100),
                    "principal": 100.0, "recon_status": "RECONCILED"})
    pm = pd.DataFrame(positions)
    pm.to_csv(raw / "position_marks.csv", index=False)
    fm = (pm.groupby(["slug", "period_end"]).agg(book_fv=("fair_value", "sum"),
                                                 positions_counted=("position_seq", "count"))
          .reset_index())
    fm = fm.assign(fund_name=fm["slug"].str.upper(), recon_status="RECONCILED",
                   is_partial=False, marked_fv=fm["book_fv"], positions_excluded=0,
                   fv_below_watch=0.0, fv_below_stress=0.0, fv_below_deep=0.0)
    fm.to_csv(raw / "fund_marks.csv", index=False)
    pd.DataFrame({"slug": ["fund-a", "fund-b"], "structure": ["BDC", "BDC"],
                  "asset_class": ["credit", "credit"], "months_stale": [1, 2]}
                 ).to_csv(raw / "quality_fund_completeness.csv", index=False)
    pd.DataFrame({"slug": ["fund-a", "fund-b"], "crowded_share": [0.3, 0.6],
                  "unique_share": [0.7, 0.4], "total_issuers": [2, 1]}
                 ).to_csv(raw / "fund_crowding.csv", index=False)
    pd.DataFrame({"issuer_key": ["iss-fund-a-1"], "slug": ["fund-a"], "period_end": [new],
                  "display_name": ["Issuer One"], "industry": ["Software"]}
                 ).to_csv(raw / "issuer_fund_exposure.csv", index=False)


def test_the_pipeline_is_pull_then_transform_then_build(tmp_path):
    out = _run(tmp_path, """
        import json
        from tracebi.web.demo_app.altsvault.pipeline import runner
        print(json.dumps({l["name"]: l["depends_on"] for l in runner.layers()}))
    """)
    assert out == {"pull": None, "transform": "pull", "build": "transform"}


def test_transform_keeps_each_funds_latest_period_and_the_report_builds(tmp_path):
    _fixture(tmp_path)
    out = _run(tmp_path, """
        import json, os
        from tracebi.web.demo_app.altsvault.pipeline import runner, model
        runner.run("transform")
        runner.run("build")
        facts = model.load("fact_fund_marks").to_pandas()
        html = os.path.join("output", "altsvault", "credit_marks.html")
        print(json.dumps({
            "periods": sorted({str(p)[:10] for p in facts["period_end"]}),
            "funds": len(facts),
            "built": os.path.isfile(html) and os.path.isfile(html + ".manifest.json"),
            "status": [runner.run_history(n, limit=1)[0]["status"]
                       for n in ("transform", "build")],
        }))
    """)
    assert out["periods"] == ["2026-03-31"]      # the older period is dropped
    assert out["funds"] == 2
    assert out["built"] is True
    assert out["status"] == ["success", "success"]


def test_a_recent_pull_is_reused_without_the_api(tmp_path):
    raw = tmp_path / "av" / "inputs"
    raw.mkdir(parents=True)
    exports = ["position_marks", "fund_marks", "quality_fund_completeness",
               "fund_crowding", "issuer_fund_exposure"]
    fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
    (raw / "_pull_manifest.json").write_text(json.dumps({
        "pulled_at": fresh.isoformat(timespec="seconds"),
        "exports": {e: {"rows": 3} for e in exports}}))
    out = _run(tmp_path, """
        import json
        from tracebi.web.demo_app.altsvault.pull import pull
        print(json.dumps({"reused": pull()["reused"]}))
    """)
    assert out == {"reused": True}             # no key set, and no error


def test_a_stale_pull_without_a_key_says_what_is_missing(tmp_path):
    out = _run(tmp_path, """
        import json
        from tracebi.web.demo_app.altsvault.pull import pull
        try:
            pull()
            print(json.dumps({"error": None}))
        except RuntimeError as exc:
            print(json.dumps({"error": str(exc)}))
    """)
    assert "ALTSVAULT_API_KEY" in out["error"]
