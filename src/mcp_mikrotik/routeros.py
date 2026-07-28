"""Shared helpers for RouterOS ``print`` operations.

The scope modules historically each hand-built a ``print`` command string and
returned the device's raw text. This module centralises that so every
list/print tool can, consistently and without duplication:

  * request the machine-friendly ``terse`` output format (one record per line);
  * carry ``show-ids`` so each record includes its stable ``.id`` (``*XX``),
    which later ``get``/``set``/``remove`` calls can reference;
  * accept a ``proplist`` so an MCP client can select exactly the fields it
    wants (fewer tokens back);
  * parse the terse output into a list of field dicts and render it as JSON.

RouterOS terse format (what ``/ip address print terse show-ids`` emits)::

    Flags: X - disabled, I - invalid, D - dynamic
     0   .id=*1 address=192.168.88.1/24 network=192.168.88.0 interface=ether1
     1 D .id=*2 address=10.0.0.2/24 network=10.0.0.0 interface=ether2

Each data line is ``<index> <flag letters> key=value key=value …``; values that
contain spaces are double-quoted. The leading ``Flags:`` legend maps the flag
letters to names, which we decode onto each record.
"""

import json
import re
from typing import Dict, List, Literal, Optional, Sequence

from mcp.server.fastmcp import Context

from .connector import execute_mikrotik_command
from .docs_refs import doc_url

# Output shapes a print tool can return.
OutputFormat = Literal["json", "terse", "detail", "raw"]

# Keys we synthesise onto parsed records. RouterOS field names never start with
# an underscore, so these cannot collide with real fields.
INDEX_KEY = "_index"
FLAGS_KEY = "_flags"


def build_where(filters: Sequence[str]) -> str:
    """Return a ``where …`` clause for a list of already-formatted predicates.

    Predicates are joined with ``and`` (RouterOS treats a bare space between
    predicates as ``and`` too, but the explicit keyword is unambiguous). An
    empty list yields an empty string.
    """
    active = [f.strip() for f in filters if f and f.strip()]
    if not active:
        return ""
    return " where " + " and ".join(active)


def build_print_command(
    path: str,
    *,
    where: Optional[Sequence[str]] = None,
    proplist: Optional[str] = None,
    terse: bool = True,
    show_ids: bool = True,
    detail: bool = False,
    count_only: bool = False,
    limit: Optional[int] = None,
) -> str:
    """Assemble a ``<path> print …`` command from structured options.

    ``path`` is the RouterOS menu path without a trailing ``print`` (e.g.
    ``"/ip address"``). ``detail`` and ``count_only`` are mutually exclusive
    with ``terse``; when either is set the terse/show-ids modifiers are dropped.
    """
    parts = [f"{path.rstrip()} print"]

    if count_only:
        parts.append("count-only")
    elif detail:
        parts.append("detail")
        if show_ids:
            parts.append("show-ids")
    elif terse:
        parts.append("terse")
        if show_ids:
            parts.append("show-ids")
        # ``without-paging`` is harmless over a non-interactive SSH channel and
        # guarantees the device never waits for a "-- more --" keypress.
        parts.append("without-paging")

    if proplist:
        cleaned = ",".join(p.strip() for p in proplist.split(",") if p.strip())
        if cleaned:
            parts.append(f"proplist={cleaned}")

    cmd = " ".join(parts)
    cmd += build_where(where or [])

    if limit is not None:
        cmd += f" limit={limit}"

    return cmd


# ── terse parsing ──────────────────────────────────────────────────────────

_LEGEND_PAIR = re.compile(r"([A-Za-z])\s*-\s*([A-Za-z][A-Za-z -]*?)(?=,|;|$)")


def parse_flag_legend(text: str) -> Dict[str, str]:
    """Parse a ``Flags: X - disabled, D - dynamic`` legend into ``{letter: name}``."""
    legend: Dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("flags:"):
            continue
        body = stripped.split(":", 1)[1]
        for letter, name in _LEGEND_PAIR.findall(body):
            legend[letter] = name.strip().rstrip(".").replace(" ", "-")
    return legend


