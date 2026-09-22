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
    #: Documentation page path, relative to :data:`DOCS_BASE` (starts with
    #: "/", no trailing slash).
    path: str
    #: ``True`` for a section page — a menu with sub-menus (``/ip/pool``), whose
    #: Markdown source is ``…/pool/pool.md`` rather than ``…/pool.md``.
    section: bool = False

    @property
    def url(self) -> str:
        """Rendered HTML documentation URL.

        Always with a trailing slash: without one the site answers with a
        redirect to the plain-``http://`` URL.
        """
        return f"{DOCS_BASE}{self.path}/"

    @property
    def markdown_url(self) -> str:
        """Raw-Markdown variant of the page, for LLM ingestion."""
        if self.section:
            return f"{DOCS_BASE}{self.path}/{self.path.rsplit('/', 1)[-1]}.md"
        return f"{DOCS_BASE}{self.path}.md"


# Keyed by the scope module name (``mcp_mikrotik.scope.<name>``) so a tool can
# resolve its own docs via ``doc_for(__name__)`` without hard-coding a string.
# Paths follow https://manual.mikrotik.com/sitemap.xml; ``test_docs_refs``
# has an opt-in check that every URL resolves.
_CLI = "/docs/cli-reference"
SCOPE_DOCS: Dict[str, ScopeDoc] = {
    "ip_address": ScopeDoc("IP Addressing", f"{_CLI}/ip/address"),
    "ipv6_address": ScopeDoc("IPv6 Addressing", f"{_CLI}/ipv6/address"),
    "ip_pool": ScopeDoc("IP Pools", f"{_CLI}/ip/pool", section=True),
    "dhcp": ScopeDoc("DHCP Server & Client", f"{_CLI}/ip/dhcp-server", section=True),
    "dns": ScopeDoc("DNS", f"{_CLI}/ip/dns", section=True),
    "firewall_filter": ScopeDoc("Firewall Filter", f"{_CLI}/ip/firewall/filter", section=True),
    "firewall_nat": ScopeDoc("Firewall NAT", f"{_CLI}/ip/firewall/nat", section=True),
    "interfaces": ScopeDoc("Interfaces", f"{_CLI}/interface", section=True),
    "vlan": ScopeDoc("VLAN Interfaces", f"{_CLI}/interface/vlan"),
    "wireless": ScopeDoc("Wireless / WiFi", f"{_CLI}/interface/wifi", section=True),
    "wireguard": ScopeDoc("WireGuard", f"{_CLI}/interface/wireguard", section=True),
    "routes": ScopeDoc("IP Routes", f"{_CLI}/ip/route", section=True),
    "queue": ScopeDoc("Simple Queues (QoS)", f"{_CLI}/queue/simple", section=True),
    "queue_tree": ScopeDoc("Queue Trees (QoS)", f"{_CLI}/queue/tree", section=True),
    "queue_type": ScopeDoc("Queue Types", f"{_CLI}/queue/type"),
    "poe": ScopeDoc("Power over Ethernet (PoE-out)", f"{_CLI}/interface/ethernet/poe", section=True),
    "users": ScopeDoc("User Management", f"{_CLI}/user", section=True),
    "logs": ScopeDoc("Logging", f"{_CLI}/log"),
    "backup": ScopeDoc("Backup & Configuration Export", f"{_CLI}/system/backup/save"),
    "safe_mode": ScopeDoc("Safe Mode", f"{_CLI}/safe-mode"),
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
