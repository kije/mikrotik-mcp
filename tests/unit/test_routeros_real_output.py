"""Differential tests of the terse parsers against real RouterOS output.

``tests/fixtures/routeros-7.19.4.json`` holds, for each menu, the raw
``print terse show-ids`` text *and* the device's own exact serialisation of the
same records (``:serialize to=json [print as-value]``). Every value the device
reports must come out of :func:`parse_terse` identically — this is what caught
the lost ``.id`` column and the values truncated at their first space.
"""

import json
from pathlib import Path

import pytest

from mcp_mikrotik.routeros import (
    RouterOSError,
    parse_flag_legend,
    parse_log_terse,
    parse_terse,
)

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "routeros-7.19.4.json").read_text()
)
MENUS = FIXTURE["menus"]

# ``as-value`` renders these differently from the CLI without the value
# differing: durations as epoch dates (``1d`` → ``1970-01-02 00:00:00``), sizes
# and rates as plain numbers (``5M`` → ``5000000``), priorities in decimal.
REPRESENTATION_ONLY = {
    ("/ip firewall address-list", "timeout"),
    ("/ip dhcp-server", "lease-time"),
    ("/ip dns static", "ttl"),
    ("/queue tree", "bucket-size"),
    ("/queue tree", "burst-time"),
    ("/queue tree", "max-limit"),
    ("/queue type", "pcq-burst-time"),
    ("/queue type", "pcq-limit"),
    ("/queue type", "pcq-total-limit"),
    ("/interface bridge", "ageing-time"),
    ("/interface bridge", "forward-delay"),
    ("/interface bridge", "max-message-age"),
    ("/interface bridge", "mtu"),
    ("/interface bridge", "priority"),
    ("/ip service", "local"),
    # Computed pool statistics that terse output does not include at all.
    ("/ip pool", "available"),
    ("/ip pool", "total"),
    ("/ip pool", "used"),
}


def _as_cli(value):
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ",".join(_as_cli(v) for v in value)
    return str(value)


def _parse(menu):
    raw = MENUS[menu]
    return parse_terse(raw["terse"], legend=parse_flag_legend(raw["legend"]))


@pytest.mark.parametrize("menu", sorted(MENUS))
def test_terse_matches_device_serialisation(menu):
    parsed = {r[".id"]: r for r in _parse(menu)}
    truth = json.loads(MENUS[menu]["as_value"])
    assert set(parsed) == {t[".id"] for t in truth}

    for expected in truth:
        record = parsed[expected[".id"]]
        for key, value in expected.items():
            if (menu, key) in REPRESENTATION_ONLY:
                continue
            if key == "comment" and value == "":
                # as-value reports an unset comment as ""; terse omits it.
                assert key not in record
                continue
            assert record.get(key) == _as_cli(value), (menu, expected[".id"], key)


def test_values_with_spaces_and_quotes_survive():
    addr = {r[".id"]: r for r in _parse("/ip address")}["*2"]
    assert addr["comment"] == 'LAN side "main" = primary ncode'
    assert addr["address"] == "192.168.50.1/24"

    names = {r["name"] for r in _parse("/interface")}
    assert {"vlan 20", "br lan"} <= names

    iface = {r["name"]: r for r in _parse("/interface")}["ether1"]
    assert iface["last-link-up-time"].count(" ") == 1  # date *and* time


def test_valueless_blackhole_property():
    route = {r["dst-address"]: r for r in _parse("/ip route")}["10.98.0.0/16"]
    assert route["blackhole"] == "yes"
    assert route["routing-table"] == "main"
    assert route["immediate-gw"] == ""


def test_flags_decoded_from_separate_legend():
    routes = {r["dst-address"]: r for r in _parse("/ip route")}
    assert routes["0.0.0.0/0"]["_flags"] == ["dynamic", "active", "dhcp"]
    assert routes["10.97.0.0/16"]["_flags"] == ["disabled", "static"]

    addrs = {r[".id"]: r for r in _parse("/ip address")}
    assert addrs["*1"]["_flags"] == ["dynamic"]
    assert addrs["*3"]["_flags"] == ["disabled"]
    assert "_flags" not in addrs["*2"]


def test_wrapped_route_legend_is_fully_parsed():
    legend = parse_flag_legend(MENUS["/ip route"]["legend"])
    assert legend["A"] == "active"
    assert legend["y"] == "bgp-mpls-vpn"  # second line
    assert legend["+"] == "ecmp"  # third line, non-letter symbol


def test_log_terse_matches_device_serialisation():
    parsed = parse_log_terse(FIXTURE["log_terse"])
    truth = json.loads(FIXTURE["log_as_value"])
    assert len(parsed) == len(truth)
    for entry, expected in zip(parsed, truth):
        assert entry == {
            ".id": expected[".id"],
            "time": expected["time"],
            "topics": ",".join(expected["topics"]),
            "message": expected["message"],
        }


@pytest.mark.parametrize("command", sorted(FIXTURE["errors"]))
def test_device_errors_raise_instead_of_parsing_as_empty(command):
    output = FIXTURE["errors"][command]
    with pytest.raises(RouterOSError) as exc:
        parse_terse(output)
    assert str(exc.value) == output.strip()
