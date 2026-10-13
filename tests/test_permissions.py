"""The folder permission check, edge by edge.

The journeys in ``tests/e2e/test_folder_permissions_journey.py`` drive it
through the app and the gateway; these pin what a journey cannot: grant
semantics, failing closed, and the shape of a name.
"""

from __future__ import annotations

import logging

import pytest

from tracebi.audit import actor, get_groups
from tracebi.permissions import (
    BUILD, MANAGE, NONE, PUBLISH, VIEW, Principal, can, granted_level, require, NotPermitted,
)

ANALYST = Principal("ann@example.com", "analyst", ("finance",))
VIEWER = Principal("vic@example.com", "viewer", ("finance",))
ADMIN = Principal("ada@example.com", "admin", ())
OPERATOR = Principal(None, "cli", ())


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """reports/ with a package at finance/q3/pack and one at open/pack."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRACEBI_LIBRARY_MOUNTS", raising=False)
    monkeypatch.delenv("TRACEBI_REPORTS_DIR", raising=False)
    for rel in ("finance/q3/pack", "open/pack"):
        (tmp_path / "reports" / rel).mkdir(parents=True)
        (tmp_path / "reports" / rel / "report.json").write_text("{}")
    return tmp_path / "reports"


def level(who, name="finance/q3/pack"):
    return granted_level(name, who)


def test_with_no_file_the_role_alone_decides(lib):
    """The no-lockout promise: a deployment that never wrote a _folder.yaml."""
    assert level(VIEWER) == VIEW and level(ANALYST) == PUBLISH
    assert level(ADMIN) == MANAGE and level(OPERATOR) == MANAGE
    assert level(Principal(None, None, ())) == MANAGE      # no sign-in at all


def test_the_nearest_file_replaces_its_ancestors(lib):
    (lib / "_folder.yaml").write_text("view: [everyone-at-root]\n")
    (lib / "finance" / "_folder.yaml").write_text("view: [finance]\n")
    assert level(ANALYST) == VIEW                                    # finance/'s file
    assert level(Principal("x", "analyst", ("everyone-at-root",))) == NONE   # not unioned
    assert level(Principal("x", "analyst", ("everyone-at-root",)), "open/pack") == VIEW
    (lib / "finance" / "q3" / "_folder.yaml").write_text("manage: [finance]\n")
    assert level(ANALYST) == PUBLISH                                 # q3's file, capped by role


def test_a_level_includes_the_ones_below_it_and_a_name_works_like_a_group(lib):
    (lib / "finance" / "_folder.yaml").write_text(
        "build: [finance]\npublish: [Ann@Example.com]\nview: [anyone]\n")
    assert level(Principal("bob", "analyst", ("anyone",))) == VIEW
    assert level(Principal("bob", "analyst", ("FINANCE",))) == BUILD
    assert level(ANALYST) == PUBLISH                       # by name, ignoring case
    assert level(Principal("bob", "analyst", ())) == NONE


def test_star_grants_every_named_person_but_the_role_still_caps(lib):
    (lib / "finance" / "_folder.yaml").write_text("manage: '*'\n")
    assert level(VIEWER) == VIEW        # a folder never widens a role
    assert level(ANALYST) == PUBLISH
    assert level(Principal("someone", "analyst", ())) == PUBLISH


def test_an_empty_file_grants_nobody_but_admins(lib):
    (lib / "finance" / "_folder.yaml").write_text("")
    assert level(ANALYST) == NONE and level(ADMIN) == MANAGE and level(OPERATOR) == MANAGE


@pytest.mark.parametrize("content", [
    "veiw: [finance]",                  # a typo in a permission name
    "- finance",                        # not a mapping
    "view: 7",                          # not names
    "view: [finance, 3]",
    "view: ['']",
    "view: [unclosed",                  # not even YAML
    "\x00\x01\x02",
])
def test_a_malformed_file_fails_closed_without_raising(lib, caplog, content):
    """Catches a typo opening a folder to everyone, or crashing a request."""
    (lib / "finance" / "_folder.yaml").write_text(content)
    with caplog.at_level(logging.WARNING, logger="tracebi.permissions"):
        assert level(ANALYST) == NONE and level(VIEWER) == NONE
        assert level(ADMIN) == MANAGE and level(OPERATOR) == MANAGE
    assert "nobody but admins" in caplog.text
    assert level(ANALYST, "open/pack") == PUBLISH           # other folders are unaffected


def test_an_unreadable_file_is_malformed_not_absent(lib):
    """A _folder.yaml that cannot be decoded must not read as "no rule"."""
    (lib / "finance" / "_folder.yaml").write_bytes(b"\xff\xfe\x00bad")
    assert level(ANALYST) == NONE


def test_a_folder_file_is_read_again_when_it_changes(lib):
    f = lib / "finance" / "_folder.yaml"
    f.write_text("view: [finance]\n")
    assert level(ANALYST) == VIEW
    f.write_text("view: [somebody-else]\n")
    assert level(ANALYST) == NONE
    f.unlink()
    assert level(ANALYST) == PUBLISH


@pytest.mark.parametrize("name", [
    "../outside", "finance/../../outside", "finance/q3/../../open/pack", "/etc/passwd",
    "finance\\q3", "finance//pack", "", ".hidden/x", "_private/x", "finance/_folder.yaml/x",
])
def test_a_name_that_is_not_a_library_path_holds_nothing_for_anyone(lib, name):
    """Even an admin: a traversal is not a report, so nothing can be granted on it."""
    for who in (VIEWER, ANALYST, ADMIN, OPERATOR):
        assert granted_level(name, who) == NONE
        assert not can("view", name, who)


def test_purposes_map_to_levels_and_require_says_which_is_missing(lib):
    (lib / "finance" / "_folder.yaml").write_text("view: [finance]\nbuild: [builders]\n")
    can_view = Principal("v", "analyst", ("finance",))
    assert can("view", "finance/q3/pack", can_view) and can("source", "finance/q3/pack", can_view)
    assert not can("build", "finance/q3/pack", can_view)
    assert not can("schedule", "finance/q3/pack", can_view)
    with pytest.raises(NotPermitted, match="build permission"):
        require("build", "finance/q3/pack", can_view)
    with pytest.raises(NotPermitted, match="publish permission"):
        require("schedule", "finance/q3/pack", can_view)


def test_a_mount_root_file_covers_the_whole_mount(tmp_path, monkeypatch):
    mount = tmp_path / "board"
    (mount / "pack").mkdir(parents=True)
    (mount / "pack" / "report.json").write_text("{}")
    (mount / "_folder.yaml").write_text("view: [directors]\n")
    monkeypatch.setenv("TRACEBI_LIBRARY_MOUNTS", f"board:{mount}")
    assert granted_level("board/pack", Principal("d", "analyst", ("directors",))) == VIEW
    assert granted_level("board/pack", ANALYST) == NONE
    assert granted_level("elsewhere/pack", ANALYST) == PUBLISH       # no such mount: no rule


def test_the_current_actor_is_the_default_principal_and_groups_scope_like_it(lib):
    (lib / "finance" / "_folder.yaml").write_text("view: [finance]\n")
    assert can("view", "finance/q3/pack")                  # unattributed: the operator
    with actor("ann@example.com", role="analyst", groups=["finance"]):
        assert get_groups() == ("finance",) and can("view", "finance/q3/pack")
        with actor("bob@example.com", role="analyst"):
            assert get_groups() == () and not can("view", "finance/q3/pack")
        assert get_groups() == ("finance",)
    assert get_groups() == ()


# ── how groups reach the principal ─────────────────────────────────────────

def test_proxy_groups_come_only_from_the_configured_header(monkeypatch):
    """Catches a groups header trusted without being asked for, or dropped on
    the way from the proxy to the check."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tracebi.web.api.auth import ProxyHeaderAuthMiddleware

    app = FastAPI()
    app.add_middleware(ProxyHeaderAuthMiddleware, header="X-User")

    @app.get("/api/who")
    def who():
        return {"groups": list(get_groups())}

    client = TestClient(app)
    sent = {"X-User": "ann", "X-Groups": "finance, ops"}
    monkeypatch.delenv("TRACEBI_AUTH_GROUPS_HEADER", raising=False)
    assert client.get("/api/who", headers=sent).json() == {"groups": []}
    monkeypatch.setenv("TRACEBI_AUTH_GROUPS_HEADER", "X-Groups")
    assert client.get("/api/who", headers=sent).json() == {"groups": ["finance", "ops"]}
    # An appending proxy leaves a client's copy first; the last one is the proxy's.
    got = client.get("/api/who", headers=[("X-User", "ann"), ("X-Groups", "admins"),
                                          ("X-Groups", "finance")])
    assert got.json() == {"groups": ["finance"]}


def test_local_users_carry_groups_beside_the_role():
    """The password may contain ':' so groups sit with the role, and the old
    three-part form still parses."""
    pytest.importorskip("mcp")
    from tracebi.mcp_oauth import OAuthConfigError, parse_local_users

    got = parse_local_users("ann:analyst@finance+ops:pa:ss-word-1,vic:viewer:other-password")
    assert got["ann"] == ("analyst", "pa:ss-word-1", ("finance", "ops"))
    assert got["vic"] == ("viewer", "other-password", ())
    with pytest.raises(OAuthConfigError):
        parse_local_users("ann:superuser@finance:long-enough-pw")
