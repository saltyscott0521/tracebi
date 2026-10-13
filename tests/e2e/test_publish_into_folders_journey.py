"""Publishing a draft into a folder, and asking for it, end to end.

Three people share one library: Lena may publish into ``finance/`` (the
finance-leads group), Alice may only build there (finance-analysts), and Bob
is not in the folder at all. Over HTTP and over the agent gateway. Each test
names the bug it would catch.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")
pytest.importorskip("jwt")

from tests.e2e.test_app_sso_journey import sign_in_browser, sso  # noqa: E402, F401
from tests.e2e.test_mcp_oauth_journey import idp, mcp_session, sign_in, signin, tool  # noqa: E402, F401

SOURCE = "sample_model/sample_dashboard"     # under no _folder.yaml
DEST = "finance/q3"                          # a folder that does not exist yet
LANDS = "finance/q3/sample_dashboard"
FOLDER_FILE = ("view: [finance]\nbuild: [finance-analysts]\n"
               "publish: [finance-leads]\n")


@pytest.fixture
def library(scaffolded, cli):
    assert cli("run-transform", "sample_transform")[0] == 0
    finance = scaffolded / "reports" / "finance"
    finance.mkdir()
    (finance / "_folder.yaml").write_text(FOLDER_FILE, encoding="utf-8")
    return scaffolded


def person(sso, idp, name, *groups):
    b = sso()
    sign_in_browser(b, idp, sub=f"u-{name}", email=f"{name}@example.com",
                    groups=["bi-analysts", *groups])
    return b


def start(client, path=SOURCE):
    got = client.post("/api/drafts", json={"kind": "reports", "path": path,
                                           "from_published": True})
    assert got.status_code in (200, 201), got.text
    return got.json()["owner"]


def publish(client, owner, **body):
    return client.post(f"/api/drafts/{owner}/reports/{SOURCE}/publish", json=body)


def test_a_publisher_publishes_into_a_new_folder_and_the_history_says_who(library, sso, idp):
    """Catches a folder choice that is ignored (it lands at the draft's own
    path), a new folder that is refused or not created, a replaced version not
    kept, and a history with no author or time."""
    lena = person(sso, idp, "lena", "finance", "finance-leads")
    owner = start(lena)
    first = publish(lena, owner, folder=DEST, note="first")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "published" and first.json()["path"] == LANDS
    assert (library / "reports" / LANDS / "report.json").is_file()

    second = publish(lena, owner, folder=DEST, note="second")
    assert second.json()["previous"], "the version it replaced is kept"

    from tracebi import drafts
    log = drafts.publish_history("reports", LANDS)
    assert [e["note"] for e in log] == ["first", "second"]
    assert all(e["published_by"] == "lena@example.com" and e["published_at"] for e in log)
    assert not (library / "drafts" / "_requests").exists()


def test_build_only_asks_and_a_publisher_approves_exactly_what_was_asked(library, sso, idp):
    """Catches a Build holder publishing outright, a request visible to people
    with no say, an approval by the requester, an approval that publishes the
    draft as edited since (not as asked), and a history that forgets who
    approved and when."""
    alice = person(sso, idp, "alice", "finance", "finance-analysts")
    lena = person(sso, idp, "lena", "finance", "finance-leads")
    bob = person(sso, idp, "bob")
    owner = start(alice)
    asked = publish(alice, owner, folder=DEST, note="please")
    assert asked.status_code == 202, asked.text
    request = asked.json()["request"]
    assert asked.json()["status"] == "requested" and request["status"] == "pending"
    assert request["requested_by"] == "alice@example.com" and request["destination"] == LANDS
    assert not (library / "reports" / LANDS).exists()

    # The request is a file: it is what survives a restart.
    assert (library / "drafts" / "_requests" / f"{request['id']}.json").is_file()
    listed = lambda c: [r["id"] for r in c.get("/api/publish-requests").json()["requests"]]  # noqa: E731
    assert listed(alice) == listed(lena) == [request["id"]] and listed(bob) == []
    assert bob.post(f"/api/publish-requests/{request['id']}/approve").status_code == 404

    # The requester edits the draft afterwards; the approver still gets what was asked.
    alice.put(f"/api/drafts/{owner}/reports/{SOURCE}/files/style.css",
              json={"content": "body { color: red; }"})
    # She cannot approve her own.
    own = alice.post(f"/api/publish-requests/{request['id']}/approve")
    assert own.status_code == 403 and "publish permission" in own.text
    assert not (library / "reports" / LANDS).exists()

    done = lena.post(f"/api/publish-requests/{request['id']}/approve")
    assert done.status_code == 200, done.text
    assert done.json()["request"]["decided_by"] == "lena@example.com"
    assert not (library / "reports" / LANDS / "style.css").exists()
    assert listed(alice) == [request["id"]]
    assert alice.get("/api/publish-requests?status=pending").json()["requests"] == []

    from tracebi import drafts
    [entry] = drafts.publish_history("reports", LANDS)
    assert (entry["published_by"], entry["requested_by"], entry["approved_by"]) == (
        "alice@example.com",) * 2 + ("lena@example.com",)
    assert entry["approved_at"] and entry["requested_at"] and entry["request_id"] == request["id"]

    again = lena.post(f"/api/publish-requests/{request['id']}/approve")
    assert again.status_code == 422 and "already approved" in again.text


def test_a_rejection_needs_a_note_and_publishes_nothing(library, sso, idp):
    """Catches a rejection that publishes, one with no reason, and a decided
    request that can be decided again."""
    alice = person(sso, idp, "alice", "finance", "finance-analysts")
    lena = person(sso, idp, "lena", "finance", "finance-leads")
    owner = start(alice)
    rid = publish(alice, owner, folder=DEST).json()["request"]["id"]
    assert lena.post(f"/api/publish-requests/{rid}/reject", json={"note": ""}).status_code == 422
    assert alice.post(f"/api/publish-requests/{rid}/reject",
                      json={"note": "mine"}).status_code == 403
    no = lena.post(f"/api/publish-requests/{rid}/reject", json={"note": "not this quarter"})
    assert no.status_code == 200 and no.json()["status"] == "rejected"
    seen = alice.get("/api/publish-requests").json()["requests"][0]
    assert seen["status"] == "rejected" and seen["decision_note"] == "not this quarter"
    assert not (library / "reports" / LANDS).exists()
    assert lena.post(f"/api/publish-requests/{rid}/approve").status_code == 422


def test_someone_without_build_there_is_refused_not_asked(library, sso, idp):
    """Catches the request path letting a person who cannot even build in the
    folder queue a request."""
    viewer = person(sso, idp, "vic", "finance")
    owner = start(viewer)
    got = publish(viewer, owner, folder=DEST)
    assert got.status_code == 403 and "publish permission" in got.text


def test_the_gateway_asks_and_a_publisher_decides(library, sso, idp):
    """Catches the agent tools lacking the folder, the request or the decision,
    and the decision skipping the Publish check the app has."""
    c = sso.mcp_client
    _, a = sign_in(c, idp, sub="u-alice", email="alice@example.com",
                   groups=["bi-analysts", "finance", "finance-analysts"])
    _, l = sign_in(c, idp, sub="u-lena", email="lena@example.com",
                   groups=["bi-analysts", "finance", "finance-leads"])
    ta, tl = a["access_token"], l["access_token"]
    sa, sl = mcp_session(c, ta), mcp_session(c, tl)
    assert tool(c, ta, sa, "start_draft", kind="reports", path=SOURCE,
                from_published=True)["structuredContent"]["ok"]
    asked = tool(c, ta, sa, "publish_draft", kind="reports", path=SOURCE,
                 folder=DEST)["structuredContent"]
    assert asked["ok"] and asked["status"] == "requested", asked
    rid = asked["request"]["id"]

    mine = tool(c, tl, sl, "list_publish_requests", status="pending")["structuredContent"]
    assert [r["id"] for r in mine["requests"]] == [rid]
    own = tool(c, ta, sa, "decide_publish_request", request_id=rid, approve=True)["structuredContent"]
    assert own["ok"] is False and "publish permission" in own["errors"][0]
    done = tool(c, tl, sl, "decide_publish_request", request_id=rid,
                approve=True)["structuredContent"]
    assert done["ok"] and done["status"] == "approved", done
    assert (library / "reports" / LANDS / "report.json").is_file()

    from tracebi import drafts
    [entry] = drafts.publish_history("reports", LANDS)
    assert entry["approved_by"] == "lena@example.com" and entry["approved_at"]


def test_a_checkable_folder_refuses_python_at_publish_and_at_request(library, sso, idp):
    """Catches the folder's `accepts: checkable` being unread, or enforced on
    only one of the two paths, and a plain checkable report being refused."""
    (library / "reports" / "finance" / "_folder.yaml").write_text(
        FOLDER_FILE + "accepts: checkable\n", encoding="utf-8")
    alice = person(sso, idp, "alice", "finance", "finance-analysts")
    lena = person(sso, idp, "lena", "finance", "finance-leads")
    a_owner, l_owner = start(alice), start(lena)

    # A draft cannot hold report.py through the app, so put one on disk.
    for who in ("alice", "lena"):
        draft = next((library / "drafts").glob(f"{who}@*/reports/{SOURCE}"))
        (draft / "report.py").write_text("def build(inputs):\n    return {}\n", encoding="utf-8")
    for client, owner in ((alice, a_owner), (lena, l_owner)):
        refused = publish(client, owner, folder=DEST)
        assert refused.status_code == 422, refused.text
        assert "accepts only checkable" in refused.text and "report.py" in refused.text
    assert not (library / "drafts" / "_requests").exists()
    assert not (library / "reports" / LANDS).exists()

    for who in ("alice", "lena"):
        (next((library / "drafts").glob(f"{who}@*/reports/{SOURCE}")) / "report.py").unlink()
    assert publish(lena, l_owner, folder=DEST).status_code == 200
    assert publish(alice, a_owner, folder=DEST).status_code == 202


def test_checkable_names_the_figure_that_python_computed():
    """Catches a section the replay cannot reproduce passing as checkable, and
    a refusal that does not say which one."""
    from types import SimpleNamespace

    from pathlib import Path

    from tracebi.drafts import checkable_problems

    manifest = SimpleNamespace(
        sections=[{"id": "ok", "dataset_fingerprint": "f", "dataset_lineage": [
                       {"metadata": {"query_spec": {"x": 1}, "model": "m"}, "operation": "query"}]},
                  {"id": "py", "dataset_fingerprint": "g", "verifiable": False}],
        figures=[{"id": "total", "binding": "py"}])
    problems = checkable_problems(Path("."), manifest)
    assert len(problems) == 1 and "'py' is computed by Python" in problems[0]
    assert "total" in problems[0]


def test_an_unknown_accepts_value_fails_closed(library, sso, idp):
    """Catches a typo'd `accepts` being read as the permissive default."""
    (library / "reports" / "finance" / "_folder.yaml").write_text(
        FOLDER_FILE + "accepts: anything\n", encoding="utf-8")
    from tracebi import permissions
    assert permissions.folder_accepts(LANDS) == "checkable"
    lena = person(sso, idp, "lena", "finance", "finance-leads")
    owner = start(lena)
    assert publish(lena, owner, folder=DEST).status_code == 403   # nobody but admins


def test_without_any_folder_file_publishing_is_unchanged(scaffolded, cli, sso, idp):
    """Catches a deployment that never wrote a _folder.yaml suddenly getting
    requests, or needing to name a folder."""
    assert cli("run-transform", "sample_transform")[0] == 0
    bob = person(sso, idp, "bob")
    owner = start(bob)
    plain = publish(bob, owner)
    assert plain.status_code == 200 and plain.json()["status"] == "published"
    assert plain.json()["path"] == SOURCE
    moved = publish(bob, owner, folder="anywhere")
    assert moved.status_code == 200 and moved.json()["path"] == "anywhere/sample_dashboard"
    assert not (scaffolded / "drafts" / "_requests").exists()
    assert json.loads(bob.get("/api/publish-requests").text) == {"requests": []}
