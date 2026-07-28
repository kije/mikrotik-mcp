# API Reference

Complete reference documentation for all MikroTik MCP tools.

## Structured output (list/get tools)

Tools that list a configuration object or fetch one by id/name share two
options:

- **`output`** — `json` (default; parsed `{count, records, documentation}`
  where each record carries its stable `.id` via `show-ids`, plus `_index` and
  decoded `_flags`), `terse` (raw one-line records), `detail` (verbose text), or
  `raw` (legacy plain `print` text for backward compatibility).
- **`proplist`** — comma-separated field names (e.g. `"address,interface"`) so
  the client fetches only the fields it needs.

Each response includes a `documentation` link to the relevant
[RouterOS manual](https://manual.mikrotik.com/docs/introduction/) page. The same
references and live config snapshots are also exposed as **MCP resources**
(`mikrotik://docs`, `mikrotik://docs/{scope}`, `mikrotik://<object>`, and the
pollable `mikrotik://logs/recent`). See
[design/structured-output-and-resources.md](../design/structured-output-and-resources.md).

## Available Tool Categories

- **[Interfaces](interfaces/README.md)** - All Interface Management (ethernet, bridge, PPPoE, SFP, LTE …)
- **[PoE](poe/README.md)** - Power over Ethernet monitoring
- **[VLAN](vlan/README.md)** - VLAN Interface Management
- **[IP Address](ip-address/README.md)** - IPv4 Address Management
- **[IPv6 Address](ipv6-address/README.md)** - IPv6 Address Management
- **[DHCP](dhcp/README.md)** - DHCP Server Management
- **[NAT](nat/README.md)** - NAT Rules Management
- **[IP Pool](ip-pool/README.md)** - IP Pool Management
- **[Backup](backup/README.md)** - Backup and Export Management
- **[Logs](logs/README.md)** - Log Management
- **[Firewall](firewall/README.md)** - Firewall Filter Rules Management
- **[Routes](routes/README.md)** - Route Management
- **[DNS](dns/README.md)** - DNS Management
- **[Users](users/README.md)** - User Management
- **[WireGuard](wireguard/README.md)** - WireGuard VPN Management
- **[Queue](queue/README.md)** - Queue Types, Trees, and Simple Queues
- **[Safe Mode](safe-mode/README.md)** - Safe Mode Session Management
