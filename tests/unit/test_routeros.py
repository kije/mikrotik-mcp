"""Unit tests for the shared RouterOS print/parse helpers."""

import asyncio
import json

import pytest

from mcp_mikrotik import routeros
from mcp_mikrotik.routeros import (
    build_print_command,
    build_where,
    parse_flag_legend,
    parse_terse,
    print_resource,
)


# ── build_where / build_print_command ──────────────────────────────────────

def test_build_where_empty():
    assert build_where([]) == ""
    assert build_where(["", "  "]) == ""


def test_build_where_joins_with_and():
    assert build_where(['interface="ether1"', "disabled=yes"]) == \
        ' where interface="ether1" and disabled=yes'


def test_build_print_default_is_terse_showids():
    cmd = build_print_command("/ip address")
    assert cmd == "/ip address print terse show-ids without-paging"


def test_build_print_with_proplist_and_where():
    cmd = build_print_command(
        "/ip address",
        where=['interface="ether1"'],
        proplist="address, interface ,network",
    )
    # ``where`` must be last: RouterOS reads the rest of the line as the filter.
    assert cmd == (
        "/ip address print terse show-ids without-paging "
        'proplist=address,interface,network where interface="ether1"'
    )


def test_build_print_has_no_limit():
    # ``print`` has no limit argument; after ``where`` a ``limit=N`` silently
    # becomes part of the filter and matches nothing.
    with pytest.raises(TypeError):
        build_print_command("/log", limit=10)


def test_build_print_detail_drops_terse():
    cmd = build_print_command("/ip address", detail=True)
    assert cmd == "/ip address print detail show-ids"


def test_build_print_count_only():
    cmd = build_print_command("/ip address", count_only=True, where=['address~"10."'])
    assert cmd == '/ip address print count-only where address~"10."'


def test_build_print_no_show_ids():
    cmd = build_print_command("/ip address", show_ids=False)
    assert cmd == "/ip address print terse without-paging"


# ── flag legend parsing ────────────────────────────────────────────────────

def test_parse_flag_legend():
    legend = parse_flag_legend(
        "Flags: X - disabled, I - invalid, D - dynamic\n 0 address=1.2.3.4/24"
    )
    assert legend == {"X": "disabled", "I": "invalid", "D": "dynamic"}


def test_parse_flag_legend_semicolons():
    legend = parse_flag_legend("Flags: D - dynamic; G - global, L - link-local")
    assert legend == {"D": "dynamic", "G": "global", "L": "link-local"}


# ── terse parsing ──────────────────────────────────────────────────────────

TERSE_SAMPLE = (
    "Flags: X - disabled, I - invalid, D - dynamic\n"
    " 0   .id=*1 address=192.168.88.1/24 network=192.168.88.0 interface=ether1\n"
    " 1 D .id=*2 address=10.0.0.2/24 network=10.0.0.0 interface=ether2\n"
)


def test_parse_terse_basic():
    records = parse_terse(TERSE_SAMPLE)
    assert len(records) == 2
    assert records[0][".id"] == "*1"
    assert records[0]["address"] == "192.168.88.1/24"
    assert records[0]["interface"] == "ether1"
    assert records[0]["_index"] == "0"
    assert "_flags" not in records[0]  # no flag letters on row 0


def test_parse_terse_decodes_flags():
    records = parse_terse(TERSE_SAMPLE)
    assert records[1]["_flags"] == ["dynamic"]
    assert records[1][".id"] == "*2"


def test_parse_terse_unquoted_value_with_spaces():
    # Terse output does not quote values; a value runs to the next ``key=``.
    out = '*3 X comment=hello "world" here address=1.1.1.1/32 interface=ether1\r\n\r\n'
    records = parse_terse(out, legend={"X": "disabled"})
    assert records == [{
        ".id": "*3",
        "comment": 'hello "world" here',
        "address": "1.1.1.1/32",
        "interface": "ether1",
        "_flags": ["disabled"],
    }]


def test_parse_terse_show_ids_column_is_the_id():
    records = parse_terse("*1A  D address=10.0.0.1/24\r\n*1B    address=10.0.0.2/24\r\n")
    assert [r[".id"] for r in records] == ["*1A", "*1B"]
    assert records[0]["_flags"] == ["D"]  # no legend given: raw symbol kept
    assert "_index" not in records[0]


def test_parse_terse_rejects_device_error():
    with pytest.raises(routeros.RouterOSError, match="bad command name"):
        parse_terse("bad command name addresss (line 1 column 5)\n")


def test_parse_flag_legend_wrapped_lines_and_symbols():
    legend = parse_flag_legend(
        "Flags: D - dynamic; X - disabled, I - inactive, A - active; \r\n"
        "c - connect, s - static, i - is-is, y - bgp-mpls-vpn; \r\n"
        "H - hw-offloaded; + - ecmp \r\n\r\n"
    )
    assert legend["A"] == "active"
    assert legend["i"] == "is-is"
    assert legend["y"] == "bgp-mpls-vpn"
    assert legend["+"] == "ecmp"


