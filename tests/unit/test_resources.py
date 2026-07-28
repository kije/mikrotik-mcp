"""MCP resources: registration and per-device routing."""

import asyncio
import json

from mcp_mikrotik import routeros
from mcp_mikrotik.app import mcp
from mcp_mikrotik.resources import CONFIG_SNAPSHOTS


def test_every_snapshot_has_default_and_per_device_uri():
    uris = {str(r.uri) for r in asyncio.run(mcp.list_resources())}
    templates = {t.uri_template for t in asyncio.run(mcp.list_resource_templates())}

    for uri, *_ in CONFIG_SNAPSHOTS + [("mikrotik://logs/recent",)]:
        assert uri in uris
        suffix = uri[len("mikrotik://"):]
        assert f"mikrotik://device/{{device}}/{suffix}" in templates


def test_device_template_targets_the_named_device(monkeypatch):
    seen = []

    async def fake(cmd, _ctx=None, device=None):
        seen.append((cmd, device))
        return ' 0   address=10.0.0.1/24 interface=ether1\n'

    monkeypatch.setattr(routeros, "execute_mikrotik_command", fake)

    contents = asyncio.run(mcp.read_resource("mikrotik://device/RouterB/ip/address"))
    payload = json.loads(list(contents)[0].content)
    assert payload["count"] == 1
    assert seen == [("/ip address print terse show-ids without-paging", "RouterB")]

    seen.clear()
    asyncio.run(mcp.read_resource("mikrotik://ip/address"))
    assert seen[0][1] is None
