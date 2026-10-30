"""The workbench inside the agent (MCP Apps), against a scaffolded workspace:

    the authoring tools name ui://tracebi/workbench → a host that negotiated
    Apps lists the panel's two tools, one that did not sees the agent's own →
    the resource is one HTML file → a host page (this test, playing Claude's
    part of the bridge) opens it beside a draft with no network → the draft's
    figure shows → write_draft_file changes the page and the panel follows
    without a click → the person clicks the figure and pins a note → the agent
    is told, and workbench_state(draft=true) lists the pin

The bridge is the ext-apps JSON-RPC over postMessage; the host page answers
``tools/call`` by calling the gateway's own functions, as a host proxies the
call to the server.
"""

from __future__ import annotations

import json

from tests.e2e.conftest import run_cli

PATH = "sample_model/desk_brief"

_KPI = ('<div class="tb-kpi tb-kpi--lead" data-tb-figure="value" id="kpi-revenue" '
        'data-tb-binding="totals" data-tb-cell="revenue"><span class="tb-kpi-label">'
        '{label}</span><span class="tb-kpi-value"></span></div>')


def page(label: str, extra: str = "") -> str:
    return ('<!doctype html><html><head><title>Desk Brief</title></head><body>'
            f'<div class="tb-grid">{_KPI.format(label=label)}{extra}</div></body></html>')


