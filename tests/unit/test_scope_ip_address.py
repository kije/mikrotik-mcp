"""Unit tests for the ip_address scope after the print/parse conversion."""

import asyncio
import json


def _run(coro):
    return asyncio.run(coro)


TERSE = (
    "Flags: X - disabled, D - dynamic\n"
    " 0   .id=*1 address=192.168.88.1/24 network=192.168.88.0 interface=ether1\n"
)


def test_list_default_json(ctx, monkeypatch):
    from mcp_mikrotik.scope import ip_address as m

    calls = []

    async def fake(cmd, _ctx=None):
        calls.append(cmd)
        return TERSE

    monkeypatch.setattr(m, "execute_mikrotik_command", fake, raising=True)
    # print_resource imports the executor from routeros, patch there too.
    from mcp_mikrotik import routeros
    monkeypatch.setattr(routeros, "execute_mikrotik_command", fake, raising=True)

    out = _run(m.mikrotik_list_ip_addresses(ctx))
    assert calls[0] == "/ip address print terse show-ids without-paging"
    payload = json.loads(out)
    assert payload["count"] == 1
    assert payload["records"][0]["address"] == "192.168.88.1/24"
    assert payload["records"][0][".id"] == "*1"
    assert payload["documentation"].endswith("/docs/cli-reference/ip/address")


def test_list_with_filters_and_proplist(ctx, monkeypatch):
    from mcp_mikrotik.scope import ip_address as m
    from mcp_mikrotik import routeros

    calls = []

    async def fake(cmd, _ctx=None):
        calls.append(cmd)
        return TERSE

    monkeypatch.setattr(routeros, "execute_mikrotik_command", fake, raising=True)

    _run(m.mikrotik_list_ip_addresses(
        ctx, interface_filter="ether1", disabled_only=True,
        proplist="address,interface",
    ))
    cmd = calls[0]
    assert "proplist=address,interface" in cmd
    assert 'where interface="ether1" and disabled=yes' in cmd


def test_list_raw_output(ctx, monkeypatch):
    from mcp_mikrotik.scope import ip_address as m
    from mcp_mikrotik import routeros

    calls = []

    async def fake(cmd, _ctx=None):
        calls.append(cmd)
        return "plain text"

    monkeypatch.setattr(routeros, "execute_mikrotik_command", fake, raising=True)

    out = _run(m.mikrotik_list_ip_addresses(ctx, output="raw"))
    assert calls[0] == "/ip address print"
    assert out == "plain text"


def test_get_resolves_by_id_then_renders(ctx, monkeypatch):
    from mcp_mikrotik.scope import ip_address as m
    from mcp_mikrotik import routeros

    seen = []

    async def fake(cmd, _ctx=None):
        seen.append(cmd)
        if "count-only" in cmd:
            return "1"
        return TERSE

    monkeypatch.setattr(m, "execute_mikrotik_command", fake, raising=True)
    monkeypatch.setattr(routeros, "execute_mikrotik_command", fake, raising=True)

    out = _run(m.mikrotik_get_ip_address(ctx, address_id="*1", output="json"))
    assert seen[0] == '/ip address print count-only where .id="*1"'
    payload = json.loads(out)
    assert payload["count"] == 1


def test_get_not_found(ctx, monkeypatch):
    from mcp_mikrotik.scope import ip_address as m

    async def fake(cmd, _ctx=None):
        return "0"

    monkeypatch.setattr(m, "execute_mikrotik_command", fake, raising=True)
    out = _run(m.mikrotik_get_ip_address(ctx, address_id="nope"))
    assert "not found" in out
