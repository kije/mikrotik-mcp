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

- **Done (this PR):** foundation (`routeros.py` + tests), `docs_refs`, docs +
  snapshot + logs resources, and a fully converted **`ip_address`** scope as the
  reference pattern.
- **Next (per-scope, mechanical):** apply the same two-argument (`proplist`,
  `output`) conversion to the remaining list/print tools — `ipv6_address`,
  `interfaces`, `vlan`, `firewall_filter`, `firewall_nat`, `dhcp`, `dns`,
  `routes`, `ip_pool`, `queue`, `wireless`, `wireguard`, `poe`, `users`, `logs`.
  Each keeps `output="raw"` available for backward compatibility.
- **Later:** per-scope config-snapshot resources; experimental log subscription
  (background poll-and-notify) if the notify-then-refetch UX proves worthwhile.

## Backward compatibility

Converted list/get tools now default to JSON instead of wrapped text. The prior
plain-text behavior remains available via `output="raw"`. Existing tests for
untouched scopes are unchanged; the `ipv6_address` suite (which asserts exact
legacy command strings) is intentionally left for the next rollout step.
