from typing import Literal, Optional
from ..connector import execute_mikrotik_command
from mcp.server.fastmcp import Context
from ..app import mcp, READ, WRITE_IDEMPOTENT, annotate
from ..routeros import OutputFormat, print_resource


@mcp.tool(name="list_interfaces", annotations=annotate(READ, "List Interfaces"))
async def mikrotik_list_interfaces(
    ctx: Context,
    type_filter: Optional[Literal[
        "ether", "wg", "bridge", "vlan", "pppoe-out", "pppoe-server",
        "wifi", "wireless", "lte", "loopback", "sfp", "sfp-sfpplus"
    ]] = None,
    name_filter: Optional[str] = None,
    running_only: bool = False,
    disabled_only: bool = False,
    proplist: Optional[str] = None,
    output: OutputFormat = "json",
) -> str:
    """Lists all interfaces on the MikroTik device (ethernet, bridge, WireGuard,
    PPPoE, VLAN, WiFi, SFP, LTE, loopback, and any other type).

    By default returns parsed JSON ``{count, records, documentation}`` where each
    record includes its stable ``.id`` (via ``show-ids``) for use in follow-up
    calls.

    Notes:
        type_filter: RouterOS interface type e.g. "ether", "bridge", "vlan",
            "wg", "pppoe-out", "wifi", "lte", "loopback"
        name_filter: partial name match e.g. "ether" matches ether1, ether2 …
        proplist: comma-separated fields to return (e.g. "name,type").
        output: "json" (default, parsed) | "terse" (raw one-line records) |
            "detail" (verbose) | "raw" (legacy plain ``print``).

    Docs: https://manual.mikrotik.com/docs/cli-reference/interface/interface
    """
    await ctx.info("Listing all interfaces")

    filters = []
    if type_filter:
        filters.append(f'type="{type_filter}"')
    if name_filter:
        filters.append(f'name~"{name_filter}"')
    if running_only:
        filters.append("running=yes")
    if disabled_only:
        filters.append("disabled=yes")

    return await print_resource(
        ctx,
        "/interface",
        where=filters,
        proplist=proplist,
        output=output,
        scope="interfaces",
        empty_message="No interfaces found matching the criteria.",
    )


@mcp.tool(name="get_interface", annotations=annotate(READ, "Get Interface"))
async def mikrotik_get_interface(
    ctx: Context,
    name: str,
    proplist: Optional[str] = None,
    output: OutputFormat = "detail",
) -> str:
    """Gets detailed information about a specific interface by name.

    Notes:
        name: exact interface name e.g. "ether1", "bridge", "pppoe-out1", "wg0"
        output: "detail" (default, verbose text) | "json" (parsed) |
            "terse" (one-line) | "raw".
        proplist: comma-separated fields to return.

    Docs: https://manual.mikrotik.com/docs/cli-reference/interface/interface
    """
    await ctx.info(f"Getting interface details: name={name}")

    return await print_resource(
        ctx,
        "/interface",
        where=[f'name="{name}"'],
        proplist=proplist,
        output=output,
        scope="interfaces",
        empty_message=f"Interface '{name}' not found.",
    )


@mcp.tool(name="enable_interface", annotations=annotate(WRITE_IDEMPOTENT, "Enable Interface"))
async def mikrotik_enable_interface(ctx: Context, name: str) -> str:
    """Enables an interface on the MikroTik device.

    Notes:
        name: exact interface name e.g. "ether1", "bridge", "pppoe-out1"
    """
    await ctx.info(f"Enabling interface: name={name}")

    cmd = f'/interface enable [find name="{name}"]'
    result = await execute_mikrotik_command(cmd, ctx)

    if "failure:" in result.lower() or "error" in result.lower():
        return f"Failed to enable interface '{name}': {result}"

    # Verify the change
    check_cmd = f'/interface print detail where name="{name}"'
    details = await execute_mikrotik_command(check_cmd, ctx)

    if not details.strip():
        return f"Interface '{name}' not found."

    return f"Interface '{name}' enabled successfully:\n\n{details}"


@mcp.tool(name="disable_interface", annotations=annotate(WRITE_IDEMPOTENT, "Disable Interface"))
async def mikrotik_disable_interface(ctx: Context, name: str) -> str:
    """Disables an interface on the MikroTik device.

    Notes:
        name: exact interface name e.g. "ether1", "bridge", "pppoe-out1"
    """
    await ctx.info(f"Disabling interface: name={name}")

    cmd = f'/interface disable [find name="{name}"]'
    result = await execute_mikrotik_command(cmd, ctx)

    if "failure:" in result.lower() or "error" in result.lower():
        return f"Failed to disable interface '{name}': {result}"

    # Verify the change
    check_cmd = f'/interface print detail where name="{name}"'
    details = await execute_mikrotik_command(check_cmd, ctx)

    if not details.strip():
        return f"Interface '{name}' not found."

    return f"Interface '{name}' disabled successfully:\n\n{details}"
