"""Reads LinkedIn's own data-export Connections.csv: the user's first-degree
network, with the company each connection listed when the export was made.

Read from the official export rather than scraped. The file's modification
date is carried as the EXPORT DATE and rendered beside every warm path,
because a connection's company is only as current as the export it came from.
"""
from __future__ import annotations

import csv
import datetime
import io
from dataclasses import dataclass
from pathlib import Path

from engine.network.company import slugify
from engine.network.errors import NetworkError

REQUIRED_COLUMNS = ("First Name", "Last Name", "URL", "Company", "Position",
                    "Connected On")


@dataclass(frozen=True)
class Connection:
    name: str
    url: str
    company: str
    position: str
    connected_on: str  # ISO date when parseable, otherwise the raw cell

    @property
    def slug(self) -> str:
        return slugify(self.name)


def _iso(raw: str) -> str:
    """LinkedIn writes '15 Jan 2019'. Anything else is kept verbatim rather
    than guessed at: a wrong year beside a name is worse than an odd string."""
    text = (raw or "").strip()
    try:
        return datetime.datetime.strptime(text, "%d %b %Y").date().isoformat()
    except ValueError:
        return text


def parse_connections(text: str, where: str = "Connections.csv") -> list:
    """Every connection with a company to match on.

    The export opens with a notes preamble, so the header is found by its
    first cell rather than assumed to be line one. Rows with a blank Company
    are skipped: LinkedIn leaves it empty for some members, and a row with no
    company cannot be a path to any posting.
    """
    lines = text.lstrip("﻿").splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.lstrip("﻿").startswith("First Name,")), None)
    if start is None:
        raise NetworkError(
            f"{where}: no header row starting 'First Name,' — is this LinkedIn's "
            "Connections.csv from Settings → Data privacy → Get a copy of your data?")
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    fields = [f.lstrip("﻿") for f in (reader.fieldnames or [])]
    reader.fieldnames = fields
    missing = [c for c in REQUIRED_COLUMNS if c not in fields]
    if missing:
        raise NetworkError(
            f"{where}: missing column(s) {', '.join(missing)} — re-export the file "
            "from LinkedIn rather than editing it")

    connections = []
    for raw in reader:
        company = (raw.get("Company") or "").strip()
        if not company:
            continue
        first = (raw.get("First Name") or "").strip()
        last = (raw.get("Last Name") or "").strip()
        connections.append(Connection(
            name=f"{first} {last}".strip(),
            url=(raw.get("URL") or "").strip(),
            company=company,
            position=(raw.get("Position") or "").strip(),
            connected_on=_iso(raw.get("Connected On") or "")))
    return connections


def load_connections(path) -> tuple:
    """(connections, export_date). A missing file is ([], None): the warm
    path is simply off until the person drops their export in."""
    p = Path(path)
    if not p.exists():
        return [], None
    exported = datetime.date.fromtimestamp(p.stat().st_mtime)
    try:
        text = p.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NetworkError(
            f"{p} is not UTF-8 ({exc.reason} at byte {exc.start}). LinkedIn exports "
            "UTF-8; this usually means it was opened and re-saved in Excel. "
            "Re-export it and copy it in without re-saving") from exc
    try:
        return parse_connections(text, where=str(p)), exported
    except csv.Error as exc:
        raise NetworkError(f"{p}: unreadable CSV ({exc}) — re-export it from LinkedIn") from exc
