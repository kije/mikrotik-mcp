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

RouterOS v7 terse format (verified against 7.19.4; what
``/ip address print terse show-ids`` emits)::

    *1  D address=10.0.2.15/24 network=10.0.2.0 interface=ether1
    *2    comment=LAN side "main" address=192.168.50.1/24 interface=ether2
    *3 X  comment=plain address=192.168.60.1/24 interface=ether2

Each data line is ``<id|index> <flag letters> key=value key=value …``. With
``show-ids`` the leading column *is* the ``.id``; without it, it is the
positional index. Values are **not** quoted or escaped, so they may contain
spaces (and quotes); a field therefore runs until the next ``key=`` token.
Terse output carries no ``Flags:`` legend, so :func:`print_resource` appends
an empty ``print detail`` (see :func:`legend_command`) to decode the flags.
"""

import json
import re
from typing import Dict, List, Literal, Optional, Sequence

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

from .connector import execute_mikrotik_command
from .docs_refs import doc_url

# Output shapes a print tool can return.
OutputFormat = Literal["json", "terse", "detail", "raw"]

# Keys we synthesise onto parsed records. RouterOS field names never start with
# an underscore, so these cannot collide with real fields.
INDEX_KEY = "_index"
FLAGS_KEY = "_flags"


# RouterOS evaluates ``$var`` / ``$[cmd]`` and the usual backslash escapes even
# inside double quotes, and ``;`` outside them ends the command.
_STR_ESCAPES = str.maketrans({
    "\\": "\\\\", '"': '\\"', "$": "\\$", "?": "\\?",
    "\n": "\\n", "\r": "\\r", "\t": "\\t",
})

# A property name as accepted by ``proplist=`` (``address``, ``.id``,
# ``dst-address``).
_PROPERTY_NAME = re.compile(r"^\.?[a-z0-9][a-z0-9-]*$")


def ros_str(value: object) -> str:
    """Quote *value* as a RouterOS string literal, safe to splice into a command.

    Every caller-supplied value in a ``where`` predicate must go through this:
    an unescaped ``"`` would let the value close the string and append
    ``; <any command>`` — from a tool annotated read-only.
    """
    return '"' + str(value).translate(_STR_ESCAPES) + '"'


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
) -> str:
    """Assemble a ``<path> print …`` command from structured options.

    ``path`` is the RouterOS menu path without a trailing ``print`` (e.g.
    ``"/ip address"``). ``detail`` and ``count_only`` are mutually exclusive
    with ``terse``; when either is set the terse modifier is dropped.

    There is deliberately no ``limit``: ``print`` has no such argument, and
    since ``where`` swallows everything after it, a trailing ``limit=N`` turns
    into part of the filter expression and silently matches nothing.
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
        names = [p.strip() for p in proplist.split(",") if p.strip()]
        invalid = [n for n in names if not _PROPERTY_NAME.match(n)]
        if invalid:
            # proplist is spliced in unquoted, so this check is what stops
            # ``address;/system reboot`` from running a second command.
            raise ToolError(f"Invalid proplist field name(s): {', '.join(invalid)}")
        if names:
            parts.append(f"proplist={','.join(names)}")

    # ``where`` must come last: RouterOS reads the rest of the line as the
    # filter expression.
    return " ".join(parts) + build_where(where or [])


# ── terse parsing ──────────────────────────────────────────────────────────


class RouterOSError(ResourceError):
    """The device answered a ``print`` with an error instead of records.

    Subclassing :class:`ResourceError` means the message reaches the client
    both from a tool (reported as ``isError``) and from a resource read
    (reported as a JSON-RPC error); any other exception type would be masked
    by the SDK as an opaque "unexpected" failure.
    """


# One ``<letter> - <name>`` pair; pairs are separated by ``,`` or ``;``. Flag
# symbols are not always letters (routes use ``+ - ecmp``).
_LEGEND_PAIR = re.compile(r"(?:^|[,;])\s*(\S)\s+-\s+([^,;]+)")

# The leading column of a record: ``*1A`` with ``show-ids``, else ``0``, ``12``.
_RECORD_START = re.compile(r"^\s*(\*[0-9A-Fa-f]+|\d+)(?=\s|$)")

# Start of a ``key=`` field. RouterOS property names are lower-case words
# joined by ``-`` (``.id``/``.nextid`` carry a leading dot).
_FIELD_START = re.compile(r"(?:^|(?<= ))(\.?[a-z0-9][a-z0-9-]*)=")

# Properties RouterOS prints as a bare word, without ``=value``, when set
# (``/ip route … blackhole``). Without this list the word would be read as the
# tail of the preceding field's value.
VALUELESS_PROPERTIES = frozenset({"blackhole"})


def parse_flag_legend(text: str) -> Dict[str, str]:
    """Parse a ``Flags:`` legend into ``{symbol: name}``.

    Long legends wrap onto continuation lines (``/ip route``)::

        Flags: D - dynamic; X - disabled, I - inactive, A - active;
        c - connect, s - static, r - rip, b - bgp, o - ospf, ...
        H - hw-offloaded; + - ecmp

    so every line up to the first blank or record line belongs to it.
    """
    legend: Dict[str, str] = {}
    in_legend = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("flags:"):
            in_legend = True
            stripped = stripped.split(":", 1)[1]
        elif not in_legend:
            continue
        elif not stripped or _RECORD_START.match(line) or stripped.lower().startswith("columns:"):
            in_legend = False
            continue
        for symbol, name in _LEGEND_PAIR.findall(stripped):
            legend[symbol] = name.strip().rstrip(".").replace(" ", "-")
    return legend


