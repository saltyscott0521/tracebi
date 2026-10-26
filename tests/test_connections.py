"""A connection's URL from its fields and back (``tracebi.connections``).

The app's form shows a SQL connection as fields and as one URL, the loader
builds the URL a structured file says, and a pasted URL with a password is
written as fields. Each case pins a mapping a person relies on without
reading it: a password that reaches the driver altered, a query option lost,
a ``${NAME}`` percent-encoded into a value that no longer resolves.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from tracebi.connections import build_url, parse_url

POSTGRES = {"host": "db.example.com", "port": "5432", "database": "crm", "user": "reader",
            "password": "s3cret", "ssl": "require", "connect_timeout": "10",
            "options": "application_name=tracebi&target_session_attrs=read-write"}
MYSQL = {"host": "10.0.0.7", "port": "3306", "database": "shop", "user": "app",
         "password": "s3cret", "ssl": "on", "connect_timeout": "5", "options": "charset=utf8mb4"}
SNOWFLAKE = {"account": "xy12345.eu-west-1", "user": "loader", "password": "s3cret",
             "warehouse": "COMPUTE_WH", "database": "SALES", "schema": "PUBLIC", "role": "READER"}


@pytest.mark.parametrize("ctype, fields", [
    ("postgres", POSTGRES), ("mysql", MYSQL), ("snowflake", SNOWFLAKE),
])
@pytest.mark.parametrize("password", [True, False])
@pytest.mark.parametrize("options", [True, False])
def test_fields_survive_the_url_both_ways(ctype, fields, password, options):
    """Catches a field the URL drops or renames (a lost sslmode, a port read
    as part of the host), with and without a password and query options."""
    f = {k: v for k, v in fields.items()
         if (password or k != "password")
         and (options or k not in ("options", "ssl", "connect_timeout", "warehouse", "role"))}
    url = build_url(ctype, f)
    assert parse_url(ctype, url) == f
    assert build_url(ctype, parse_url(ctype, url)) == url


@pytest.mark.parametrize("ctype", ["postgres", "mysql", "snowflake"])
def test_a_password_with_at_and_colon_reaches_the_driver_unchanged(ctype):
    """Catches a password written into the URL raw: '@' and ':' would split
    it into the host, and the driver would sign in with a different one."""
    base = {"postgres": POSTGRES, "mysql": MYSQL, "snowflake": SNOWFLAKE}[ctype]
    tricky = "p@ss:w/rd%?#&="
    url = build_url(ctype, {**base, "password": tricky})
    assert tricky not in url and "p%40ss%3Aw%2Frd" in url
    assert parse_url(ctype, url)["password"] == tricky
    if ctype != "snowflake":
        parsed = make_url(url)
        assert parsed.password == tricky and parsed.host == base["host"]


def test_a_reference_is_carried_whole_never_encoded():
    """Catches ${NAME} percent-encoded into %24%7B...: the URL the app shows
    and copies must name the variable, and a file's url must resolve."""
    url = build_url("postgres", {**POSTGRES, "password": "${TRACEBI_CRM_PASSWORD}"})
    assert url.startswith("postgresql+psycopg://reader:${TRACEBI_CRM_PASSWORD}@db.example.com:5432/crm?")
    assert parse_url("postgres", url)["password"] == "${TRACEBI_CRM_PASSWORD}"


def test_the_fields_become_the_query_the_driver_reads():
    """Catches ssl written under a name the driver ignores: postgres reads
    sslmode, the mysql dialect turns ssl_check_hostname into its ssl block."""
    assert dict(make_url(build_url("postgres", POSTGRES)).query) == {
        "sslmode": "require", "connect_timeout": "10", "application_name": "tracebi",
        "target_session_attrs": "read-write"}
    assert make_url(build_url("mysql", MYSQL)).query["ssl_check_hostname"] == "true"


@pytest.mark.parametrize("url", [
    "postgresql+psycopg2://u:p@h/db",       # another driver: kept as one URL
    "mysql+pymysql://u:p@h/db",             # another database
    "postgresql+psycopg:///db",             # no host (a socket)
    "not a url",
])
def test_a_url_the_fields_cannot_say_is_refused(url):
    """Catches a driver silently swapped for psycopg 3 when the fields write
    the URL again."""
    with pytest.raises(ValueError):
        parse_url("postgres", url)


def test_a_bare_postgresql_url_is_read_as_its_fields():
    assert parse_url("postgres", "postgresql://u@h/db") == {"user": "u", "host": "h", "database": "db"}
