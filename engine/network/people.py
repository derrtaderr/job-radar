"""People files: what a Clay lookup found at one company, and when.

One YAML file per company under config/network/people/, written only by
`network_cli.py add` after the /paths session has done the lookup. The
lookup date is part of the record because people change jobs: a file older
than thirty days renders as stale.

`result: none` is a real answer ("looked, found nobody") and is kept apart
from having no file at all ("never looked"). A failed lookup writes nothing,
so it can never pass for a `none`.
"""
from __future__ import annotations

import datetime
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from engine.network.company import canonical, company_slug, slugify
from engine.network.errors import NetworkError

ROLES = ("hiring_manager", "recent_hire")
RESULTS = ("found", "none")
STATUSES = ("current", "left_company")


@dataclass(frozen=True)
class Person:
    slug: str
    name: str
    title: str
    url: str
    role: str
    started: str
    status: str


@dataclass(frozen=True)
class PeopleFile:
    company: str
    looked_up: datetime.date
    source: str
    result: str
    people: tuple


def _date(value, where: str) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise NetworkError(
            f"{where}: looked_up {value!r} is not a YYYY-MM-DD date") from exc


def parse_people(text: str, where: str) -> PeopleFile:
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise NetworkError(f"bad yaml in {where}: {exc}") from exc
    if not isinstance(raw, dict):
        raise NetworkError(
            f"{where}: expected a mapping with company, looked_up, source, result")
    for key in ("company", "looked_up", "source", "result"):
        if not raw.get(key):
            raise NetworkError(f"{where}: missing required key {key!r}")
    if raw["result"] not in RESULTS:
        raise NetworkError(
            f"{where}: result {raw['result']!r} is not one of {', '.join(RESULTS)}")

    people = []
    for idx, entry in enumerate(raw.get("people") or []):
        at = f"{where} person #{idx + 1}"
        if not isinstance(entry, dict) or not entry.get("name"):
            raise NetworkError(f"{at}: needs at least a name")
        role = entry.get("role")
        if role not in ROLES:
            raise NetworkError(f"{at}: role {role!r} is not one of {', '.join(ROLES)}")
        status = entry.get("status") or "current"
        if status not in STATUSES:
            raise NetworkError(
                f"{at}: status {status!r} is not one of {', '.join(STATUSES)}")
        people.append(Person(
            slug=str(entry.get("slug") or slugify(entry["name"])),
            name=str(entry["name"]),
            title=str(entry.get("title") or ""),
            url=str(entry.get("url") or ""),
            role=role,
            started=str(entry.get("started") or ""),
            status=status))

    if raw["result"] == "found" and not people:
        raise NetworkError(f"{where}: result is found but it lists no people")
    if raw["result"] == "none" and people:
        raise NetworkError(f"{where}: result is none but it lists people")
    return PeopleFile(company=str(raw["company"]),
                      looked_up=_date(raw["looked_up"], where),
                      source=str(raw["source"]), result=raw["result"],
                      people=tuple(people))


def render_people(pf: PeopleFile) -> str:
    data = {
        "company": pf.company,
        "looked_up": pf.looked_up.isoformat(),
        "source": pf.source,
        "result": pf.result,
        "people": [
            {key: value for key, value in (
                ("slug", p.slug), ("name", p.name), ("title", p.title),
                ("url", p.url), ("role", p.role), ("started", p.started),
                ("status", p.status)) if value}
            for p in pf.people],
    }
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def load_people_dir(people_dir, aliases) -> dict:
    """{canonical company: PeopleFile}. A missing directory is empty."""
    d = Path(people_dir)
    if not d.is_dir():
        return {}
    out = {}
    for path in sorted(d.glob("*.yaml")):
        pf = parse_people(path.read_text(), str(path))
        out[canonical(pf.company, aliases)] = pf
    return out


def write_people(people_dir, pf: PeopleFile, aliases) -> Path:
    """Replace the company's file atomically (temp file, then rename), so a
    crash can never leave half a lookup that parses as a whole one."""
    d = Path(people_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{company_slug(pf.company, aliases)}.yaml"
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(render_people(pf))
    os.replace(tmp, path)
    return path


def mark_left(pf: PeopleFile, slug: str) -> PeopleFile:
    if slug not in {p.slug for p in pf.people}:
        raise NetworkError(
            f"nobody with slug {slug!r} in the {pf.company} people file")
    people = tuple(replace(p, status="left_company") if p.slug == slug else p
                   for p in pf.people)
    return replace(pf, people=people)
