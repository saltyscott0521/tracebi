"""Remote authoring from a laptop: ``tracebi push``, code approval, git sync.

An analyst edits a copy of the project on their laptop and pushes it to the
served app as themselves: the report package and the declarative model land
in their drafts, the transform lands as a code request. They cannot approve
it; an admin reviews the diff and approves, the file goes in and the pipeline
that runs it runs once on the server. The CLI's HTTP transport is routed into
the in-process app (the login itself is ``test_login_cli_journey``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
from contextlib import contextmanager

import pytest

pytest.importorskip("mcp")
pytest.importorskip("jwt")

from tests.e2e.conftest import follow_run, run_cli  # noqa: E402
from tests.e2e.test_app_sso_journey import sso  # noqa: E402, F401
from tests.e2e.test_mcp_oauth_journey import PUBLIC, idp, sign_in, signin  # noqa: E402, F401
from tracebi import credentials  # noqa: E402


@contextmanager
def _cwd(path):
    here = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(here)


@pytest.fixture
def laptop(sso, idp, scaffolded, tmp_path, monkeypatch):
    """A copy of the project to edit, and the CLI signed in as whoever
    ``as_person`` names. The server keeps its own working directory."""
    c = sso.mcp_client
    tokens = {
        "alice": sign_in(c, idp, groups=["bi-analysts"])[1]["access_token"],
        "boss": sign_in(c, idp, sub="u-boss", email="boss@example.com",
                        groups=["bi-admins"])[1]["access_token"],
    }
    who = {"name": "alice"}
    server = scaffolded
    app = sso()

    def fake_request(method, url, *, form=None, json_body=None, bearer=None):
        assert url.startswith(PUBLIC + "/"), url
        with _cwd(server):
            resp = app.request(method, url[len(PUBLIC):], json=json_body,
                               headers={"Authorization": f"Bearer {bearer}"})
        return resp.status_code, resp.json()

    monkeypatch.setattr(credentials, "_request", fake_request)
    monkeypatch.setattr(credentials, "access_token", lambda s: tokens[who["name"]])
    copy = tmp_path / "laptop"
    shutil.copytree(server, copy, ignore=shutil.ignore_patterns("data", ".tracebi", "output"))
    monkeypatch.chdir(copy)

    def as_person(name):
        who["name"] = name
        return {"Authorization": f"Bearer {tokens[name]}"}
    return copy, server, _Server(app, server), as_person


class _Server:
    """The app, called from the server's working directory, as it runs."""

    def __init__(self, app, root):
        self.app, self.root = app, root

    def get(self, path, **kw):
        with _cwd(self.root):
            return self.app.get(path, **kw)

    def post(self, path, **kw):
        with _cwd(self.root):
            return self.app.post(path, **kw)

    def signed(self, headers):
        """This server with one person's credentials on every GET."""
        server = self

        class _Signed:
            def get(self, path, **kw):
                return server.get(path, headers=headers, **kw)
        return _Signed()


