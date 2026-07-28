# IP Address Management

> 📖 Official RouterOS docs: <https://manual.mikrotik.com/docs/cli-reference/ip/address>
>
> **Structured output (new).** The list/get tools default to parsed **JSON**
> (`{count, records, documentation}`). Each record carries its stable `.id`
> (via `show-ids`) so follow-up `get`/`remove` calls can reference it, plus
> `_index` and decoded `_flags`. Two shared options are available on these
> tools:
> - `proplist` — comma-separated field names to return only what you need
>   (e.g. `"address,interface"`), reducing output size.
> - `output` — `json` (default) · `terse` (raw one-line records) · `detail`
>   (verbose) · `raw` (legacy plain `print` text).
>
> A read-only **MCP resource** `mikrotik://ip/address` exposes the same live
> snapshot as JSON, and `mikrotik://docs/ip_address` returns this doc reference.

## `mikrotik_add_ip_address`
Adds an IP address to an interface.
- Parameters:
  - `address` (required): IP address with CIDR notation
  - `interface` (required): Interface name
  - `network` (optional): Network address
  - `broadcast` (optional): Broadcast address
  - `comment` (optional): Description
  - `disabled` (optional): Disable address
- Example:
  ```
  mikrotik_add_ip_address(address="192.168.1.1/24", interface="vlan100")
  ```

## `mikrotik_list_ip_addresses`
Lists IP addresses on MikroTik device.
- Parameters:
  - `interface_filter` (optional): Filter by interface
  - `address_filter` (optional): Filter by address
  - `network_filter` (optional): Filter by network
  - `disabled_only` (optional): Show only disabled addresses
  - `dynamic_only` (optional): Show only dynamic addresses
  - `proplist` (optional): Comma-separated fields to return (e.g. `"address,interface"`)
  - `output` (optional): `json` (default) · `terse` · `detail` · `raw`
- Example:
  ```
  mikrotik_list_ip_addresses(interface_filter="vlan100", proplist="address,interface")
  ```

## `mikrotik_get_ip_address`
Gets detailed information about a specific IP address.
- Parameters:
  - `address_id` (required): Address ID or address value
  - `proplist` (optional): Comma-separated fields to return
  - `output` (optional): `detail` (default) · `json` · `terse` · `raw`
- Example:
  ```
  mikrotik_get_ip_address(address_id="*1", output="json")
  ```

## `mikrotik_remove_ip_address`
Removes an IP address from MikroTik device.
- Parameters:
  - `address_id` (required): Address ID
- Example:
  ```
  mikrotik_remove_ip_address(address_id="*1")
  ```
