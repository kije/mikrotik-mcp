from typing import Optional
from ..connector import execute_mikrotik_command
from mcp.server.fastmcp import Context
from ..app import mcp, READ, annotate
from ..routeros import OutputFormat, print_resource


@mcp.tool(name="get_poe_monitor", annotations=annotate(READ, "PoE Monitor"))
async def mikrotik_get_poe_monitor(ctx: Context, interfaces: str) -> str:
    """Reads real-time Power-over-Ethernet (PoE) monitor data for one or more
    ethernet interfaces — PoE-out status, voltage, current, and power.

    Runs ``/interface ethernet poe monitor <interfaces> once``.

    Notes:
        interfaces: comma-separated ethernet interface name(s), e.g.
            "ether1" or "ether9-ap,ether10-ap,ether11-ap,ether12-ap"
    """
    await ctx.info(f"Reading PoE monitor for: {interfaces}")

    # `once` is required — without it the monitor streams continuously and the
    # command never returns (it would hang the SSH session).
    cmd = f"/interface ethernet poe monitor {interfaces} once"
    result = await execute_mikrotik_command(cmd, ctx)

    if not result or not result.strip():
        return (
            f"No PoE monitor data returned for: {interfaces}. "
            "The interface(s) may not exist or the device may not support PoE."
        )

    return f"POE MONITOR:\n\n{result}"


@mcp.tool(name="list_poe", annotations=annotate(READ, "List PoE"))
async def mikrotik_list_poe(
    ctx: Context,
    interface_filter: Optional[str] = None,
    proplist: Optional[str] = None,
    output: OutputFormat = "json",
) -> str:
    """Lists the Power-over-Ethernet (PoE) configuration of PoE-capable
    ethernet interfaces (PoE-out mode, priority).

    By default returns parsed JSON ``{count, records, documentation}`` where each
    record includes its stable ``.id`` (via ``show-ids``) for use in follow-up
    ``get`` calls.

    Notes:
        interface_filter: partial name match, e.g. "ether" matches ether1, ether2 …

    - ``proplist``: comma-separated fields to return.
    - ``output``: ``json`` (default, parsed) | ``terse`` (raw one-line records) |
      ``detail`` (verbose) | ``raw`` (legacy plain ``print``).

    Docs: https://manual.mikrotik.com/docs/hardware/poe-out
    """
    await ctx.info("Listing PoE configuration")

    filters = []
    if interface_filter:
        filters.append(f'name~"{interface_filter}"')

    return await print_resource(
        ctx,
        "/interface ethernet poe",
        where=filters,
        proplist=proplist,
        output=output,
        scope="poe",
        empty_message=(
            "No PoE-capable ethernet interfaces found. "
            "The device may not support PoE."
        ),
    )


@mcp.tool(name="get_poe_settings", annotations=annotate(READ, "PoE Settings"))
async def mikrotik_get_poe_settings(
    ctx: Context,
    name: str,
    proplist: Optional[str] = None,
    output: OutputFormat = "detail",
) -> str:
    """Gets the detailed PoE-out settings of a specific ethernet interface
    (PoE-out mode, priority, voltage, low/high thresholds, …).

    Notes:
        name: exact ethernet interface name, e.g. "ether1"

    - ``output``: ``detail`` (default, verbose text) | ``json`` (parsed) |
      ``terse`` (one-line) | ``raw``.
    - ``proplist``: comma-separated fields to return.

    Docs: https://manual.mikrotik.com/docs/hardware/poe-out
    """
    await ctx.info(f"Getting PoE settings for: {name}")

    return await print_resource(
        ctx,
        "/interface ethernet poe",
        where=[f'name="{name}"'],
        proplist=proplist,
        output=output,
        scope="poe",
        empty_message=f"No PoE settings found for interface '{name}'.",
    )
