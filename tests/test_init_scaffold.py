"""
The init scaffold is the product's first run — it must walk the three-phase
workflow end to end and finish with `tracebi verify` reading REPRODUCES.

These tests run the scaffolded project through subprocesses (the exact
commands the scaffolded README gives a new user), so they are hermetic: no
shared registry state with the rest of the suite.
"""

import compileall
import subprocess
import sys
from pathlib import Path

import pytest

from tracebi import cli

pytest.importorskip("duckdb")


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "tracebi.cli", *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


class TestInitScaffold:
    def test_init_creates_the_three_phase_layout(self, tmp_path):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        # M5 flip ledger: init no longer scaffolds requests/ — the
        # deprecated lane is not handed to new projects.
        for d in ("inputs", "transforms", "models", "reports",
                  "pipelines", "scheduled", "data", "output"):
            assert (proj / d).is_dir(), f"missing {d}/"
        assert not (proj / "requests").exists(), \
            "init must not scaffold the deprecated requests/ lane"
        assert (proj / "inputs" / "orders.csv").is_file()
        assert (proj / "transforms" / "sample_transform.py").is_file()
        assert (proj / "models" / "sample_model.py").is_file()
        # Round-2 flip: the sample report is an ARTIFACT PACKAGE — the one
        # report lane — not a legacy JSON spec.
        assert (proj / "reports" / "sample_dashboard" / "report.json").is_file()
        assert (proj / "reports" / "sample_dashboard" / "template.html").is_file()
        import json as _json
        pkg = _json.loads((proj / "reports" / "sample_dashboard" /
                           "report.json").read_text())
        assert pkg.get("libs") == ["echarts"], \
            "the sample chart must opt into the vendored ECharts or it is blank"
        assert not (proj / "reports" / "sample_dashboard.json").exists(), \
            "the scaffold must not teach the legacy spec lane"

    def test_init_scaffolds_an_agent_guide(self, tmp_path):
        """A fresh agent landing in the project must find orientation there —
        the project onboards its own agent."""
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        guide = proj / "AGENTS.md"
        assert guide.is_file(), "init must scaffold AGENTS.md"
        text = guide.read_text()
        # It must teach the load-bearing concepts, not just exist.
        for concept in ("tracebi context", "tracebi verify", "transforms/",
                        "models/", "reports/", "receipt"):
            assert concept in text, f"AGENTS.md should mention {concept}"

    def test_init_loop_ends_in_reproduces(self, tmp_path):
        """The README's four commands, verbatim: transform → validate →
        build → verify. The first thing a new user runs ends green."""
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0

        # ① transform — clean the sample input, sink the warehouse
        out = subprocess.run(
            [sys.executable, "transforms/sample_transform.py"],
            capture_output=True, text=True, cwd=str(proj),
        )
        assert out.returncode == 0, out.stderr
        assert (proj / "data" / "warehouse.duckdb").exists()

        # ③ render + receipt — the sample is an artifact package, so the
        # first page a project renders demonstrates the real lane: figure
        # claims, the presentation stack, provenance badges, and a manifest
        # that joins the sink contract (round-2 finding: the scaffold must
        # not teach the form `migrate` exists to convert away from).
        out = _run(["report", "build", "sample_dashboard"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        # M1 flip ledger: report build renders to output/ (finding #14).
        manifest = proj / "output" / "sample_dashboard.html.manifest.json"
        assert manifest.is_file()

        html = (proj / "output" / "sample_dashboard.html").read_text(
            encoding="utf-8")
        assert "tb-kpi" in html, "the sample page must use the shipped stack"
        # The scaffold's exploration block ("Working notes") must be DELETED
        # by the build — the inlined stylesheet still names the attribute in
        # its selectors, so assert on the content, not the string.
        assert "Working notes" not in html, \
            "exploration blocks must be deleted at the final build"
        import json as _json
        m = _json.loads(manifest.read_text(encoding="utf-8"))
        assert m["schema_version"] == 2 and m.get("figures"), \
            "the sample must produce the figure claims layer"
        contracts = m.get("transform_contracts", {})
        assert contracts and all(
            r.get("status") == "satisfied" for r in contracts.values()
        ), "the sample receipt must join the scaffolded sink contract green"

        # the loop closes under --strict: every figure in the scaffold is
        # bound, so the CI-gate bar itself reads green on first contact.
        out = _run(["verify", "output/sample_dashboard.html.manifest.json",
                    "--strict", "--contracts"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "REPRODUCES" in out.stdout
        assert "satisfied" in out.stdout

    def test_scaffolded_python_compiles(self, tmp_path):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        for f in ("transforms/sample_transform.py", "models/sample_model.py"):
            assert compileall.compile_file(
                str(proj / f), quiet=2
            ), f"{f} does not compile"

    def test_scaffolded_model_is_lazy(self, tmp_path):
        """Importing the scaffolded model must not touch the warehouse —
        it has to load before phase ① has ever run."""
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        # No warehouse exists yet; a connect-at-import would fail here.
        out = subprocess.run(
            [sys.executable, "-c",
             "from tracebi.model_registry import get_model; "
             "m = get_model('sample_model'); print('lazy-ok', m.name)"],
            capture_output=True, text=True, cwd=str(proj),
        )
        assert out.returncode == 0, out.stderr
        assert "lazy-ok" in out.stdout


class TestNewTransform:
    def test_scaffold_compiles(self, tmp_path):
        out = _run(["new-transform", "Orders Clean",
                    "--transforms-dir", str(tmp_path / "transforms")], tmp_path)
        assert out.returncode == 0, out.stderr
        f = tmp_path / "transforms" / "orders_clean.py"
        assert f.is_file()
        assert compileall.compile_file(str(f), quiet=2)
        text = f.read_text()
        assert "DuckDBConnector" in text
        # Notebook-shaped: percent cells, top-level execution — every
        # notebook editor opens it as a notebook; python runs it as a script.
        assert "# %%" in text and "# %% [markdown]" in text


class TestNewModelScaffold:
    def test_no_connect_at_import(self, tmp_path):
        """The new-model template must construct lazily — discovery imports
        every model file, and a connect at import opens a connection (or
        fails outright) on every scan."""
        out = _run(["--models-dir", str(tmp_path / "models"),
                    "new-model", "My Model"], tmp_path)
        assert out.returncode == 0, out.stderr
        text = (tmp_path / "models" / "my_model.py").read_text()
        assert "\nmodel.connect()" not in text


class TestNotebookShapedTransforms:
    """Transforms are notebook-shaped .py (percent cells) — every notebook
    editor opens them as notebooks while the file stays reviewable Python —
    and literal .ipynb runs top-to-bottom fresh via run-transform."""

    def test_scaffolds_are_percent_format(self, tmp_path):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        sample = (proj / "transforms" / "sample_transform.py").read_text()
        assert "# %% [markdown]" in sample and "# %%" in sample
        from tracebi.cli import _transform_template_text
        assert "# %% [markdown]" in _transform_template_text("X")

    def test_run_transform_executes_py_and_ipynb(self, tmp_path, monkeypatch):
        import json as _json
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        monkeypatch.chdir(proj)
        # the scaffolded notebook-shaped .py runs top-to-bottom
        assert cli.main(["run-transform", "sample_transform"]) == 0
        assert (proj / "data" / "warehouse.duckdb").exists()
        # a literal .ipynb transform runs fresh, cells concatenated in order
        nb = {"cells": [
            {"cell_type": "markdown", "source": ["# methodology\n"]},
            {"cell_type": "code", "source": ["x = 2\n"]},
            {"cell_type": "code",
             "source": ["open('nb_ran.txt', 'w').write(str(x * 21))\n"]},
        ], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
        (proj / "transforms" / "probe.ipynb").write_text(_json.dumps(nb))
        assert cli.main(["run-transform", "probe"]) == 0
        assert (proj / "nb_ran.txt").read_text() == "42"

    def test_run_transform_missing_is_a_clean_error(self, tmp_path, monkeypatch):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        monkeypatch.chdir(proj)
        assert cli.main(["run-transform", "nope"]) == 1


class TestReportSend:
    """`tracebi report send` — scheduled-delivery v1: distribution with the
    receipt attached, gated by verification.

    The honesty rule under test: distribution never outruns verification.
    A receipt that does not verify is refused; --force pastes the failing
    verdict INTO the body, so the red flag travels WITH the report — never
    silently. No test opens a socket: SMTP is faked at the smtplib seam or
    send_report is captured at the CLI seam.
    """

    _PASSING = {
        "verdict": "reproduces",
        "verdict_detail": "REPRODUCES — every checked section matches "
                          "the manifest",
        "exit_code": 0, "ok": True, "figures": [{"id": "kpi_total"}],
    }
    _FAILING = {
        "verdict": "not_reproduced",
        "verdict_detail": "NOT REPRODUCED — section(s) could not be shown "
                          "to reproduce; explain before anyone reads the "
                          "number",
        "exit_code": 1, "ok": False, "figures": [{"id": "kpi_total"}],
    }

    @pytest.fixture(scope="class")
    def proj(self, tmp_path_factory):
        """One scaffolded project with a sunk warehouse, shared by the
        class — each test rebuilds the report in-process (that is what
        `send` does) but the transform runs once."""
        proj = tmp_path_factory.mktemp("send") / "proj"
        assert cli.main(["init", str(proj)]) == 0
        out = subprocess.run(
            [sys.executable, "transforms/sample_transform.py"],
            capture_output=True, text=True, cwd=str(proj),
        )
        assert out.returncode == 0, out.stderr
        return proj

    def _env(self, monkeypatch, proj):
        monkeypatch.chdir(proj)
        monkeypatch.setenv("TRACEBI_SMTP_URL", "smtp://mail.example.com:2525")
        monkeypatch.setenv("TRACEBI_SMTP_FROM", "reports@example.com")
        monkeypatch.delenv("TRACEBI_SLACK_WEBHOOK", raising=False)

    def _fake_smtp(self, monkeypatch):
        """Capture the EmailMessage at the smtplib seam — no sockets."""
        import tracebi._delivery as delivery
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                sent["host"], sent["port"] = host, port

            def starttls(self):
                pass

            def login(self, user, password):
                sent["login"] = (user, password)

            def send_message(self, msg):
                sent["msg"] = msg

            def quit(self):
                pass

        monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(delivery.smtplib, "SMTP_SSL", FakeSMTP)
        return sent

    def test_send_report_names_the_missing_env_vars(self, tmp_path, monkeypatch):
        """Invariant 4 shape: unconfigured delivery fails loudly, naming
        exactly the variables to set."""
        from tracebi._delivery import send_report
        monkeypatch.delenv("TRACEBI_SMTP_URL", raising=False)
        monkeypatch.delenv("TRACEBI_SMTP_FROM", raising=False)
        html = tmp_path / "r.html"
        html.write_text("<p>x</p>")
        man = tmp_path / "r.html.manifest.json"
        man.write_text("{}")
        with pytest.raises(RuntimeError) as exc:
            send_report(html, man, "a@example.com")
        assert "TRACEBI_SMTP_URL" in str(exc.value)
        assert "TRACEBI_SMTP_FROM" in str(exc.value)

    def test_send_refuses_without_smtp_env(self, proj, monkeypatch, capsys):
        import tracebi.verify as verify_mod
        monkeypatch.chdir(proj)
        monkeypatch.delenv("TRACEBI_SMTP_URL", raising=False)
        monkeypatch.delenv("TRACEBI_SMTP_FROM", raising=False)
        monkeypatch.delenv("TRACEBI_SLACK_WEBHOOK", raising=False)
        monkeypatch.setattr(verify_mod, "verify_manifest",
                            lambda *a, **k: dict(self._PASSING))
        rc = cli.main(["report", "send", "sample_dashboard",
                       "--to", "a@example.com"])
        assert rc == 1
        assert "TRACEBI_SMTP_URL" in capsys.readouterr().err

    def test_send_refuses_when_verify_fails(self, proj, monkeypatch, capsys):
        import tracebi._delivery as delivery
        import tracebi.verify as verify_mod
        self._env(monkeypatch, proj)
        monkeypatch.setattr(verify_mod, "verify_manifest",
                            lambda *a, **k: dict(self._FAILING))
        attempted = []
        monkeypatch.setattr(delivery, "send_report",
                            lambda *a, **k: attempted.append(a))
        rc = cli.main(["report", "send", "sample_dashboard",
                       "--to", "a@example.com"])
        assert rc == 1
        assert not attempted, "a failing receipt must never be sent"
        assert "NOT REPRODUCED" in capsys.readouterr().err

    def test_force_sends_with_the_verdict_in_the_body(self, proj, monkeypatch):
        import tracebi.verify as verify_mod
        self._env(monkeypatch, proj)
        monkeypatch.setattr(verify_mod, "verify_manifest",
                            lambda *a, **k: dict(self._FAILING))
        sent = self._fake_smtp(monkeypatch)
        rc = cli.main(["report", "send", "sample_dashboard",
                       "--to", "a@example.com", "--force"])
        assert rc == 0
        body = sent["msg"].get_body(
            preferencelist=("plain",)).get_content()
        assert "DID NOT VERIFY" in body    # the red flag banner, up top
        assert "NOT REPRODUCED" in body    # the verdict itself

    def test_happy_path_attaches_html_and_manifest(self, proj, monkeypatch):
        import tracebi.verify as verify_mod
        self._env(monkeypatch, proj)
        monkeypatch.setattr(verify_mod, "verify_manifest",
                            lambda *a, **k: dict(self._PASSING))
        sent = self._fake_smtp(monkeypatch)
        rc = cli.main(["report", "send", "sample_dashboard",
                       "--to", "a@example.com,b@example.com"])
        assert rc == 0
        msg = sent["msg"]
        assert msg["To"] == "a@example.com, b@example.com"
        names = [p.get_filename() for p in msg.iter_attachments()]
        assert names == ["sample_dashboard.html",
                         "sample_dashboard.html.manifest.json"], \
            "the page and its receipt travel together"
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert "self-contained" in body and "receipt" in body
        assert "RED FLAG" not in body
