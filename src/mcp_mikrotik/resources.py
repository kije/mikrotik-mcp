"""MCP *resources* for the MikroTik server.

Tools are *model-controlled* (the LLM decides to call them); resources are
*application-controlled* context a client can pull in deliberately. We expose
two kinds:

  * **Documentation** — ``mikrotik://docs`` and ``mikrotik://docs/{scope}``
    surface the official RouterOS manual references (see :mod:`.docs_refs`)
    without spending prompt tokens on every tool description.
  * **Configuration snapshots** — e.g. ``mikrotik://ip/address`` returns the
    device's current state as parsed JSON, reusing the same ``print`` +
    terse-parse pipeline the tools use. These are generated from
    :data:`CONFIG_SNAPSHOTS` so every configuration object gets one
    consistently.

The logs resource (``mikrotik://logs/recent``) is intentionally *pollable*
rather than push-subscribed: MCP resource subscriptions are a notify-then-
refetch mechanism with no ergonomic FastMCP support today, so a client that
wants fresh logs simply re-reads this resource. A true subscription remains a
future enhancement.
"""

import json
from typing import List, Tuple

from .app import mcp
from .docs_refs import DOCS_INTRO, SCOPE_DOCS, doc_for
from .routeros import print_resource


# ── Documentation resources ────────────────────────────────────────────────


@mcp.resource(
    "mikrotik://docs",
    name="MikroTik Documentation Index",
    description="Official RouterOS manual references for every configuration object this server exposes.",
    mime_type="application/json",
)
def docs_index() -> str:
    """Return the full scope→documentation index as JSON."""
    entries = [
        {
            "scope": scope,
            "title": doc.title,
            "url": doc.url,
            "markdown_url": doc.markdown_url,
        }
        for scope, doc in sorted(SCOPE_DOCS.items())
    ]
    return json.dumps({"introduction": DOCS_INTRO, "objects": entries}, ensure_ascii=False)


@mcp.resource(
    "mikrotik://docs/{scope}",
    name="MikroTik Object Documentation",
    description="Documentation reference for a single configuration object (e.g. 'ip_address').",
    mime_type="application/json",
)
def docs_for_scope(scope: str) -> str:
    """Return the documentation reference for a single scope, as JSON."""
    doc = doc_for(scope)
    if doc is None:
        return json.dumps(
            {"error": f"No documentation reference for scope '{scope}'.",
             "known_scopes": sorted(SCOPE_DOCS)},
            ensure_ascii=False,
        )
    return json.dumps(
        {"scope": scope, "title": doc.title, "url": doc.url, "markdown_url": doc.markdown_url},
        ensure_ascii=False,
    )


# ── Configuration-snapshot resources ───────────────────────────────────────
#
# (uri, RouterOS menu path, scope key, human name). Each becomes a read-only
# JSON resource that returns the live, parsed state of that configuration
# object — the resource counterpart of the corresponding ``list_*`` tool.
CONFIG_SNAPSHOTS: List[Tuple[str, str, str, str]] = [
    ("mikrotik://ip/address", "/ip address", "ip_address", "IP Addresses"),
    ("mikrotik://ipv6/address", "/ipv6 address", "ipv6_address", "IPv6 Addresses"),
    ("mikrotik://ip/pool", "/ip pool", "ip_pool", "IP Pools"),
    ("mikrotik://interface", "/interface", "interfaces", "Interfaces"),
    ("mikrotik://interface/vlan", "/interface vlan", "vlan", "VLAN Interfaces"),
    ("mikrotik://ip/firewall/filter", "/ip firewall filter", "firewall_filter", "Firewall Filter Rules"),
    ("mikrotik://ip/firewall/nat", "/ip firewall nat", "firewall_nat", "Firewall NAT Rules"),
    ("mikrotik://ip/dhcp-server", "/ip dhcp-server", "dhcp", "DHCP Servers"),
    ("mikrotik://ip/dns/static", "/ip dns static", "dns", "Static DNS Entries"),
    ("mikrotik://ip/route", "/ip route", "routes", "IP Routes"),
    ("mikrotik://queue/simple", "/queue simple", "queue", "Simple Queues"),
    ("mikrotik://user", "/user", "users", "Users"),
    ("mikrotik://interface/wireguard", "/interface wireguard", "wireguard", "WireGuard Interfaces"),
]


def _register_snapshot(uri: str, path: str, scope: str, name: str) -> None:
    """Register one config-snapshot resource.

    ``path``/``scope`` are captured from these function parameters (each call
    has its own), so the registered zero-argument handler binds the right
    values. A non-template resource URI requires a no-argument function, hence
    the closure rather than default parameters.
    """

    async def _snapshot() -> str:
        return await print_resource(None, path, output="json", scope=scope)

    _snapshot.__name__ = f"snapshot_{scope}"
    mcp.resource(
        uri,
        name=f"{name} (current)",
        description=f"Live snapshot of {name.lower()}, parsed to JSON.",
        mime_type="application/json",
    )(_snapshot)


for _uri, _path, _scope, _name in CONFIG_SNAPSHOTS:
    _register_snapshot(_uri, _path, _scope, _name)


# ── Logs (pollable; stands in for a push subscription) ──────────────────────


@mcp.resource(
    "mikrotik://logs/recent",
    name="Recent Logs",
    description="The most recent log entries as parsed JSON. Re-read to poll for new entries.",
    mime_type="application/json",
)
async def recent_logs() -> str:
    """Pollable logs resource (stand-in for a push subscription)."""
    return await print_resource(None, "/log", output="json", limit=50, scope="logs")
