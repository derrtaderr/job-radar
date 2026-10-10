"""Path resolution: who the person can reach at a company, best first."""
import datetime

from engine.network.connections import Connection
from engine.network.network import Network, load_network
from engine.network.paths import render_path_cell, resolve_paths
from engine.network.people import PeopleFile, Person

TODAY = datetime.date(2026, 10, 12)


def _conn(name, company, since="2019-01-15"):
    return Connection(name=name, url="https://www.linkedin.com/in/example",
                      company=company, position="Engineer", connected_on=since)


def _person(name, role, status="current", started=""):
    return Person(slug=name.lower().replace(" ", "-"), name=name, title="VP Growth",
                  url="", role=role, started=started, status=status)


def _pf(company, people, looked_up=datetime.date(2026, 10, 10), result="found"):
    return PeopleFile(company=company, looked_up=looked_up, source="clay",
                      result=result, people=tuple(people))


def _net(connections=(), people=None):
    return Network(connections=tuple(connections), export_date=datetime.date(2026, 10, 1),
                   people=people or {}, aliases={})


def test_warm_beats_clay_paths_and_counts_the_rest():
    net = _net([_conn("Ana Rivera", "Northwind Analytics, Inc.")],
               {"northwind analytics": _pf("Northwind Analytics", [
                   _person("Dee Marsh", "hiring_manager"),
                   _person("Eli Park", "recent_hire")])})
    report = resolve_paths("Northwind Analytics", net, TODAY)
    assert [p.kind for p in report.paths] == ["warm", "recent_hire", "cold_hm"]
    assert report.status == "found"
    assert render_path_cell(report) == "warm: Ana Rivera, connected 2019 (+2)"


def test_none_and_unresearched_are_different():
    looked = _net(people={"cobalt grid": _pf("Cobalt Grid", [], result="none")})
    assert resolve_paths("Cobalt Grid", looked, TODAY).status == "none"
    assert render_path_cell(resolve_paths("Cobalt Grid", looked, TODAY)) == \
        "none (looked up 2026-10-10)"
    assert render_path_cell(resolve_paths("Cobalt Grid", _net(), TODAY)) == "unresearched"


def test_person_who_left_is_not_a_path():
    net = _net(people={"harborlight": _pf("Harborlight", [
        _person("Dee Marsh", "hiring_manager", status="left_company"),
        _person("Eli Park", "recent_hire")])})
    report = resolve_paths("Harborlight", net, TODAY)
    assert [p.name for p in report.paths] == ["Eli Park"]


def test_stale_lookup_is_marked():
    net = _net(people={"harborlight": _pf(
        "Harborlight", [_person("Eli Park", "recent_hire")],
        looked_up=datetime.date(2026, 9, 1))})
    assert render_path_cell(resolve_paths("Harborlight", net, TODAY)).endswith("[stale]")


def test_short_substring_is_a_capped_check_never_warm():
    net = _net([_conn(f"P{i} Q", f"Cobalt Grid Unit {i}") for i in range(5)])
    report = resolve_paths("Cobalt Grid", net, TODAY)
    assert report.status == "unresearched" and not report.paths
    cell = render_path_cell(report)
    assert cell.startswith("unresearched; check: P0 Q at Cobalt Grid Unit 0?")
    assert cell.endswith("(+2 more)")


def test_load_network_from_disk(tmp_path):
    d = tmp_path / "network"
    (d / "people").mkdir(parents=True)
    (d / "connections.csv").write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Ana,Rivera,https://www.linkedin.com/in/example,,Harborlight,Eng,15 Jan 2019\n")
    net = load_network(d)
    assert len(net.connections) == 1 and net.export_date is not None
    assert load_network(tmp_path / "nope") == Network((), None, {}, {})
    assert load_network(None) == Network((), None, {}, {})