#: The host's half of the bridge: answer the handshake, hand the panel the tool
#: call that opened it, proxy tools/call to Python, record ui/message.
HOST = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%%} iframe{border:0;width:100%%;height:100%%;display:block}
</style></head><body><iframe id="app" sandbox="allow-scripts"></iframe><script>
window.__messages = []; window.__context = []; window.__init = null; window.__sizes = [];
window.__replies = {};
var app = document.getElementById('app');
function reply(id, result) { app.contentWindow.postMessage({jsonrpc: '2.0', id: id, result: result}, '*'); }
window.addEventListener('message', function (e) {
  var m = e.data;
  if (e.source !== app.contentWindow || !m || m.jsonrpc !== '2.0') return;
  if (m.id !== undefined && m.method === undefined) { window.__replies[m.id] = m; return; }
  if (m.method === 'ui/initialize') window.__init = m.params;
  if (m.method === 'ui/initialize') reply(m.id, {protocolVersion: '2026-01-26',
      hostInfo: {name: 'test-host', version: '1'}, hostCapabilities: {},
      hostContext: {theme: %(theme)s, displayMode: 'inline', availableDisplayModes: ['inline', 'fullscreen']}});
  else if (m.method === 'ui/notifications/initialized') {
    /* Streaming arguments first, as a host may send them; then the whole call. */
    app.contentWindow.postMessage({jsonrpc: '2.0', method: 'ui/notifications/tool-input-partial',
                                   params: {arguments: {kind: 'reports'}}}, '*');
    app.contentWindow.postMessage({jsonrpc: '2.0', method: 'ui/notifications/tool-input',
                                   params: {arguments: %(arguments)s}}, '*');
  }
  else if (m.method === 'ui/notifications/size-changed') window.__sizes.push(m.params);
  else if (m.method === 'tools/call')
    window.hostCall(m.params.name, m.params.arguments).then(function (r) {
      reply(m.id, {content: [{type: 'text', text: JSON.stringify(r)}], structuredContent: r}); });
  else if (m.method === 'ui/message') { window.__messages.push(m.params); reply(m.id, {}); }
  else if (m.method === 'ui/update-model-context') { window.__context.push(m.params); reply(m.id, {}); }
  else if (m.id !== undefined) reply(m.id, {});
});
app.srcdoc = %(html)s;
</script></body></html>"""


def open_panel(browser, html: str, arguments: dict, calls: list, *, theme="light",
               size=(1200, 800)):
    """The panel in a host page, with every network request refused and counted."""
    from tracebi import mcp_server as gw

    tools = {"workbench_view": gw.gateway_workbench_view,
             "workbench_pin": gw.gateway_workbench_pin}
    context = browser.new_context(viewport={"width": size[0], "height": size[1]})
    page_ = context.new_page()
    page_.set_default_timeout(30_000)
    errors, requests = [], []
    page_.on("pageerror", lambda exc: errors.append(str(exc)))
    context.route("**/*", lambda route: (requests.append(route.request.url), route.abort()))

    def host_call(name, args):
        calls.append((name, args))
        return tools[name](**args)

    page_.expose_function("hostCall", host_call)
    page_.set_content(HOST % {"theme": json.dumps(theme), "arguments": json.dumps(arguments),
                              "html": json.dumps(html).replace("</", "<\\/")})
    return page_, errors, requests


def report_frame(page_):
    """The report's own frame, nested inside the panel's."""
    app = page_.frame_locator("#app")
    return app, app.frame_locator("#page")


def test_the_workbench_opens_beside_the_chat_follows_edits_and_takes_pins(scaffolded):
    import asyncio

    from mcp.client import Client
    from mcp.client.extension import advertise
    from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID

    from tests.e2e.test_reference_project import _browser
    from tracebi import mcp_server as gw
    from tracebi.workbench_app import APP_URI

    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out

    # 1. The authoring tools open the panel; the panel's own tools are for it.
    server = gw.build_server(token=None)
    apps = advertise(EXTENSION_ID, {"mimeTypes": [APP_MIME_TYPE]})

    async def listing(extensions):
        async with Client(server, extensions=extensions) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            resource = await client.read_resource(APP_URI) if extensions else None
            return tools, resource

    with_apps, resource = asyncio.run(listing([apps]))
    for name in ("preview_draft", "workbench_state", "build_report"):
        assert with_apps[name].meta["ui"] == {"resourceUri": APP_URI}, name
    for name in ("workbench_view", "workbench_pin"):
        assert with_apps[name].meta["ui"]["visibility"] == ["app"], name
    without, _ = asyncio.run(listing(None))
    assert set(with_apps) - set(without) == {"workbench_view", "workbench_pin"}
    [content] = resource.contents
    assert content.mime_type == APP_MIME_TYPE
    html = content.text
    assert "connect-src 'none'" in html and "http" not in html.split("<script>", 1)[1]

    # 2. The agent starts a draft and writes its first page.
    started = gw.gateway_start_draft("reports", PATH)
    assert started["ok"] is True, started
    fact = gw.gateway_model_info("sample_model")["facts"][0]["name"]
    stamped = gw.gateway_query("sample_model", fact, ["revenue"])
    declared = {"name": "Desk Brief", "data": {"totals": stamped["binding"]}}
    for name, text in (("report.json", json.dumps(declared)), ("template.html", page("Revenue"))):
        assert gw.gateway_write_draft_file("reports", PATH, name, text)["ok"] is True
    preview = gw.gateway_preview_draft("reports", PATH)
    assert preview["ok"] is True and preview["url"].endswith(f"/drafts/agent/reports/{PATH}")

    # 3. The host opens the panel for that preview_draft call. No network at all.
    pw, browser = _browser()
    calls: list = []
    try:
        page_, errors, requests = open_panel(browser, html, {"kind": "reports", "path": PATH}, calls)
        app, report = report_frame(page_)
        value = report.locator("#kpi-revenue .tb-kpi-value")
        value.wait_for()
        assert app.locator("#title").inner_text() == PATH
        assert app.locator("#mode").inner_text() == "Draft"
        assert "kpi-revenue" in app.locator("#figs").inner_text()
        assert "model query" in app.locator("#figs").inner_text()
        assert value.inner_text().strip(), "the KPI shows the query's number"
        assert report.locator("#kpi-revenue .tb-kpi-label").inner_text() == "Revenue"
        # The handshake declares the modes the host may switch to, and the panel
        # tells the host how big it wants to be (the report's height, at least).
        init = page_.evaluate("window.__init")
        assert init["appCapabilities"]["availableDisplayModes"] == ["inline", "fullscreen"]
        page_.wait_for_function("window.__sizes.length > 0")
        size = page_.evaluate("window.__sizes[window.__sizes.length - 1]")
        assert size["width"] == 1200 and size["height"] > 300, size

        # 4. Live: the agent edits; the panel follows with no one touching it.
        extra = ('<p data-tb-figure="value" id="kpi-orders" data-tb-binding="totals" '
                 'data-tb-cell="revenue"></p>')
        assert gw.gateway_write_draft_file("reports", PATH, "template.html",
                                           page("Revenue, all regions", extra))["ok"] is True
        report.locator("#kpi-revenue .tb-kpi-label").filter(
            has_text="Revenue, all regions").wait_for()
        app.locator("#figs", has_text="kpi-orders").wait_for()
        app.locator("#feed", has_text="Wrote template.html in the draft").wait_for()
        assert any(a.get("since") for n, a in calls if n == "workbench_view"), "it polls"

        # 5. The person clicks the figure and pins a note; the agent is told.
        report.locator("#kpi-revenue").click()
        app.locator("#selected", has_text="kpi-revenue").wait_for()
        app.locator("#note").fill("this looks off: should exclude refunds")
        app.locator("#pinBtn").click()
        app.locator("#pinMsg", has_text="your agent was told").wait_for()
        [told] = page_.evaluate("window.__messages")
        assert told["role"] == "user" and told["content"]["type"] == "text"   # one block
        assert told["content"]["text"].startswith(
            f"Pinned on kpi-revenue in the draft of {PATH}: this looks off")
        assert page_.evaluate("window.__context")[0]["content"][0]["text"].endswith(
            f"selected figure kpi-revenue of the draft of {PATH}.")
        app.locator("#pins", has_text="should exclude refunds").wait_for()

        # 6. Teardown is a request the panel answers; the poll stops with it.
        page_.evaluate("""document.getElementById('app').contentWindow.postMessage(
            {jsonrpc: '2.0', id: 9001, method: 'ui/resource-teardown', params: {}}, '*')""")
        page_.wait_for_function("window.__replies[9001] !== undefined")
        polls = sum(n == "workbench_view" for n, _ in calls)
        page_.wait_for_timeout(4500)
        assert sum(n == "workbench_view" for n, _ in calls) == polls, "the poll outlived teardown"
        assert errors == [] and requests == [], (errors, requests)
        page_.context.close()
    finally:
        browser.close()
        pw.stop()

    # 7. Where the agent reads it: workbench_state on the draft, and resolve_pin.
    state = gw.gateway_workbench_state(report=PATH, draft=True)
    assert [(p["id"], p["note"]) for p in state["pins"]] == [
        ("kpi-revenue", "this looks off: should exclude refunds")]
    assert state["workbench_url"] == preview["url"]
    assert gw.gateway_resolve_pin(PATH, "kpi-revenue", "now excludes refunds", draft=True)["ok"]
    assert gw.gateway_workbench_state(report=PATH, draft=True)["pins"] == []
    # The panel writes pins only: a figure id that is no id is refused.
    refused = gw.gateway_workbench_pin(PATH, figure="../../x", note="n", draft=True)
    assert refused["ok"] is False
