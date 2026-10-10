"""LinkedIn's Connections.csv, in the shape the export actually arrives in:
a notes preamble above the header, sometimes a BOM, quoted commas, blank
Company cells. Fictional people only."""
import datetime
import os

import pytest

from engine.network.connections import load_connections, parse_connections
from engine.network.errors import NetworkError

HEADER = "First Name,Last Name,URL,Email Address,Company,Position,Connected On"

EXPORT = (
    "﻿Notes:\n"
    '"When exporting your connection data, you may notice that some of the '
    'email addresses are missing."\n'
    "\n"
    f"{HEADER}\n"
    "Ana,Rivera,https://www.linkedin.com/in/example-ar,,"
    '"Northwind Analytics, Inc.","Head of Growth, Data",15 Jan 2019\n'
    "Ben,Okafor,https://www.linkedin.com/in/example-bo,,,Founder,02 Mar 2021\n"
    "Cy,Lund,https://www.linkedin.com/in/example-cl,,Cobalt Grid,Engineer,not a date\n"
)


def test_preamble_bom_quotes_and_blank_company():
    rows = parse_connections(EXPORT)
    assert [r.name for r in rows] == ["Ana Rivera", "Cy Lund"]  # blank company skipped
    ana = rows[0]
    assert ana.company == "Northwind Analytics, Inc."
    assert ana.position == "Head of Growth, Data"
    assert ana.connected_on == "2019-01-15"
    assert ana.slug == "ana-rivera"
    assert rows[1].connected_on == "not a date"  # kept raw, never invented


def test_no_header_names_the_file():
    with pytest.raises(NetworkError, match="Connections.csv"):
        parse_connections("Notes:\nnothing here\n")


def test_missing_column_is_named():
    with pytest.raises(NetworkError, match="Connected On"):
        parse_connections("First Name,Last Name,URL,Company,Position\nA,B,u,C,P\n")


def test_load_returns_export_date_and_tolerates_absence(tmp_path):
    assert load_connections(tmp_path / "connections.csv") == ([], None)
    path = tmp_path / "connections.csv"
    path.write_text(EXPORT)
    stamp = datetime.datetime(2026, 9, 1, 12, 0).timestamp()
    os.utime(path, (stamp, stamp))
    rows, exported = load_connections(path)
    assert len(rows) == 2
    assert exported == datetime.date(2026, 9, 1)
