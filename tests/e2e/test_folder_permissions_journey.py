"""Folder permissions, end to end: two people in different sign-in groups, one
folder that only one group may see, over HTTP and over the agent gateway.

The people sign in through the same fake identity provider as the app and MCP
sign-in journeys; their groups travel from the provider's ID token to the
folder check (``tracebi/permissions.py``) in a session cookie or an access
token. Each test names the bug it would catch.
"""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("mcp")
pytest.importorskip("jwt")

import tests.e2e.test_mcp_local_signin_journey as local_journey  # noqa: E402
from tests.e2e.test_mcp_local_signin_journey import local  # noqa: E402, F401
from tests.e2e.test_app_sso_journey import sign_in_browser, sso  # noqa: E402, F401
from tests.e2e.test_mcp_oauth_journey import idp, mcp_session, sign_in, signin, tool  # noqa: E402, F401

HIDDEN = "finance/q3/pack"            # under finance/, whose _folder.yaml names the finance group
PUBLIC_ONE = "finance/public/notice"  # under finance/public/, whose own _folder.yaml opens it
OPEN = "sample_model/sample_dashboard"  # under no _folder.yaml at all


@pytest.fixture
def library(scaffolded):
    """The scaffolded project plus a finance folder that only finance may see."""
    from tracebi.web import discovery

    src = scaffolded / "reports" / "sample_model" / "sample_dashboard"
    for name in (HIDDEN, PUBLIC_ONE):
        shutil.copytree(src, scaffolded / "reports" / name)
    finance = scaffolded / "reports" / "finance"
    (finance / "_folder.yaml").write_text(
        "view: [finance]\nbuild: [finance-analysts]\n", encoding="utf-8")
    (finance / "public" / "_folder.yaml").write_text("view: ['*']\n", encoding="utf-8")
    discovery.rescan("reports", "models", "pipelines")
    return scaffolded


def person(sso, idp, name, *groups):
    b = sso()
    sign_in_browser(b, idp, sub=f"u-{name}", email=f"{name}@example.com", groups=list(groups))
    return b


def names(client):
    return {r["name"] for r in client.get("/api/reports").json()}


def test_a_hidden_folder_is_not_listed_and_looks_not_found_everywhere(library, sso, idp):
    """Catches a list that filters but a route that does not (or the reverse),
    and a refusal that says "forbidden" and so confirms the folder exists."""
    alice = person(sso, idp, "alice", "bi-analysts", "finance")
    bob = person(sso, idp, "bob", "bi-analysts")

    assert {HIDDEN, PUBLIC_ONE, OPEN} <= names(alice)
    assert names(bob) >= {PUBLIC_ONE, OPEN} and HIDDEN not in names(bob)

    # Alice builds it; the build is on disk for her.
    assert alice.post(f"/api/reports/{HIDDEN}/run").status_code == 200
    assert alice.get(f"/api/reports/{HIDDEN}/built").status_code == 200

    reads = [("get", f"/api/reports/{HIDDEN}/source"), ("get", f"/api/reports/{HIDDEN}/built"),
             ("get", f"/api/reports/{HIDDEN}/lineage"), ("get", f"/api/reports/{HIDDEN}/mermaid"),
             ("get", f"/api/reports/{HIDDEN}/download?format=html"),
             ("get", f"/r/{HIDDEN}"), ("post", f"/api/reports/{HIDDEN}/run"),
             ("post", f"/api/reports/{HIDDEN}/runs")]
    for method, url in reads:
        got = getattr(bob, method)(url)
        missing = getattr(bob, method)(url.replace("q3/pack", "q3/nothing"))
        # Whatever a name that does not exist gets, a hidden one gets.
        assert got.status_code == missing.status_code, (url, got.text)
        assert got.text.replace(HIDDEN, "X") == missing.text.replace("finance/q3/nothing", "X"), url
        assert getattr(alice, method)(url).status_code != got.status_code, url

    # A run history is empty, as for a report that does not exist.
    assert bob.get(f"/api/reports/{HIDDEN}/runs").json() == []

    # Its builds and schedule runs are no more visible than the report.
    assert not [r for r in bob.get("/api/runs").json() if HIDDEN in str(r.get("target"))]
    assert [r for r in alice.get("/api/runs").json() if HIDDEN in str(r.get("target"))]
    assert HIDDEN not in str(bob.get("/api/discovery").json())
    assert HIDDEN in str(alice.get("/api/discovery").json())


