"""Fixes from the whole-branch review. Each test is the reviewer's repro."""
import datetime
import shutil
from pathlib import Path

from engine.network.connections import Connection
from engine.network.errors import NetworkError
from engine.network.flow import due, gate
from engine.network.network import Network, load_network
from engine.network.paths import ContactPath, PathReport, resolve_paths
from engine.network.touches import Touch

D = datetime.date
WARM = ContactPath("warm", "ana-rivera", "Ana Rivera", "Engineer", "2019-01-15")


def report(*paths, company="Harborlight"):
    return PathReport(company=company, paths=tuple(paths), checks=(),
                      status="found" if paths else "unresearched",
                      looked_up=None, stale=False, export_date=None)


def T(date, state, slug="ana-rivera", path="warm", company="Harborlight"):
    return Touch(date=date, posting_id="", company=company, person_slug=slug,
                 path=path, motive="", hook_level="", register="", control="no",
                 state=state, note="")


# I-1
def test_due_stops_saying_apply_once_the_company_has_an_application():
    touches = [T("2026-10-01", "asked"), T("2026-10-07", "applied", slug="", path="")]
    items, _ = due(touches, {}, {}, D(2026, 10, 9))
    assert not any("Apply today" in i.message for i in items)


# I-2
def test_a_warm_connection_who_left_drops_out(tmp_path):
    d = tmp_path / "network"
    d.mkdir()
    (d / "connections.csv").write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Ana,Rivera,https://www.linkedin.com/in/example,,Harborlight,Eng,15 Jan 2019\n")
    (d / "touches.csv").write_text(
        "date,posting_id,company,person_slug,path,motive,hook_level,register,control,state,note\n"
        "2026-10-01,,Harborlight,ana-rivera,warm,,,,no,asked,\n"
        "2026-10-02,,Harborlight,ana-rivera,warm,,,,no,left_company,\n")
    rep = resolve_paths("Harborlight", load_network(d), D(2026, 10, 9))
    assert [p.kind for p in rep.paths] == []


# I-3
def test_a_plain_reply_is_not_a_referral_and_holds_the_gate():
    touches = [T("2026-10-05", "asked"), T("2026-10-06", "replied")]
    held = gate(report(WARM), touches, {}, D(2026, 10, 7))
    assert held.code == 4 and "referred" in held.message
    # three business days after the reply with no referral confirmed: move on
    assert gate(report(WARM), touches, {}, D(2026, 10, 9)).code == 0


# I-4
def test_a_non_utf8_export_is_a_network_error_not_a_crash(tmp_path):
    d = tmp_path / "network"
    d.mkdir()
    (d / "connections.csv").write_bytes(
        b"First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        b"Jos\xe9,M,u,,Caf\xe9 Co,Eng,15 Jan 2019\n")
    try:
        load_network(d)
    except NetworkError as exc:
        assert "Excel" in str(exc)
    else:
        raise AssertionError("expected NetworkError")


# I-5
def test_paths_table_says_whether_a_lookup_happened(tmp_path, capsys):
    from tools.network_cli import main
    cfg_dir = tmp_path / "config"
    shutil.copytree(Path(__file__).parent.parent / "config.example", cfg_dir)
    assert main(["--config", str(cfg_dir), "paths", "Cobalt Grid"],
                today=D(2026, 10, 12)) == 0
    out = capsys.readouterr().out
    assert "| Company | Path | Lookup |" in out
    assert "| Cobalt Grid | warm: Riley Example, connected 2019 | never |" in out


# M-1 (re-graded Important)
def test_an_old_override_does_not_wave_through_a_new_posting():
    touches = [T("2026-01-05", "override", slug="", path="")]
    assert gate(report(WARM), touches, {}, D(2026, 10, 9)).code == 3


# M-4 (re-graded Important)
def test_doctor_warns_when_the_connections_are_still_the_fictional_example(tmp_path):
    from engine.radar.config import load_config
    from tools.doctor import _check_network
    cfg_dir = tmp_path / "config"
    shutil.copytree(Path(__file__).parent.parent / "config.example", cfg_dir)
    result = _check_network(load_config(cfg_dir), None)
    assert result.ok == "warn" and "example" in result.detail
