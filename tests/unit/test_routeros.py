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


def test_build_print_with_proplist_and_where_and_limit():
    cmd = build_print_command(
        "/ip address",
        where=['interface="ether1"'],
        proplist="address, interface ,network",
        limit=10,
    )
    assert cmd == (
        "/ip address print terse show-ids without-paging "
        'proplist=address,interface,network where interface="ether1" limit=10'
    )


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


def test_parse_terse_quoted_value_with_spaces():
    out = (
        "Flags: X - disabled\n"
        ' 0 X .id=*3 address=1.1.1.1/32 comment="hello world here" interface=ether1\n'
    )
    records = parse_terse(out)
    assert records[0]["comment"] == "hello world here"
    assert records[0]["interface"] == "ether1"
    assert records[0]["_flags"] == ["disabled"]


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
    assert calls[0] == "/ip address print terse show-ids without-paging"


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