def _tokenize(line: str) -> List[str]:
    """Split a terse line into tokens, keeping double-quoted spans intact."""
    tokens: List[str] = []
    buf: List[str] = []
    in_quote = False
    escaped = False
    for ch in line:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            buf.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_quote = not in_quote
            buf.append(ch)
            continue
        if ch == " " and not in_quote:
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"')
    return value


def _is_data_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.lower().startswith("flags:"):
        return False
    # A record always carries at least one ``key=value`` field.
    return "=" in stripped


def parse_terse(output: str) -> List[Dict[str, str]]:
    """Parse ``print terse`` output into a list of field dicts.

    Each record gains an ``_index`` (the leading ordinal, if present) and a
    ``_flags`` list of decoded flag names (from the ``Flags:`` legend). Real
    RouterOS fields — including ``.id`` when ``show-ids`` was used — are kept
    verbatim.
    """
    if not output:
        return []

    legend = parse_flag_legend(output)
    records: List[Dict[str, str]] = []

    for line in output.splitlines():
        if not _is_data_line(line):
            continue

        record: Dict[str, str] = {}
        flag_letters: List[str] = []
        index: Optional[str] = None
        fields_started = False

        for token in _tokenize(line.strip()):
            if not fields_started and "=" not in token:
                # Leading index / flag-letter column.
                if index is None and token.isdigit():
                    index = token
                else:
                    flag_letters.extend(ch for ch in token if ch.isalpha())
                continue
            fields_started = True
            if "=" not in token:
                continue
            key, _, value = token.partition("=")
            record[key] = _unquote(value)

        if not record:
            continue
        if index is not None:
            record[INDEX_KEY] = index
        if flag_letters:
            record[FLAGS_KEY] = [legend.get(f, f) for f in flag_letters]
        records.append(record)

    return records


# ── high-level tool helper ─────────────────────────────────────────────────


def render_json(records: List[Dict[str, str]], *, scope: Optional[str] = None) -> str:
    """Render parsed records as a compact JSON document with a count + docs link."""
    payload: Dict[str, object] = {"count": len(records), "records": records}
    if scope:
        url = doc_url(scope)
        if url:
            payload["documentation"] = url
    return json.dumps(payload, ensure_ascii=False)


async def print_resource(
    ctx: Optional[Context],
    path: str,
    *,
    where: Optional[Sequence[str]] = None,
    proplist: Optional[str] = None,
    output: OutputFormat = "json",
    limit: Optional[int] = None,
    show_ids: bool = True,
    scope: Optional[str] = None,
    empty_message: Optional[str] = None,
) -> str:
    """Run a ``print`` and return it in the requested shape.

    * ``json``   — ``terse show-ids`` parsed into a JSON ``{count, records, …}``
      document (the default; smallest and easiest for a client to consume).
    * ``terse``  — the raw ``terse`` text, unparsed.
    * ``detail`` — the verbose ``print detail`` text (with ``show-ids``).
    * ``raw``    — a plain ``print`` exactly as before this helper existed.

    ``proplist`` (comma-separated field names) is honoured in every mode except
    ``raw``, letting the caller trim the returned fields.
    """
    detail = output == "detail"
    terse = output in ("json", "terse")

    cmd = build_print_command(
        path,
        where=where,
        proplist=proplist if output != "raw" else None,
        terse=terse,
        show_ids=show_ids and output != "raw",
        detail=detail,
        limit=limit,
    )

    result = await execute_mikrotik_command(cmd, ctx)

    if output == "json":
        records = parse_terse(result)
        if not records:
            return render_json([], scope=scope)
        return render_json(records, scope=scope)

    if not result or not result.strip() or result.strip() == "no such item":
        return empty_message or "No matching items found."
    return result
