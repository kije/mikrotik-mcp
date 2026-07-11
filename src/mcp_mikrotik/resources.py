"""MCP *resources* for the MikroTik server.

Tools are *model-controlled* (the LLM decides to call them); resources are
*application-controlled* context a client can pull in deliberately. We expose
two kinds:

  * **Documentation** — ``mikrotik://docs`` and ``mikrotik://docs/{scope}``
    surface the official RouterOS manual references (see :mod:`.docs_refs`)
    without spending prompt tokens on every tool description.
  * **Configuration snapshots** — e.g. ``mikrotik://ip/address`` returns the
    device's current state as parsed JSON, reusing the same ``print`` +
    terse-parse pipeline the tools use.

The logs resource (``mikrotik://logs/recent``) is intentionally *pollable*
rather than push-subscribed: MCP resource subscriptions are a notify-then-
refetch mechanism with no ergonomic FastMCP support today, so a client that
wants fresh logs simply re-reads this resource. A true subscription remains a
future enhancement.
"""

import json

from .app import mcp
from .docs_refs import DOCS_INTRO, SCOPE_DOCS, doc_for
from .routeros import print_resource


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


@mcp.resource(
    "mikrotik://ip/address",
    name="IP Addresses (current)",
    description="Live snapshot of configured IPv4 addresses, parsed to JSON.",
    mime_type="application/json",
)
async def ip_address_snapshot() -> str:
    """Config-snapshot resource: current IP addresses as parsed JSON."""
    return await print_resource(None, "/ip address", output="json", scope="ip_address")


@mcp.resource(
    "mikrotik://logs/recent",
    name="Recent Logs",
    description="The most recent log entries as parsed JSON. Re-read to poll for new entries.",
    mime_type="application/json",
)
async def recent_logs() -> str:
    """Pollable logs resource (stand-in for a push subscription)."""
    return await print_resource(None, "/log", output="json", limit=50, scope="logs")
