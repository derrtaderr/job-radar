"""Tracker schema — header-driven parsing and validation of the job-search
tracker markdown file (the Global Constraints contract).

Unlike engine/radar/tracker.py (which only cares about the first cell of a
row, for suppression), this module reads every column by name and checks the
tracker's shape: are the required sections and columns present, does every
row's cell count match its header, does every date cell actually carry a
date, is any Company+Role duplicated within a section where a role can't
legitimately be live twice at once (Active, Drafted but not applied — not
Closed or Research, which allow repeats by design). Task 3 edits the file
by the line numbers this module reports, so `Row.line` must be exact — it is
a 1-based position in the ORIGINAL text's `splitlines()`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
_ISO_DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
_SEPARATOR_CELL = re.compile(r"^:?-+:?$")

# The Global Constraints contract: only these two sections gate on missing
# columns. The other two (Drafted but not applied, Research) are expected
# shape, not required — extra or missing columns there are tolerated.
REQUIRED_COLUMNS = {
    "active": ["Company", "Role", "Last touch"],
    "closed": ["Company", "Role", "Date closed", "Outcome"],
}
_SECTION_TITLES = {"active": "Active", "closed": "Closed"}

# Columns that must carry a parseable ISO date whenever the cell is non-empty,
# wherever they show up (only Active and Closed name one today, but the check
# is by column name, not by hardcoded section).
_DATE_COLUMNS = {"last touch", "date closed"}

# Duplicate Company+Role only gates a section where a role can't legitimately
# be live twice at once. Closed and Research are append-only / low-commitment
# by design — a company can reapply for the same role months apart (a real
# tracker shows this for Crux, EZO.io, and Tempo, all closed-then-reactivated
# or reapplied), so flagging a repeat there is a false positive, not a data
# bug. Orchestrator ruling, 2026-09-13. Same set tracker_edit gates row
# findability on (tracker_edit._IDENTITY_GATED_SECTIONS) — keep the two in
# sync.
_DUPLICATE_GATED_SECTIONS = {"active", "drafted but not applied"}


class Row:
    """One data row from a tracker table. Dict-like lookup by header name,
    case-insensitive ('Company' and 'company' both work), plus `.line` — the
    1-based line number of this row in the source text — and
    `.raw_cell_count`, the number of pipe-delimited cells the source line
    actually had (which may differ from the header count; that mismatch is
    what tracker_check reports, not something parse_tracker hides by padding
    silently).
    """

    def __init__(self, cells: dict, line: int, raw_cell_count: int):
        self._cells = cells
        self.line = line
        self.raw_cell_count = raw_cell_count

    def get(self, key, default=None):
        key_lower = key.lower()
        for k, v in self._cells.items():
            if k.lower() == key_lower:
                return v
        return default

    def __getitem__(self, key):
        sentinel = object()
        value = self.get(key, sentinel)
        if value is sentinel:
            raise KeyError(key)
        return value

    def __contains__(self, key):
        key_lower = key.lower()
        return any(k.lower() == key_lower for k in self._cells)

    def __repr__(self):
        return f"Row({self._cells!r}, line={self.line})"


@dataclass
class Table:
    headers: list = field(default_factory=list)
    rows: list = field(default_factory=list)


def _normalize_section_name(raw: str) -> str:
    """'Research (JD filed, no work started)' -> 'research'."""
    name = raw.strip()
    if "(" in name:
        name = name[: name.index("(")].strip()
    return name.lower()

# A pipe preceded by a backslash is a literal "|" inside a cell (what the
# radar's own report renderer produces), not a column boundary.
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def _split_row(line: str) -> list:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    parts = _UNESCAPED_PIPE.split(stripped)
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.strip().replace("\\|", "|") for p in parts]

def _is_separator_row(cells: list) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL.match(c) for c in cells)


def _table_lines(text: str):
    """Yield (lineno, section_key, cells, is_new_block) for every table row
    (header, separator, or data) in the source text. `is_new_block` is True
    for the first pipe-line of a contiguous run — it resets on a '## '
    heading and on any non-blank-pipe line, so a section holding prose above
    or below a table (e.g. '## Schema notes') never mixes that prose into the
    table state.
    """
    section_key = None
    in_table = False
    for i, line in enumerate(text.splitlines()):
        lineno = i + 1
        stripped = line.strip()
        heading = _SECTION_RE.match(stripped)
        if heading:
            section_key = _normalize_section_name(heading.group(1))
            in_table = False
            continue
        if section_key is None:
            continue
        if not stripped.startswith("|"):
            in_table = False
            continue
        cells = _split_row(stripped)
        is_new_block = not in_table
        in_table = True
        yield lineno, section_key, cells, is_new_block


def _present_sections(text: str) -> set:
    """Every '## ' heading's normalized name, whether or not it carries a
    table — used to tell 'the section is missing entirely' apart from 'the
    section exists but has no table', which are different mistakes."""
    sections = set()
    for line in (text or "").splitlines():
        heading = _SECTION_RE.match(line.strip())
        if heading:
            sections.add(_normalize_section_name(heading.group(1)))
    return sections


