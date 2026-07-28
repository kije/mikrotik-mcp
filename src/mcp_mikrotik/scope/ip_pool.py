from typing import Optional, List

from mcp.server.fastmcp import Context

from ..connector import execute_mikrotik_command
from ..app import mcp, READ, WRITE, WRITE_IDEMPOTENT, DESTRUCTIVE, annotate
from ..routeros import OutputFormat, print_resource

@mcp.tool(name="create_ip_pool", annotations=annotate(WRITE, "Add IP Pool"))
async def mikrotik_create_ip_pool(
    ctx: Context,
    name: str,
    ranges: str,
    next_pool: Optional[str] = None,
    comment: Optional[str] = None
) -> str:
    """Creates an IP pool with the given address ranges on the MikroTik device.

    Notes:
        ranges: hyphen-separated range(s) e.g. "192.168.1.1-192.168.1.100"
            Multiple ranges comma-separated: "10.0.0.1-10.0.0.50,10.0.0.100-10.0.0.120"
    """
    await ctx.info(f"Creating IP pool: name={name}, ranges={ranges}")

    # Build the command
    cmd = f"/ip pool add name={name} ranges={ranges}"

    # Add optional parameters
    if next_pool:
        cmd += f' next-pool="{next_pool}"'

    if comment:
        cmd += f' comment="{comment}"'

    result = await execute_mikrotik_command(cmd, ctx)

    # Check if creation was successful
    if result.strip():
        # MikroTik returns the ID of created item on success
        if "*" in result or result.strip().isdigit():
            # Success - get the details
            details_cmd = f'/ip pool print detail where name="{name}"'
            details = await execute_mikrotik_command(details_cmd, ctx)

            if details.strip():
                return f"IP pool created successfully:\n\n{details}"
            else:
                return f"IP pool created with ID: {result}"
        else:
            # Error occurred
            return f"Failed to create IP pool: {result}"
    else:
        # No output might mean success, let's check
        details_cmd = f'/ip pool print detail where name="{name}"'
        details = await execute_mikrotik_command(details_cmd, ctx)

        if details.strip():
            return f"IP pool created successfully:\n\n{details}"
        else:
            return "IP pool creation completed but unable to verify."

@mcp.tool(name="list_ip_pools", annotations=annotate(READ, "List IP Pools"))
async def mikrotik_list_ip_pools(
    ctx: Context,
    name_filter: Optional[str] = None,
    ranges_filter: Optional[str] = None,
    proplist: Optional[str] = None,
    output: OutputFormat = "json",
) -> str:
    """Lists IP pools on the MikroTik device.

    By default returns parsed JSON ``{count, records, documentation}`` where each
    record includes its stable ``.id`` (via ``show-ids``) for use in follow-up
    ``get``/``remove`` calls.

    - ``proplist``: comma-separated fields to return (e.g. ``"name,ranges"``)
      so the client fetches only what it needs.
    - ``output``: ``json`` (default, parsed) | ``terse`` (raw one-line records) |
      ``detail`` (verbose) | ``raw`` (legacy plain ``print``).

    Note: per-pool used-address counts are available via ``list_ip_pool_used``
    or ``get_ip_pool``.

    Docs: https://manual.mikrotik.com/docs/cli-reference/ip/pool
    """
    await ctx.info(f"Listing IP pools with filters: name={name_filter}, ranges={ranges_filter}")

    filters = []
    if name_filter:
        filters.append(f'name~"{name_filter}"')
    if ranges_filter:
        filters.append(f'ranges~"{ranges_filter}"')

    return await print_resource(
        ctx,
        "/ip pool",
        where=filters,
        proplist=proplist,
        output=output,
        scope="ip_pool",
        empty_message="No IP pools found matching the criteria.",
    )

@mcp.tool(name="get_ip_pool", annotations=annotate(READ, "Get IP Pool"))
async def mikrotik_get_ip_pool(
    ctx: Context,
    name: str,
    proplist: Optional[str] = None,
    output: OutputFormat = "detail",
) -> str:
    """Gets detailed information about a specific IP pool by name.

    - ``output``: ``detail`` (default, verbose text) | ``json`` (parsed) |
      ``terse`` (one-line) | ``raw``.
    - ``proplist``: comma-separated fields to return.

    Note: per-pool used-address counts are available via ``list_ip_pool_used``.

    Docs: https://manual.mikrotik.com/docs/cli-reference/ip/pool
    """
    await ctx.info(f"Getting IP pool details: name={name}")

    return await print_resource(
        ctx,
        "/ip pool",
        where=[f'name="{name}"'],
        proplist=proplist,
        output=output,
        scope="ip_pool",
        empty_message=f"IP pool '{name}' not found.",
    )

