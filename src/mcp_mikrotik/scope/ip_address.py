from typing import Optional

from ..connector import execute_mikrotik_command
from mcp.server.fastmcp import Context
from ..app import mcp, READ, WRITE, DESTRUCTIVE, annotate
from ..docs_refs import doc_url
from ..routeros import OutputFormat, print_resource

@mcp.tool(name="add_ip_address", annotations=annotate(WRITE, "Add IP Address"))
async def mikrotik_add_ip_address(
    ctx: Context,
    address: str,
    interface: str,
    network: Optional[str] = None,
    broadcast: Optional[str] = None,
    comment: Optional[str] = None,
    disabled: bool = False
) -> str:
    """Adds an IP address to an interface on the MikroTik device."""
    await ctx.info(f"Adding IP address: address={address}, interface={interface}")

    # Build the command
    cmd = f"/ip address add address={address} interface={interface}"

    # Add optional parameters
    if network:
        cmd += f" network={network}"

    if broadcast:
        cmd += f" broadcast={broadcast}"

    if comment:
        cmd += f' comment="{comment}"'

    if disabled:
        cmd += " disabled=yes"

    result = await execute_mikrotik_command(cmd, ctx)

    if "failure:" in result.lower() or "error" in result.lower():
        return f"Failed to add IP address: {result}"

    # Get the created address details
    details_cmd = f'/ip address print detail where address="{address}"'
    details = await execute_mikrotik_command(details_cmd, ctx)

    return f"IP address added successfully:\n\n{details}"

@mcp.tool(name="list_ip_addresses", annotations=annotate(READ, "List IP Addresses"))
async def mikrotik_list_ip_addresses(
    ctx: Context,
    interface_filter: Optional[str] = None,
    address_filter: Optional[str] = None,
    network_filter: Optional[str] = None,
    disabled_only: bool = False,
    dynamic_only: bool = False,
    proplist: Optional[str] = None,
    output: OutputFormat = "json",
) -> str:
    """Lists IP addresses on the MikroTik device.

    By default returns parsed JSON ``{count, records, documentation}`` where each
    record includes its stable ``.id`` (via ``show-ids``) for use in follow-up
    ``get``/``remove`` calls.

    - ``proplist``: comma-separated fields to return (e.g. ``"address,interface"``)
      so the client fetches only what it needs.
    - ``output``: ``json`` (default, parsed) | ``terse`` (raw one-line records) |
      ``detail`` (verbose) | ``raw`` (legacy plain ``print``).

    Docs: https://manual.mikrotik.com/docs/cli-reference/ip/address
    """
    await ctx.info(f"Listing IP addresses with filters: interface={interface_filter}, address={address_filter}")

    filters = []
    if interface_filter:
        filters.append(f'interface="{interface_filter}"')
    if address_filter:
        filters.append(f'address~"{address_filter}"')
    if network_filter:
        filters.append(f'network="{network_filter}"')
    if disabled_only:
        filters.append("disabled=yes")
    if dynamic_only:
        filters.append("dynamic=yes")

    return await print_resource(
        ctx,
        "/ip address",
        where=filters,
        proplist=proplist,
        output=output,
        scope="ip_address",
        empty_message="No IP addresses found matching the criteria.",
    )

@mcp.tool(name="get_ip_address", annotations=annotate(READ, "Get IP Address"))
async def mikrotik_get_ip_address(
    ctx: Context,
    address_id: str,
    proplist: Optional[str] = None,
    output: OutputFormat = "detail",
) -> str:
    """Gets detailed information about a specific IP address by ID or address value.

    - ``output``: ``detail`` (default, verbose text) | ``json`` (parsed) |
      ``terse`` (one-line) | ``raw``.
    - ``proplist``: comma-separated fields to return.

    Docs: https://manual.mikrotik.com/docs/cli-reference/ip/address
    """
    await ctx.info(f"Getting IP address details: address_id={address_id}")

    # Resolve which selector matches: .id first, then the address value.
    selector = None
    for field in (".id", "address"):
        count = await execute_mikrotik_command(
            f'/ip address print count-only where {field}="{address_id}"', ctx
        )
        if count.strip().isdigit() and int(count.strip()) > 0:
            selector = f'{field}="{address_id}"'
            break

    if selector is None:
        return f"IP address '{address_id}' not found."

    return await print_resource(
        ctx,
        "/ip address",
        where=[selector],
        proplist=proplist,
        output=output,
        scope="ip_address",
        empty_message=f"IP address '{address_id}' not found.",
    )

@mcp.tool(name="remove_ip_address", annotations=annotate(DESTRUCTIVE, "Remove IP Address"))
async def mikrotik_remove_ip_address(ctx: Context, address_id: str) -> str:
    """Removes an IP address from the MikroTik device by ID or address value."""
    await ctx.info(f"Removing IP address: address_id={address_id}")

    # Try to find by ID first
    check_cmd = f'/ip address print count-only where .id="{address_id}"'
    count = await execute_mikrotik_command(check_cmd, ctx)

    if count.strip() == "0":
        # Try finding by address value
        check_cmd = f'/ip address print count-only where address="{address_id}"'
        count = await execute_mikrotik_command(check_cmd, ctx)

        if count.strip() == "0":
            return f"IP address '{address_id}' not found."

        # Remove by address value
        cmd = f'/ip address remove [find address="{address_id}"]'
    else:
        # Remove by ID
        cmd = f'/ip address remove [find .id="{address_id}"]'

    result = await execute_mikrotik_command(cmd, ctx)

    if "failure:" in result.lower() or "error" in result.lower():
        return f"Failed to remove IP address: {result}"

    return f"IP address '{address_id}' removed successfully."