def parse_tracker(text: str) -> dict:
    """Header-driven parse of a tracker markdown file into
    {normalized_section_name: Table}. Only sections that carry at least a
    header row appear in the result — a prose-only section (or an unknown one
    like '## Strategy note') is silently absent, never a violation on its
    own; tracker_check is what turns absence of a REQUIRED section/column
    into a violation.
    """
    sections: dict = {}
    block = None  # {"key": ..., "headers": [...], "seen_sep": bool}

    for lineno, key, cells, is_new_block in _table_lines(text or ""):
        if is_new_block:
            block = {"key": key, "headers": cells, "seen_sep": False}
            if key not in sections:
                sections[key] = Table(headers=list(cells), rows=[])
            continue

        if not block["seen_sep"] and _is_separator_row(cells):
            block["seen_sep"] = True
            continue

        headers = block["headers"]
        row_data = {h: (cells[idx] if idx < len(cells) else "") for idx, h in enumerate(headers)}
        sections[key].rows.append(Row(row_data, lineno, len(cells)))

    return sections


def _section_title(key: str) -> str:
    return _SECTION_TITLES.get(key) or " ".join(w.capitalize() for w in key.split())


def tracker_check(text: str) -> list:
    """Validate a tracker's shape against the Global Constraints contract.
    Returns plain-English violation strings naming concrete things (line
    numbers, cell text, both duplicate lines) — empty list means valid.
    """
    text = text or ""
    violations = []

    present = _present_sections(text)
    for key in ("active", "closed"):
        if key not in present:
            violations.append(f"missing required section: ## {_section_title(key)}")

    sections = parse_tracker(text)

    for key, required_cols in REQUIRED_COLUMNS.items():
        if key not in present:
            continue  # already reported as a missing section above
        headers = sections[key].headers if key in sections else []
        header_lower = {h.lower() for h in headers}
        for col in required_cols:
            if col.lower() not in header_lower:
                violations.append(
                    f"## {_section_title(key)} section missing required column {col!r}")

    for key, table in sections.items():
        title = _section_title(key)
        n_headers = len(table.headers)
        header_lower = {h.lower() for h in table.headers}
        has_company_role = "company" in header_lower and "role" in header_lower
        gate_duplicates = has_company_role and key in _DUPLICATE_GATED_SECTIONS
        date_columns = [h for h in table.headers if h.lower() in _DATE_COLUMNS]

        seen_company_role = {}

        for row in table.rows:
            if row.raw_cell_count != n_headers:
                violations.append(
                    f"line {row.line}: row has {row.raw_cell_count} cells, "
                    f"header has {n_headers} ({title} section)")
                if row.raw_cell_count < n_headers:
                    # Too FEW cells means every column past the break point
                    # is misaligned — a value under "Date closed" may
                    # actually be what belongs in "Reason". Checking those
                    # columns anyway would report a symptom of this same bug
                    # as a second, unrelated violation, which is noise, not
                    # signal.
                    continue
                # Too MANY cells is different: the leading cells still line
                # up with the headers (parse_tracker built the Row from
                # exactly those, dropping only the excess), so the ISO-date
                # and duplicate checks below still apply to them — only the
                # unpositioned trailing cell(s) are lost.

            for column in date_columns:
                cell = (row.get(column) or "").strip()
                if cell and not _ISO_DATE.search(cell):
                    violations.append(
                        f"line {row.line}: {column} {cell!r} has no ISO date ({title} section)")

            if gate_duplicates:
                company = (row.get("Company") or "").strip().lower()
                role = (row.get("Role") or "").strip().lower()
                if company and role:
                    dup_key = (company, role)
                    if dup_key in seen_company_role:
                        violations.append(
                            f"duplicate Company+Role in {title} section: "
                            f"{row.get('Company')} / {row.get('Role')} "
                            f"at lines {seen_company_role[dup_key]} and {row.line}")
                    else:
                        seen_company_role[dup_key] = row.line

    return violations
