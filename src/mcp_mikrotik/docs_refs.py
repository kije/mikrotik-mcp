"""Canonical MikroTik documentation references for each configuration object.

Every scope this MCP server exposes maps to a page in the official RouterOS
manual. Centralising the mapping here (rather than sprinkling URLs through 175
tool docstrings, which would bloat the prompt context sent to the LLM) lets us:

  * attach a ``documentation`` link to structured tool responses, and
  * expose the whole index as MCP *resources* (``mikrotik://docs`` and
    ``mikrotik://docs/{scope}``) that a client can pull into context on demand.

The base host is ``manual.mikrotik.com`` (the docs entry point the user asked
for, https://manual.mikrotik.com/docs/introduction/). Each page is also
available as raw Markdown by appending ``.md`` — handy for an LLM client that
wants the page content rather than the rendered HTML.
"""

from typing import Dict, NamedTuple, Optional

DOCS_BASE = "https://manual.mikrotik.com"
DOCS_INTRO = f"{DOCS_BASE}/docs/introduction/"


class ScopeDoc(NamedTuple):
    """A single configuration object's documentation reference."""

    #: Human-readable title of the configuration object.
    title: str
    #: Documentation page path, relative to :data:`DOCS_BASE` (starts with "/").
    path: str

    @property
    def url(self) -> str:
        """Rendered HTML documentation URL."""
        return f"{DOCS_BASE}{self.path}"

    @property
    def markdown_url(self) -> str:
        """Raw-Markdown variant of the page (``…/foo.md``) for LLM ingestion."""
        return f"{DOCS_BASE}{self.path}.md"


# Keyed by the scope module name (``mcp_mikrotik.scope.<name>``) so a tool can
# resolve its own docs via ``doc_for(__name__)`` without hard-coding a string.
SCOPE_DOCS: Dict[str, ScopeDoc] = {
    "ip_address": ScopeDoc("IP Addressing", "/docs/cli-reference/ip/address"),
    "ipv6_address": ScopeDoc("IPv6 Addressing", "/docs/cli-reference/ipv6/address"),
    "ip_pool": ScopeDoc("IP Pools", "/docs/cli-reference/ip/pool"),
    "dhcp": ScopeDoc("DHCP Server & Client", "/docs/cli-reference/ip/dhcp-server"),
    "dns": ScopeDoc("DNS", "/docs/cli-reference/ip/dns"),
    "firewall_filter": ScopeDoc("Firewall Filter", "/docs/cli-reference/ip/firewall/filter"),
    "firewall_nat": ScopeDoc("Firewall NAT", "/docs/cli-reference/ip/firewall/nat"),
    "interfaces": ScopeDoc("Interfaces", "/docs/cli-reference/interface/interface"),
    "vlan": ScopeDoc("VLAN Interfaces", "/docs/cli-reference/interface/vlan"),
    "wireless": ScopeDoc("Wireless / WiFi", "/docs/cli-reference/interface/wifi"),
    "wireguard": ScopeDoc("WireGuard", "/docs/cli-reference/interface/wireguard"),
    "routes": ScopeDoc("IP Routes", "/docs/cli-reference/ip/route"),
    "queue": ScopeDoc("Queues (QoS)", "/docs/cli-reference/queue/simple"),
    "poe": ScopeDoc("Power over Ethernet (PoE-out)", "/docs/hardware/poe-out"),
    "users": ScopeDoc("User Management", "/docs/cli-reference/user"),
    "logs": ScopeDoc("Logging", "/docs/cli-reference/log"),
    "backup": ScopeDoc("Backup & Configuration Export", "/docs/cli-reference/system/backup"),
    "safe_mode": ScopeDoc("Safe Mode", "/docs/introduction/"),
}


def _normalise(scope: str) -> str:
    """Map a value like ``mcp_mikrotik.scope.ip_address`` to ``ip_address``."""
    return scope.rsplit(".", 1)[-1]


def doc_for(scope: str) -> Optional[ScopeDoc]:
    """Return the :class:`ScopeDoc` for a scope name (or dotted module path).

    Accepts either the bare scope key (``"ip_address"``) or a module's
    ``__name__`` (``"mcp_mikrotik.scope.ip_address"``) so a scope can look up
    its own docs with ``doc_for(__name__)``.
    """
    return SCOPE_DOCS.get(_normalise(scope))


def doc_url(scope: str) -> Optional[str]:
    """Convenience: the rendered documentation URL for a scope, or ``None``."""
    doc = doc_for(scope)
    return doc.url if doc else None