def test_the_nearest_folder_file_decides_and_is_read_at_request_time(library, sso, idp):
    """Catches a rule that unions with its ancestors (public/ would stay
    hidden to bob), and one cached past an edit."""
    bob = person(sso, idp, "bob", "bi-analysts")
    assert PUBLIC_ONE in names(bob)                   # its own file opens it
    assert bob.get(f"/api/reports/{PUBLIC_ONE}/source").status_code == 200

    (library / "reports" / "finance" / "public" / "_folder.yaml").write_text(
        "view: [finance-only-now]\n", encoding="utf-8")
    assert PUBLIC_ONE not in names(bob)               # no restart, no rescan
    assert bob.get(f"/api/reports/{PUBLIC_ONE}/source").status_code == 404

    (library / "reports" / "finance" / "public" / "_folder.yaml").unlink()
    assert PUBLIC_ONE not in names(bob)               # now finance/'s rule applies


def test_view_is_not_build_and_build_is_not_publish(library, sso, idp):
    """Catches drafts and publishing that ignore the folder: a person who can
    see a folder may not start a draft in it without Build, nor publish without
    Publish. The refusal is a 403 (they know the folder is there)."""
    alice = person(sso, idp, "alice", "bi-analysts", "finance")
    carol = person(sso, idp, "carol", "bi-analysts", "finance", "finance-analysts")
    bob = person(sso, idp, "bob", "bi-analysts")
    body = {"kind": "reports", "path": HIDDEN, "from_published": True}

    denied = alice.post("/api/drafts", json=body)
    assert denied.status_code == 403 and "build permission" in denied.text
    # Bob cannot even tell it is there: he is refused as a stranger, and a copy
    # of what he cannot read is not made.
    assert bob.post("/api/drafts", json=body).status_code == 403

    started = carol.post("/api/drafts", json=body)
    assert started.status_code == 201, started.text
    owner = started.json()["owner"]
    # Build is not Publish: her publish is a request, not a publish.
    published = carol.post(f"/api/drafts/{owner}/reports/{HIDDEN}/publish")
    assert published.status_code == 202 and published.json()["status"] == "requested"


def test_without_any_folder_file_nothing_changes(library, sso, idp):
    """Catches a permission check that locks out a deployment that never
    wrote one: roles decide, exactly as before."""
    (library / "reports" / "finance" / "_folder.yaml").unlink()
    (library / "reports" / "finance" / "public" / "_folder.yaml").unlink()
    bob = person(sso, idp, "bob", "bi-analysts")
    assert {HIDDEN, PUBLIC_ONE, OPEN} <= names(bob)
    assert bob.post(f"/api/reports/{HIDDEN}/run").status_code == 200
    assert bob.post("/api/drafts", json={"kind": "reports", "path": HIDDEN,
                                         "from_published": True}).status_code == 201


def test_an_admin_keeps_the_folder_even_when_the_file_is_broken(library, sso, idp):
    """Catches a typo in _folder.yaml locking out the people who can fix it,
    and one that crashes discovery or the list instead of failing closed."""
    (library / "reports" / "finance" / "_folder.yaml").write_text(
        "veiw: [finance]\n", encoding="utf-8")             # a typo'd permission name
    from tracebi.web import discovery
    discovery.rescan("reports", "models", "pipelines")
    assert not [e for e in discovery.discovery_report() if e["status"] == "failed"]
    admin = person(sso, idp, "ada", "bi-admins")
    alice = person(sso, idp, "alice", "bi-analysts", "finance")
    assert HIDDEN in names(admin)
    assert HIDDEN not in names(alice)                       # fails closed
    assert alice.get(f"/api/reports/{HIDDEN}/source").status_code == 404