def _parse_fields(text: str) -> Dict[str, str]:
    """Split ``k1=v 1 k2=v2 flag`` into fields; a value ends at the next ``key=``."""
    starts = list(_FIELD_START.finditer(text))
    fields: Dict[str, str] = {}
    for i, match in enumerate(starts):
        end = starts[i + 1].start() - 1 if i + 1 < len(starts) else len(text)
        value = text[match.end():end]
        head, sep, last = value.rpartition(" ")
        while sep and last in VALUELESS_PROPERTIES and match.group(1) != "comment":
            fields[last] = "yes"
            value = head
            head, sep, last = value.rpartition(" ")
        fields[match.group(1)] = value
    return fields


def _split_record_line(line: str):
    """Return ``(id_or_index, flag_symbols, fields_text)``, or ``None`` if *line*
    does not start with an id/index column."""
    start = _RECORD_START.match(line)
    if not start:
        return None
    rest = line[start.end():].lstrip()
    first_field = _FIELD_START.search(rest)
    split_at = first_field.start() if first_field else len(rest)
    return start.group(1), "".join(rest[:split_at].split()), rest[split_at:]


def parse_terse(output: str, *, legend: Optional[Dict[str, str]] = None) -> List[Dict[str, object]]:
    """Parse ``print terse`` output into a list of field dicts.

    The leading column becomes ``.id`` (``*1A``, with ``show-ids``) or
    ``_index`` (``0``, without). Flag symbols become a ``_flags`` list,
    decoded to names via *legend* (or a ``Flags:`` legend found in *output*);
    unknown symbols are kept as-is.

    Raises :class:`RouterOSError` if a non-blank line is neither a record nor
    part of a legend — that is how a device error (``bad command name …``,
    ``expected end of command …``) shows up, and it must not be mistaken for
    an empty result.
    """
    if not output:
        return []

    legend = {**parse_flag_legend(output), **(legend or {})}
    records: List[Dict[str, object]] = []
    in_legend = False
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            in_legend = False
            continue
        if stripped.lower().startswith("flags:"):
            in_legend = True
            continue
        parts = _split_record_line(line.rstrip())
        if parts is None:
            if in_legend:  # a wrapped legend continuation line
                continue
            raise RouterOSError(stripped)
        in_legend = False
        lead, flags, fields_text = parts

        record: Dict[str, object] = {}
        if lead.startswith("*"):
            record[".id"] = lead
        else:
            record[INDEX_KEY] = lead
        record.update(_parse_fields(fields_text))
        if flags:
            record[FLAGS_KEY] = [legend.get(f, f) for f in flags]
        records.append(record)

    return records


# ``*1A  2026-09-22 17:59:51 script,info message text`` — ``/log print terse``
# is positional, not ``key=value``. Older releases print the time as
# ``jan/02 12:00:00`` or just ``12:00:00``, hence the optional date token.
_LOG_LINE = re.compile(
    r"^\s*(\*[0-9A-Fa-f]+|\d+)\s+((?:\S+\s+)?\d{1,2}:\d{2}:\d{2})\s+(\S+)(?:\s(.*))?$"
)


def parse_log_terse(output: str) -> List[Dict[str, str]]:
    """Parse ``/log print terse show-ids`` into ``{.id, time, topics, message}``.

    Raises :class:`RouterOSError` on a line that is not a log entry.
    """
    entries: List[Dict[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        match = _LOG_LINE.match(line.rstrip())
        if match is None:
            raise RouterOSError(line.strip())
        lead, time, topics, message = match.groups()
        entry = {".id": lead} if lead.startswith("*") else {INDEX_KEY: lead}
        entry.update(time=time, topics=topics, message=message or "")
        entries.append(entry)
    return entries


# ── high-level tool helper ─────────────────────────────────────────────────


def render_json(records: List[Dict[str, object]], *, scope: Optional[str] = None) -> str:
    """Render parsed records as a compact JSON document with a count + docs link."""
    payload: Dict[str, object] = {"count": len(records), "records": records}
    if scope:
        url = doc_url(scope)
        if url:
            payload["documentation"] = url
    return json.dumps(payload, ensure_ascii=False)


def legend_command(path: str) -> str:
    """A ``print`` that outputs only the menu's ``Flags:`` legend.

    Terse output never includes the legend, but an empty ``print detail``
    still prints the complete one. :func:`print_resource` chains this after
    the terse print (``…; <this>``) so decoding flags costs no extra SSH
    session; a parse error in the first command aborts the whole line, so
    error detection is unaffected.
    """
    return f"{path.rstrip()} print detail where false"


async def print_resource(
    ctx: Optional[Context],
    path: str,
    *,
    where: Optional[Sequence[str]] = None,
    proplist: Optional[str] = None,
    output: OutputFormat = "json",
    show_ids: bool = True,
    scope: Optional[str] = None,
    empty_message: Optional[str] = None,
) -> str:
    """Run a ``print`` and return it in the requested shape.

    * ``json``   — ``terse show-ids`` parsed into a JSON ``{count, records, …}``
      document (the default; smallest and easiest for a client to consume).
      A device error raises :class:`RouterOSError` instead of returning an
      empty list.
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
    )

    if output == "json":
        result = await execute_mikrotik_command(f"{cmd}; {legend_command(path)}", ctx)
        if result.startswith("Error"):
            raise RouterOSError(result)
        return render_json(parse_terse(result), scope=scope)

    result = await execute_mikrotik_command(cmd, ctx)

    if not result or not result.strip() or result.strip() == "no such item":
        return empty_message or "No matching items found."
    return result
