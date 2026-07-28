# Structured output, documentation references & MCP resources

This note records the investigation behind the request to (1) attach MikroTik
documentation references to each configuration object, (2) use MCP resources,
(3) offer subscription-style primitives for logs, and (4–7) make `print`/`export`
output machine-friendly via `terse`, `proplist`, `show-ids`, and JSON parsing.

## Feasibility summary

| Ask | Verdict | Approach |
|-----|---------|----------|
| Doc references per config object | ✅ Sensible | `docs_refs.SCOPE_DOCS` maps each scope → `manual.mikrotik.com` page. Surfaced in JSON responses + as resources, **not** in every tool description (avoids prompt bloat across 170+ tools). |
| MCP resources | ✅ Sensible | Two kinds: **docs** (`mikrotik://docs`, `mikrotik://docs/{scope}`) and **config snapshots** (`mikrotik://ip/address`). |
| Log subscriptions | ⚠️ Deferred | MCP subscriptions are *notify-then-refetch*, and FastMCP has no ergonomic decorator for server-initiated `resources/updated`. A true version needs a background poll-and-diff task on the low-level session. Shipped a **pollable** `mikrotik://logs/recent` resource instead. |
| `terse` output | ✅ Sensible | Default internal format for list/print — one record per line, easy to parse. |
| `proplist=` | ✅ Sensible | Exposed as a `proplist` tool argument; client selects fields. |
| `show-ids` | ✅ Sensible | On by default for `json`/`terse`/`detail`; every record carries `.id` for follow-up ops. |
| Parse to JSON | ✅ Sensible | `routeros.parse_terse()` → `list[dict]`; tools return `{count, records, documentation}`. |

## Architecture

Rather than editing ~170 call sites divergently, the logic is centralized in
`src/mcp_mikrotik/routeros.py`:

- `build_print_command(path, where, proplist, terse, show_ids, detail, count_only, limit)`
- `parse_terse(output)` — tokenizer that respects quoted values, decodes the
  `Flags:` legend, and attaches `_index` / `_flags`.
- `print_resource(ctx, path, where, proplist, output, …)` — the single entry
  point tools delegate to. `output ∈ {json, terse, detail, raw}`.

Doc references live in `src/mcp_mikrotik/docs_refs.py`; resources in
`src/mcp_mikrotik/resources.py`. `connector.execute_mikrotik_command` now accepts
an optional `ctx` so resource handlers (which have no per-request `Context`) can
reuse it.

## Rollout status

- **Done:** foundation (`routeros.py` + tests) and `docs_refs`.
- **Done:** the `proplist` + `output` conversion is applied across **all**
  standard list/get tools — `ip_address`, `ipv6_address`, `interfaces`, `vlan`,
  `firewall_filter`, `firewall_nat`, `dhcp`, `dns`, `routes`, `ip_pool`,
  `queue`, `wireless`, `wireguard`, `poe`, `users`. Each keeps `output="raw"`
  for backward compatibility.
- **Done:** documentation resources (`mikrotik://docs`, `.../docs/{scope}`) and
  per-object config-snapshot resources (`CONFIG_SNAPSHOTS` in `resources.py`),
  plus the pollable `mikrotik://logs/recent`.
- **Deferred (per decision):** experimental push-based log subscription
  (background poll-and-notify). The pollable logs resource covers most of the
  value in the meantime.
- **Intentionally not converted:** aggregate/singleton readouts that are not a
  simple record list — e.g. `get_dns_settings`, `get_*_statistics`,
  `get_route_cache`, `get_routing_table`, `get_active_users`,
  `list_user_ssh_keys`, `get_poe_monitor`, `get_wireless_registration_table`,
  the `logs` tools (which already have their own `print_as`), and
  `list_backups` (a file listing). These keep their bespoke output.

## Backward compatibility & behavior changes

Converted list/get tools now default to JSON instead of wrapped text; the prior
plain-text behavior remains available via `output="raw"`. Two conversions
dropped small bespoke features that don't fit the shared shape:

- `list_ip_pools` lost its `include_used` flag (per-pool usage counts); that
  data is available via `list_ip_pool_used`.
- `list_users`/`get_user` dropped a password-redaction regex — dead code, since
  `/user print` never emits the password field.

Wireless list/get retain RouterOS **v6/v7 auto-detection** of the wireless menu
path (`/interface wifi` · `wifiwave2` · `wireless`), and the previously-stubbed
wireless security-profile / access-list tools now query the device.