def test_the_gateway_acts_as_the_person_and_hides_the_folder(library, sso, idp):
    """Catches an agent that sees more than the person using it: list_reports,
    the workbench, a build and the built file are all refused as not found."""
    c = sso.mcp_client
    _, alice_t = sign_in(c, idp, sub="u-alice", email="alice@example.com",
                         groups=["bi-analysts", "finance", "finance-analysts"])
    _, bob_t = sign_in(c, idp, sub="u-bob", email="bob@example.com", groups=["bi-analysts"])
    _, dave_t = sign_in(c, idp, sub="u-dave", email="dave@example.com",
                        groups=["bi-analysts", "finance"])
    a_token, b_token, d_token = (t["access_token"] for t in (alice_t, bob_t, dave_t))
    a, b, d = (mcp_session(c, t) for t in (a_token, b_token, d_token))

    def listed(token, session):
        got = tool(c, token, session, "list_reports")["structuredContent"]["reports"]
        return {e["module"] for e in got if e.get("module")}

    assert HIDDEN in listed(a_token, a)
    assert HIDDEN not in listed(b_token, b) and PUBLIC_ONE in listed(b_token, b)

    state = tool(c, b_token, b, "workbench_state", report=HIDDEN)["structuredContent"]
    gone = tool(c, b_token, b, "workbench_state", report="finance/q3/nothing")["structuredContent"]
    assert state["errors"][0].replace(HIDDEN, "X") == gone["errors"][0].replace("finance/q3/nothing", "X")
    assert tool(c, a_token, a, "workbench_state", report=HIDDEN)["structuredContent"].get("figures") is not None

    refused = tool(c, b_token, b, "build_report", report=HIDDEN)["structuredContent"]
    assert refused["ok"] is False and "no artifact package" in refused["errors"][0]

    # Dave sees the folder (finance) but may not build in it (finance-analysts).
    viewed = tool(c, d_token, d, "build_report", report=HIDDEN)
    assert viewed["isError"] and "build permission" in viewed["content"][0]["text"]

    built = tool(c, a_token, a, "build_report", report=HIDDEN)["structuredContent"]
    assert built["ok"], built
    mine = tool(c, a_token, a, "fetch_artifact", path=built["output_path"])["structuredContent"]
    assert mine["ok"]
    for path in (built["output_path"], built["manifest_path"]):
        theirs = tool(c, b_token, b, "fetch_artifact", path=path)["structuredContent"]
        assert theirs["ok"] is False and "no file at" in theirs["errors"][0]
    verify = tool(c, b_token, b, "verify_manifest", manifest=built["manifest_path"])["structuredContent"]
    assert verify["ok"] is False and "not found" in verify["errors"][0]


def test_the_gateway_drafts_need_build_on_the_folder(library, sso, idp):
    """Catches start_draft over MCP skipping the folder check that HTTP has."""
    c = sso.mcp_client
    _, t = sign_in(c, idp, sub="u-alice", email="alice@example.com",
                   groups=["bi-analysts", "finance"])
    token = t["access_token"]
    session = mcp_session(c, token)
    got = tool(c, token, session, "start_draft", kind="reports", path=HIDDEN,
               from_published=True)["structuredContent"]
    assert got["ok"] is False and "build permission" in got["errors"][0]


def test_the_cli_and_the_scheduler_are_the_operator(library, cli):
    """Catches a folder file that stops `tracebi report build` or a schedule
    on the server: they have no sign-in, and run as the operator."""
    assert cli("run-transform", "sample_transform")[0] == 0
    code, out = cli("report", "build", HIDDEN)
    assert code == 0, out

    from tracebi.audit import actor
    from tracebi.permissions import can
    with actor("scheduler", role="cli"):
        assert can("publish", HIDDEN) and can("manage", HIDDEN)


@pytest.fixture
def local_groups(monkeypatch):
    """The built-in sign-in journey's users, with groups on the role."""
    import tests.e2e.test_mcp_local_signin_journey as journey

    monkeypatch.setattr(journey, "USERS",
                        "alice:analyst@finance+ops:alice-password,vera:analyst:vera-password")


def test_a_person_with_local_sign_in_carries_their_groups_to_the_gateway(local_groups, local, library):
    """Catches TRACEBI_LOCAL_USERS name:role@groups dropping the groups on the
    way to the token (the old name:role:password form keeps working)."""
    c = local
    seen = {}
    for name, password in (("alice", "alice-password"), ("vera", "vera-password")):
        token = local_journey.tokens_for(c, username=name, password=password)
        session = mcp_session(c, token)
        got = tool(c, token, session, "list_reports")["structuredContent"]["reports"]
        seen[name] = {e["module"] for e in got if e.get("module")}
    assert HIDDEN in seen["alice"] and HIDDEN not in seen["vera"]


def test_a_session_older_than_group_support_still_works(library, sso, idp):
    """Catches the migration (or the session read) failing for a session row
    with no groups: it signs in, sees what its role sees, nothing crashes."""
    from sqlalchemy import text

    from tracebi import state

    bob = person(sso, idp, "bob", "bi-analysts")
    with state.ensure().begin() as conn:
        conn.execute(text("UPDATE tracebi_sessions SET groups = NULL"))
    assert bob.get("/api/me").status_code == 200
    assert HIDDEN not in names(bob)
