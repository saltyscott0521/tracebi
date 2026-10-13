"""My published and the folders in the app, end to end.

Two analysts (Alice, Bob) and a finance publisher (Lena) share one library.
Each test names the bug it would catch.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")
pytest.importorskip("jwt")

from tests.e2e.test_app_sso_journey import sign_in_browser, sso  # noqa: E402, F401
from tests.e2e.test_mcp_oauth_journey import idp, signin  # noqa: E402, F401

SOURCE = "sample_model/sample_dashboard"
FOLDER_FILE = ("view: [finance]\nbuild: [finance-analysts]\n"
               "publish: [finance-leads]\n")


@pytest.fixture
def library(scaffolded, cli):
    assert cli("run-transform", "sample_transform")[0] == 0
    return scaffolded


def person(sso, idp, name, *groups):
    b = sso()
    sign_in_browser(b, idp, sub=f"u-{name}", email=f"{name}@example.com",
                    groups=["bi-analysts", *groups])
    return b


def start(client):
    got = client.post("/api/drafts", json={"kind": "reports", "path": SOURCE,
                                           "from_published": True})
    assert got.status_code in (200, 201), got.text
    return got.json()["owner"]


def publish(client, owner, **body):
    return client.post(f"/api/drafts/{owner}/reports/{SOURCE}/publish", json=body)


def rescan():
    """What the live watcher does every few seconds."""
    from tracebi.web import discovery
    discovery.rescan("reports", "models", "pipelines")


def names(client):
    return [r["name"] for r in client.get("/api/reports").json()]


def destinations(client, owner):
    got = client.get(f"/api/drafts/{owner}/reports/{SOURCE}/destinations").json()
    return {d["folder"]: d for d in got["destinations"]}


def test_my_published_is_theirs_and_others_see_it_only_when_granted(library, sso, idp):
    """Catches a personal folder that is not offered, one that is not Publish
    for its owner (a request instead of a publish), one every analyst can see
    (or that a library-wide `view: ['*']` exposes), and a grant inside it that
    is ignored."""
    (library / "reports" / "_folder.yaml").write_text(
        "view: ['*']\nbuild: ['*']\npublish: ['*']\n", encoding="utf-8")
    alice = person(sso, idp, "alice")
    bob = person(sso, idp, "bob")
    mine = alice.get("/api/folders").json()
    assert mine["personal"] == "my-published/alice@example.com"
    first = mine["folders"][0]
    assert (first["name"], first["mine"], first["mode"]) == ("My published", True, "publish")

    owner = start(alice)
    assert destinations(alice, owner)[mine["personal"]]["mode"] == "publish"
    landed = publish(alice, owner, folder=mine["personal"], note="mine")
    assert landed.status_code == 200 and landed.json()["status"] == "published", landed.text
    path = f"{mine['personal']}/sample_dashboard"
    assert landed.json()["path"] == path
    assert (library / "reports" / path / "report.json").is_file()
    rescan()

    assert path in names(alice)
    assert path not in names(bob)
    assert mine["personal"] not in [f["path"] for f in bob.get("/api/folders").json()["folders"]]
    assert bob.get(f"/api/reports/{path}/built").status_code == 404
    listed = {r["name"]: r for r in alice.get("/api/reports").json()}[path]
    assert listed["folder"] == mine["personal"] and listed["owner"] == "alice@example.com"

    # Alice shares it by file: View for Bob, and no more than View.
    (library / "reports" / mine["personal"] / "_folder.yaml").write_text(
        "view: [bob@example.com]\n", encoding="utf-8")
    rescan()
    assert path in names(bob)
    seen = {f["path"]: f for f in bob.get("/api/folders").json()["folders"]}[mine["personal"]]
    assert (seen["level"], seen["mine"], seen["mode"]) == ("view", False, None)
    assert bob.get(f"/api/reports/{path}/built").status_code != 404
    owner_b = start(bob)
    assert publish(bob, owner_b, folder=mine["personal"]).status_code == 403


def test_no_sign_in_means_no_personal_folder(library):
    """Catches a shared-token, command-line or unauthenticated actor being
    handed (or crashing on) a personal folder it has no name for."""
    from tracebi import folders, permissions
    from tracebi.audit import actor

    assert permissions.personal_folder() is None
    with actor("agent", role=None):                 # the shared gateway token
        assert permissions.personal_folder() is None
    with actor("alice@example.com", role="analyst"):
        assert permissions.personal_folder() == "my-published/alice@example.com"
    listing = folders.list_folders([])
    assert listing["personal"] is None
    assert "needs a signed-in person" in listing["personal_note"]


def test_a_build_only_publish_is_asked_and_the_approver_decides_it(library, sso, idp):
    """Catches a destination list that calls a request a publish (or hides the
    folder), a pending request that does not reach the approver with the right
    to decide, a decline recorded without its reason, and an approval that
    does not publish."""
    finance = library / "reports" / "finance"
    finance.mkdir()
    (finance / "_folder.yaml").write_text(FOLDER_FILE, encoding="utf-8")
    alice = person(sso, idp, "alice", "finance", "finance-analysts")
    lena = person(sso, idp, "lena", "finance", "finance-leads")
    owner = start(alice)

    options = destinations(alice, owner)
    assert options["finance"]["mode"] == "request"
    assert options["my-published/alice@example.com"]["mode"] == "publish"
    assert options[None]["mode"] == "publish"

    asked = publish(alice, owner, folder="finance", note="for Q3")
    assert asked.status_code == 202 and asked.json()["status"] == "requested"
    rid = asked.json()["request"]["id"]
    mine = alice.get("/api/publish-requests").json()["requests"][0]
    theirs = lena.get("/api/publish-requests?status=pending").json()["requests"][0]
    assert (mine["can_decide"], theirs["can_decide"], theirs["id"]) == (False, True, rid)

    no = lena.post(f"/api/publish-requests/{rid}/reject", json={"note": "wait for the audit"})
    assert no.json()["request"]["decision_note"] == "wait for the audit"
    assert not (finance / "sample_dashboard").exists()

    rid2 = publish(alice, owner, folder="finance").json()["request"]["id"]
    assert lena.post(f"/api/publish-requests/{rid2}/approve").status_code == 200
    assert (finance / "sample_dashboard" / "report.json").is_file()
    rescan()
    listed = {r["name"]: r for r in alice.get("/api/reports").json()}["finance/sample_dashboard"]
    assert listed["owner"] == "alice@example.com" and listed["folder"] == "finance"


def test_a_folders_permissions_are_shown_read_only_and_only_to_a_manager(library, sso, idp):
    """Catches a folder's permissions shown to someone without Manage, and one
    that claims to be editable in the app."""
    finance = library / "reports" / "finance"
    finance.mkdir()
    (finance / "_folder.yaml").write_text(FOLDER_FILE, encoding="utf-8")
    lena = person(sso, idp, "lena", "finance", "finance-leads")
    entry = {f["path"]: f for f in lena.get("/api/folders").json()["folders"]}["finance"]
    assert entry["level"] == "publish" and "permissions" not in entry

    from tracebi import folders
    listing = folders.list_folders([])               # no sign-in: Manage everywhere
    shown = {f["path"]: f for f in listing["folders"]}["finance"]
    assert shown["level"] == "manage" and shown["permissions"]["editable"] is False
    assert shown["permissions"]["grants"]["publish"] == ["finance-leads"]
    assert shown["permissions"]["file"] == "finance/_folder.yaml"