@mcp.tool(name="update_ip_pool", annotations=annotate(WRITE_IDEMPOTENT, "Update IP Pool"))
async def mikrotik_update_ip_pool(
    ctx: Context,
    name: str,
    new_name: Optional[str] = None,
    ranges: Optional[str] = None,
    next_pool: Optional[str] = None,
    comment: Optional[str] = None
) -> str:
    """Updates an existing IP pool's name, ranges, or next-pool reference.

    Notes:
        ranges: hyphen-separated range(s) e.g. "192.168.1.1-192.168.1.100"
            Multiple ranges comma-separated: "10.0.0.1-10.0.0.50,10.0.0.100-10.0.0.120"
        Pass "" for next_pool to clear it.
    """
    await ctx.info(f"Updating IP pool: name={name}")

    # Build the command
    cmd = f'/ip pool set [find name="{name}"]'

    # Add parameters to update
    updates = []
    if new_name:
        updates.append(f'name={new_name}')
    if ranges:
        updates.append(f'ranges={ranges}')
    if next_pool is not None:
        if next_pool == "":
            updates.append('!next-pool')
        else:
            updates.append(f'next-pool="{next_pool}"')
    if comment is not None:
        updates.append(f'comment="{comment}"')

    if not updates:
        return "No updates specified."

    cmd += " " + " ".join(updates)

    result = await execute_mikrotik_command(cmd, ctx)

    # Check if update was successful
    if "failure:" in result.lower() or "error" in result.lower():
        return f"Failed to update IP pool: {result}"

    # Get the updated pool details
    details_name = new_name if new_name else name
    details_cmd = f'/ip pool print detail where name="{details_name}"'
    details = await execute_mikrotik_command(details_cmd, ctx)

    return f"IP pool updated successfully:\n\n{details}"

@mcp.tool(name="remove_ip_pool", annotations=annotate(DESTRUCTIVE, "Remove IP Pool"))
async def mikrotik_remove_ip_pool(ctx: Context, name: str) -> str:
    """Removes an IP pool from the MikroTik device (fails if pool is in use)."""
    await ctx.info(f"Removing IP pool: name={name}")

    # First check if the pool exists
    check_cmd = f'/ip pool print count-only where name="{name}"'
    count = await execute_mikrotik_command(check_cmd, ctx)

    if count.strip() == "0":
        return f"IP pool '{name}' not found."

    # Check if pool is in use
    pool_used_cmd = f'/ip pool used print count-only where pool="{name}"'
    used_count = await execute_mikrotik_command(pool_used_cmd, ctx)

    if used_count.strip() != "0":
        return f"Cannot remove IP pool '{name}': {used_count.strip()} addresses are currently in use."

    # Check if pool is referenced by DHCP servers
    dhcp_check_cmd = f'/ip dhcp-server print count-only where address-pool="{name}"'
    dhcp_count = await execute_mikrotik_command(dhcp_check_cmd, ctx)

    if dhcp_count.strip() != "0":
        return f"Cannot remove IP pool '{name}': It is used by {dhcp_count.strip()} DHCP server(s)."

    # Remove the pool
    cmd = f'/ip pool remove [find name="{name}"]'
    result = await execute_mikrotik_command(cmd, ctx)

    if "failure:" in result.lower() or "error" in result.lower():
        return f"Failed to remove IP pool: {result}"

    return f"IP pool '{name}' removed successfully."

@mcp.tool(name="list_ip_pool_used", annotations=annotate(READ, "List IP Pool Used"))
async def mikrotik_list_ip_pool_used(
    ctx: Context,
    pool_name: Optional[str] = None,
    address_filter: Optional[str] = None,
    mac_filter: Optional[str] = None,
    info_filter: Optional[str] = None,
    proplist: Optional[str] = None,
    output: OutputFormat = "json",
) -> str:
    """Lists currently used (allocated) addresses from IP pools.

    By default returns parsed JSON ``{count, records, documentation}`` where each
    record includes its stable ``.id`` (via ``show-ids``) for use in follow-up
    calls.

    - ``proplist``: comma-separated fields to return (e.g. ``"address,pool"``)
      so the client fetches only what it needs.
    - ``output``: ``json`` (default, parsed) | ``terse`` (raw one-line records) |
      ``detail`` (verbose) | ``raw`` (legacy plain ``print``).

    Docs: https://manual.mikrotik.com/docs/cli-reference/ip/pool
    """
    await ctx.info(f"Listing used IP pool addresses: pool={pool_name}, address={address_filter}")

    filters = []
    if pool_name:
        filters.append(f'pool="{pool_name}"')
    if address_filter:
        filters.append(f'address~"{address_filter}"')
    if mac_filter:
        filters.append(f'mac-address~"{mac_filter}"')
    if info_filter:
        filters.append(f'info~"{info_filter}"')

    return await print_resource(
        ctx,
        "/ip pool used",
        where=filters,
        proplist=proplist,
        output=output,
        scope="ip_pool",
        empty_message="No used addresses found matching the criteria.",
    )

@mcp.tool(name="expand_ip_pool", annotations=annotate(WRITE_IDEMPOTENT, "Expand IP Pool"))
async def mikrotik_expand_ip_pool(ctx: Context, name: str, additional_ranges: str) -> str:
    """Expands an existing IP pool by appending additional address ranges.

    Notes:
        additional_ranges: hyphen-separated range(s) e.g. "192.168.1.101-192.168.1.150"
            Multiple ranges comma-separated: "10.0.0.51-10.0.0.60,10.0.0.70-10.0.0.80"
    """
    await ctx.info(f"Expanding IP pool: name={name}, additional_ranges={additional_ranges}")

    # Get current ranges
    get_cmd = f'/ip pool print detail where name="{name}"'
    current = await execute_mikrotik_command(get_cmd, ctx)

    if not current or "no such item" in current:
        return f"IP pool '{name}' not found."

    # Extract current ranges
    import re
    ranges_match = re.search(r'ranges=([^\s]+)', current)
    if not ranges_match:
        return "Unable to determine current ranges."

    current_ranges = ranges_match.group(1)

    # Combine ranges
    new_ranges = f"{current_ranges},{additional_ranges}"

    # Update the pool
    return await mikrotik_update_ip_pool(name, ranges=new_ranges, ctx=ctx)
