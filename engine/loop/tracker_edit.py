"""Tracker mutations — add_row, move_row, touch_row.

Structural counterpart to tracker_schema.py's read-only parse_tracker /
tracker_check: this module WRITES the same markdown file, matching rows the
same way a human would (Company + Role, tolerant of a trailing annotation
like "(via referral)") and touching only the line(s) an edit actually
concerns — every other line in the file comes back byte-for-byte identical
to what went in, which is what tools/tracker_cli.py's diff output proves
before it ever writes to disk.

Reuses engine/radar/tracker.py's `_normalize_tracker_cell` for company/role
matching rather than reimplementing annotation-stripping here — this module
edits the same tracker rows tracker_suppresses reads, and they need to
agree on what counts as the same company.
"""
from __future__ import annotations

import re

from engine.loop.tracker_schema import _section_title, _table_lines, parse_tracker
from engine.radar.tracker import _normalize_tracker_cell

# A pipe preceded by a backslash is a literal "|" inside a cell, same
# convention tracker_schema._split_row reads — used here to find cell
# boundaries in a RAW (un-stripped) line so touch_row can splice one cell
# without disturbing any other cell's exact text.
_UNESCAPED_PIPE_POS = re.compile(r"(?<!\\)\|")


class TrackerEditError(Exception):
    """Raised when an edit can't be applied safely: an unknown section, an
    unknown column, or a Company+Role match that isn't exactly one row."""


def _normalize_section_key(section: str) -> str:
    return (section or "").strip().lower()


def _escape_cell(value) -> str:
    return str(value if value is not None else "").replace("|", "\\|")


def _require_section(sections: dict, key: str):
    if key not in sections:
        raise TrackerEditError(f"unknown section: {key!r}")
    return sections[key]


def _require_known_keys(keys, headers, section_key):
    header_lower = {h.lower() for h in headers}
    unknown = [k for k in keys if k.lower() not in header_lower]
    if unknown:
        raise TrackerEditError(
            f"unknown column(s) for {_section_title(section_key)} section: "
            f"{', '.join(unknown)}")


def _build_row_cells(headers, values: dict) -> list:
    value_lower = {k.lower(): v for k, v in values.items()}
    return [_escape_cell(value_lower.get(h.lower(), "")) for h in headers]


def _row_text(cells: list) -> str:
    return "| " + " | ".join(cells) + " |"


def _last_table_line(text: str, key: str):
    """1-based line number of the LAST line (header, separator, or data row)
    belonging to `key`'s table block. Callers only reach this after
    confirming the section exists via parse_tracker, so a table is
    guaranteed to be there."""
    last = None
    for lineno, section_key, _cells, _is_new_block in _table_lines(text):
        if section_key == key:
            last = lineno
    return last


def _splitlines_and_trailing_newline(text: str):
    return text.splitlines(), text.endswith("\n")


def _join(lines: list, trailing_newline: bool) -> str:
    return "\n".join(lines) + ("\n" if trailing_newline else "")


def _find_one_match(rows, company, role, section_key):
    """Exactly one row whose Company and Role both normalize (annotation
    stripped, lowercased — tracker_suppresses's own rule) to the given
    values. Zero or more than one is a TrackerEditError naming what was
    actually found, never a silent first-match guess."""
    target_company = _normalize_tracker_cell(company)
    target_role = _normalize_tracker_cell(role)
    matches = [
        row for row in rows
        if _normalize_tracker_cell(row.get("Company")) == target_company
        and _normalize_tracker_cell(row.get("Role")) == target_role
    ]
    if not matches:
        raise TrackerEditError(
            f"no row found for {company!r} / {role!r} in "
            f"{_section_title(section_key)} section")
    if len(matches) > 1:
        lines = ", ".join(str(m.line) for m in matches)
        raise TrackerEditError(
            f"ambiguous match: {len(matches)} rows found for {company!r} / "
            f"{role!r} in {_section_title(section_key)} section "
            f"(lines {lines})")
    return matches[0]


def add_row(text: str, section: str, values: dict) -> str:
    """Append one row to `section`'s table, right after its last existing
    line. Cells are ordered by that table's OWN headers; a header with no
    matching key in `values` gets an empty cell. A key in `values` that
    matches no header is a TrackerEditError naming it. Returns the new full
    text — every other line is untouched."""
    key = _normalize_section_key(section)
    sections = parse_tracker(text)
    table = _require_section(sections, key)
    _require_known_keys(values.keys(), table.headers, key)

    new_line = _row_text(_build_row_cells(table.headers, values))

    last_line = _last_table_line(text, key)
    lines, trailing_newline = _splitlines_and_trailing_newline(text)
    lines.insert(last_line, new_line)
    return _join(lines, trailing_newline)


def move_row(text: str, company: str, role: str, from_section: str,
             to_section: str, extra: dict) -> str:
    """Move one row from `from_section` to `to_section`. Finds exactly one
    row matching Company+Role (annotation-tolerant); zero or multiple
    matches is a TrackerEditError naming what was found. Columns shared by
    name between the two tables carry the source row's values across;
    `extra` supplies target-only columns (e.g. Active's Stage/Last touch
    when moving in from Drafted); columns that exist only in the source
    table are dropped — they lived their life there."""
    extra = extra or {}
    from_key = _normalize_section_key(from_section)
    to_key = _normalize_section_key(to_section)
    sections = parse_tracker(text)
    from_table = _require_section(sections, from_key)
    to_table = _require_section(sections, to_key)
    _require_known_keys(extra.keys(), to_table.headers, to_key)

    matched = _find_one_match(from_table.rows, company, role, from_key)

    from_header_lower = {h.lower() for h in from_table.headers}
    extra_lower = {k.lower() for k in extra}
    values = dict(extra)
    for h in to_table.headers:
        if h.lower() in extra_lower:
            continue  # extra already supplies this target-only column
        if h.lower() in from_header_lower:
            values[h] = matched.get(h) or ""
    new_line = _row_text(_build_row_cells(to_table.headers, values))

    remove_idx = matched.line - 1
    insert_after_idx = _last_table_line(text, to_key) - 1

    lines, trailing_newline = _splitlines_and_trailing_newline(text)
    del lines[remove_idx]
    if remove_idx < insert_after_idx:
        # Removing an earlier line shifts everything after it up by one,
        # including the target insertion point.
        insert_after_idx -= 1
    lines.insert(insert_after_idx + 1, new_line)
    return _join(lines, trailing_newline)