def test_parse_terse_empty_and_legend_only():
    assert parse_terse("") == []
    assert parse_terse("Flags: X - disabled, D - dynamic\n") == []


def test_parse_terse_combined_flag_letters():
    out = "Flags: X - disabled, D - dynamic\n 0 XD .id=*9 address=2.2.2.2/24\n"
    records = parse_terse(out)
    assert records[0]["_flags"] == ["disabled", "dynamic"]


# ── print_resource ─────────────────────────────────────────────────────────

def _patch_exec(monkeypatch, response):
    calls = []

    async def fake(cmd, _ctx=None):
        calls.append(cmd)
        return response

    monkeypatch.setattr(routeros, "execute_mikrotik_command", fake, raising=True)
    return calls


def test_print_resource_json(monkeypatch):
    calls = _patch_exec(monkeypatch, TERSE_SAMPLE)
    out = asyncio.run(print_resource(None, "/ip address", output="json", scope="ip_address"))
    payload = json.loads(out)
    assert payload["count"] == 2
    assert payload["records"][0]["address"] == "192.168.88.1/24"
    assert payload["documentation"].startswith("https://manual.mikrotik.com")
    # The legend query rides along in the same SSH exec.
    assert calls == ["/ip address print terse show-ids without-paging; /ip address print detail where false"]


def test_print_resource_json_decodes_flags_from_chained_legend(monkeypatch):
    # Real shape of ``<terse print>; <path> print detail where false``: the
    # records, then the legend.
    _patch_exec(
        monkeypatch,
        "*1 X address=1.2.3.4/24\r\n\r\nFlags: X - disabled, I - invalid; D - dynamic \r\n\r\n",
    )
    payload = json.loads(asyncio.run(print_resource(None, "/ip address")))
    assert payload["records"] == [{".id": "*1", "address": "1.2.3.4/24", "_flags": ["disabled"]}]


@pytest.mark.parametrize("response", [
    "Error: Failed to connect to MikroTik device",
    "input does not match any value of value-name\n",
    "expected end of command (line 1 column 42)\n",
])
def test_print_resource_json_raises_on_error(monkeypatch, response):
    _patch_exec(monkeypatch, response)
    with pytest.raises(routeros.RouterOSError):
        asyncio.run(print_resource(None, "/ip address", proplist="bogus"))


def test_print_resource_json_empty(monkeypatch):
    _patch_exec(monkeypatch, "Flags: X - disabled\n")
    out = asyncio.run(print_resource(None, "/ip address", output="json", scope="ip_address"))
    payload = json.loads(out)
    assert payload["count"] == 0
    assert payload["records"] == []


def test_print_resource_raw_uses_plain_print(monkeypatch):
    calls = _patch_exec(monkeypatch, "some output")
    out = asyncio.run(print_resource(None, "/ip address", output="raw"))
    assert out == "some output"
    assert calls[0] == "/ip address print"


def test_print_resource_terse_passes_through(monkeypatch):
    calls = _patch_exec(monkeypatch, TERSE_SAMPLE)
    out = asyncio.run(
        print_resource(None, "/ip address", output="terse", proplist="address")
    )
    assert out == TERSE_SAMPLE
    assert "proplist=address" in calls[0]


def test_print_resource_empty_message(monkeypatch):
    _patch_exec(monkeypatch, "")
    out = asyncio.run(
        print_resource(None, "/ip address", output="raw", empty_message="nothing here")
    )
    assert out == "nothing here"


# ── injection hardening ────────────────────────────────────────────────────

def test_ros_str_escapes_everything_routeros_interprets():
    assert routeros.ros_str('x"; /system reboot; "') == '"x\\"; /system reboot; \\""'
    assert routeros.ros_str("$[/system reboot]") == '"\\$[/system reboot]"'
    assert routeros.ros_str("a\\.b?\n") == '"a\\\\.b\\?\\n"'
    assert routeros.ros_str(10) == '"10"'


@pytest.mark.parametrize("proplist", [
    "address;/system reboot",
    "address,interface /system reboot",
    'address"',
])
def test_build_print_rejects_proplist_injection(proplist):
    with pytest.raises(routeros.ToolError, match="Invalid proplist"):
        build_print_command("/ip address", proplist=proplist)


def test_build_print_accepts_real_property_names():
    cmd = build_print_command("/ip route", proplist=".id,dst-address,gateway")
    assert cmd.endswith("proplist=.id,dst-address,gateway")


def test_parse_terse_valueless_property_vs_plain_value():
    records = parse_terse(
        "*1 As dst-address=10.98.0.0/16 routing-table=main blackhole distance=1\r\n"
        "*2 dst-address=10.0.0.0/8 type=blackhole comment=to blackhole\r\n"
    )
    assert records[0]["routing-table"] == "main"
    assert records[0]["blackhole"] == "yes"
    assert records[1]["type"] == "blackhole"  # RouterOS v6 style: a value
    assert records[1]["comment"] == "to blackhole"
    assert "blackhole" not in records[1]
