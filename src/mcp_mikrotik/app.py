from importlib.metadata import PackageNotFoundError, version as _pkg_version

from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import Response

from .configured_mcp_server import ConfiguredMCPServer

try:
    _VERSION = _pkg_version("mcp-server-mikrotik")
except PackageNotFoundError:  # running from a source tree without an install
    _VERSION = "0.0.0.dev0"

# Sent once, in the initialize response, instead of being repeated in all 192
# tool descriptions — the same guidance costs ~60 tokens here rather than ~4k.
INSTRUCTIONS = (
    "This server manages one or more MikroTik devices. Every tool accepts an "
    "optional `device` argument: the title of the target device, as listed by "
    "`list_devices`. Omit it when a single device is configured; when several "
    "are, it is required. Titles match case-insensitively, and an omitted or "
    "unknown device returns an error naming the valid titles."
)

# mcp 2.x reports an empty serverInfo.version unless one is passed.
mcp = ConfiguredMCPServer("mcp-mikrotik", version=_VERSION, instructions=INSTRUCTIONS)

# ── Behaviour presets ──────────────────────────────────────────────────────
# These capture the *risk profile* of a tool (MCP spec §Tool Annotations).
# Always pass them through annotate() so every tool also carries a short
# human-readable title, which allows MCP clients to surface compact tool
# lists without re-rendering full descriptions — shrinking prompt context.
READ = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(destructive_hint=False, open_world_hint=False)
WRITE_IDEMPOTENT = ToolAnnotations(destructive_hint=False, idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE = ToolAnnotations(destructive_hint=True, idempotent_hint=True, open_world_hint=False)
DANGEROUS = ToolAnnotations(destructive_hint=True, open_world_hint=False)


def annotate(base: ToolAnnotations, title: str) -> ToolAnnotations:
    """Return a copy of *base* with a human-readable *title* attached.

    The ``title`` field (MCP spec 2025-03-26) gives MCP clients a short
    display name they can show in place of the full description, reducing
    the number of tokens sent to the LLM when listing available tools.

    Usage::

        @mcp.tool(name="get_dns_settings", annotations=annotate(READ, "DNS Settings"))
        async def mikrotik_get_dns_settings(ctx: Context) -> str: ...
    """
    return base.model_copy(update={"title": title})


# Only available on HTTP transports (sse, streamable-http)
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    return Response("OK", media_type="text/plain")


# Import scope modules to trigger @mcp.tool() registration
from mcp_mikrotik.scope import (  # noqa: F401, E402
    backup, dhcp, dns, firewall_address_list, firewall_filter, firewall_nat,
    interfaces, inventory, ip_address, ipv6_address, ipv6_firewall_filter, ip_pool, logs, poe, queue, safe_mode, routes, users, vlan, wireless, wireguard,
)

# Import resource definitions to trigger @mcp.resource() registration.
from mcp_mikrotik import resources  # noqa: F401, E402