def test_a_laptop_pushes_drafts_and_code_an_admin_approves(laptop):
    copy, server, app, as_person = laptop
    alice = as_person("alice")
    pkg = copy / "reports" / "sample_model" / "sample_dashboard"
    (pkg / "app.jsx").write_text(
        (pkg / "app.jsx").read_text().replace("</h1>", " (pushed)</h1>", 1))
    model = copy / "models" / "sample_model.yaml"
    model.write_text(model.read_text() + "# reviewed on a laptop\n")
    transform = copy / "transforms" / "sample_transform.py"
    transform.write_text(transform.read_text() + '\nprint("from the laptop")\n')

    # Data stays home, and code needs a reason for its reviewer.
    (copy / "inputs" / "orders.csv").touch()
    code, out = run_cli("push", "inputs/orders.csv", "--server", PUBLIC)
    assert code == 1 and "Data stays on this machine" in out
    code, out = run_cli("push", str(pkg), "models/sample_model.yaml",
                        "transforms/sample_transform.py", "--server", PUBLIC)
    assert code == 1 and "--note" in out
    assert not (server / "drafts").exists()        # refused before anything was sent

    code, out = run_cli("push", str(pkg), "models/sample_model.yaml",
                        "transforms/sample_transform.py", "--server", PUBLIC,
                        "--note", "Print when the transform runs")
    assert code == 0, out
    assert "draft  reports/sample_model/sample_dashboard" in out
    assert "draft  models/sample_model" in out
    [req_id] = [w.rstrip(",") for w in out.split() if w[:8].isdigit() and "T" in w]
    os.chdir(server)        # the laptop's part is done; runs below are the server's

    # The drafts are alice's; nothing is published yet.
    drafts = {(d["kind"], d["path"]): d for d in app.get("/api/drafts", headers=alice).json()["drafts"]}
    assert set(drafts) == {("reports", "sample_model/sample_dashboard"), ("models", "sample_model")}
    assert "(pushed)" not in (server / "reports/sample_model/sample_dashboard/app.jsx").read_text()
    assert "from the laptop" not in (server / "transforms/sample_transform.py").read_text()

    # Alice sees her request and its diff, and cannot approve it.
    req = app.get(f"/api/code-requests/{req_id}", headers=alice).json()
    assert req["status"] == "pending" and req["requested_by"] == "alice@example.com"
    assert req["can_decide"] is False
    [f] = req["files"]
    assert f["path"] == "transforms/sample_transform.py" and not f["new"]
    assert '+print("from the laptop")' in f["diff"]
    assert app.post(f"/api/code-requests/{req_id}/approve", headers=alice).status_code == 403

    # Someone else's request is not there for her.
    boss = as_person("boss")
    theirs = app.post("/api/code-requests", headers=boss, json={
        "files": {"pipelines/other.yaml": "name: other\n"}, "note": "n"}).json()["id"]
    assert app.get(f"/api/code-requests/{theirs}", headers=alice).status_code == 404
    assert [r["id"] for r in app.get("/api/code-requests", headers=alice).json()["requests"]] == [req_id]
    assert app.post("/api/code-requests", headers=boss, json={
        "files": {"../outside.py": "x"}, "note": "n"}).status_code == 422

    # The admin approves: the file goes in, what it replaced is kept, and the
    # pipeline that runs this transform runs once on the server.
    assert app.post(f"/api/code-requests/{req_id}/reject", headers=boss,
                    json={"note": ""}).status_code == 422
    done = app.post(f"/api/code-requests/{req_id}/approve", headers=boss).json()
    assert done["status"] == "approved" and done["decided_by"] == "boss@example.com"
    assert "from the laptop" in (server / "transforms/sample_transform.py").read_text()
    kept = server / ".tracebi/history/code" / done["version"] / "transforms/sample_transform.py"
    assert "from the laptop" not in kept.read_text()
    [run] = done["runs"]
    assert run["pipeline"] == "sample_model"
    log, final = follow_run(app.signed(boss), "sample_model", run["run_id"])
    assert final["status"] == "succeeded", log
    assert "from the laptop" in log
    again = app.get(f"/api/code-requests/{req_id}", headers=alice).json()
    assert again["runs"][0]["status"] == "succeeded"
    assert '+print("from the laptop")' in again["files"][0]["diff"]   # against what it replaced
    assert app.post(f"/api/code-requests/{req_id}/approve", headers=boss).status_code == 422


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"})


def test_a_git_checkout_library_syncs_on_a_signed_webhook(sso, scaffolded, tmp_path, monkeypatch):
    """The git lane: review happened in the pull request; the webhook pulls
    the merge and the app shows it. Outside sign-in, guarded by its own secret."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    app = sso()
    assert app.post("/api/library/sync").status_code == 404      # no secret: no endpoint

    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(scaffolded, "init", "-q", "-b", "main")
    _git(scaffolded, "add", "reports", "models", "pipelines", "transforms", "connections")
    _git(scaffolded, "commit", "-q", "-m", "library")
    _git(scaffolded, "remote", "add", "origin", str(origin))
    _git(scaffolded, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(origin), str(other))
    shutil.copytree(other / "reports/sample_model/sample_dashboard",
                    other / "reports/sample_model/merged_report")
    _git(other, "add", ".")
    _git(other, "commit", "-q", "-m", "merged report")
    _git(other, "push", "-q")

    monkeypatch.setenv("TRACEBI_LIBRARY_SYNC_SECRET", "s3cret")
    body = json.dumps({"ref": "refs/heads/main"}).encode()
    assert app.post("/api/library/sync", content=body).status_code == 401
    assert app.post("/api/library/sync", content=body,
                    headers={"X-Hub-Signature-256": "sha256=" + "0" * 64}).status_code == 401
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    resp = app.post("/api/library/sync", content=body, headers={"X-Hub-Signature-256": sig})
    assert resp.status_code == 200, resp.text
    assert "sample_model/merged_report" in resp.json()["discovered"]["added"]
    assert (scaffolded / "reports/sample_model/merged_report/report.json").is_file()
