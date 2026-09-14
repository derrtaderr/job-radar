"""Template registry — the lookup layer /apply (Task 9) uses to resolve a
template name to its compiled source, kind, and page limit. Same loud-failure
standard as the config loader (engine/radar/config.py): missing or mistyped
fields raise RegistryError naming the offending entry, an unknown name in
.get()/.default() raises naming the known ones, so a typo is a one-line fix
rather than a silent wrong-template compile.

Custom templates are appended as extra `templates:` entries (documented in
the /add-template command, Task 9); their sources may live in gitignored
templates/custom/ since a custom template can embed personal header data.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REGISTRY_RELATIVE_PATH = Path("templates") / "registry.yaml"
KNOWN_KINDS = ("resume", "cover")


class RegistryError(Exception):
    """Raised for anything wrong with templates/registry.yaml: missing file,
    malformed entry, a source that doesn't exist, or a lookup for a name/kind
    the registry doesn't know. Always names the offending entry so fixing it
    is a one-line lookup, not an archaeology project."""


@dataclass
class Template:
    name: str
    source: Path
    kind: str
    page_limit: int


@dataclass
class Registry:
    templates: dict  # name -> Template
    defaults: dict  # kind -> default template name

    def get(self, name: str) -> Template:
        try:
            return self.templates[name]
        except KeyError:
            known = ", ".join(sorted(self.templates))
            raise RegistryError(
                f"unknown template {name!r} — known templates: {known}"
            ) from None

    def default(self, kind: str) -> Template:
        try:
            name = self.defaults[kind]
        except KeyError:
            known = ", ".join(sorted(self.defaults))
            raise RegistryError(
                f"unknown kind {kind!r} — known kinds: {known}"
            ) from None
        return self.get(name)


def _require(data: dict, key: str, where: str):
    value = data.get(key)
    if value is None:
        raise RegistryError(f"missing required key {key!r} in {where}")
    return value


def _require_int(data: dict, key: str, where: str) -> int:
    # Same guard as the config loader: PyYAML parses yes/no/true/false as
    # bool, and bool is a subclass of int, so a typo'd `page_limit: yes`
    # would silently pass an `isinstance(x, int)` check as 1. A float
    # (`2.0`) passes the "it's a number" instinct too but isn't the int
    # contract this field promises. Reject both explicitly.
    value = _require(data, key, where)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RegistryError(f"{key!r} in {where} must be an integer, got {value!r}")
    return value


def _load_yaml(path: Path, where: str) -> dict:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise RegistryError(f"bad yaml in {where}: {exc}") from exc
    return data or {}


def load_registry(repo_root: Path) -> Registry:
    repo_root = Path(repo_root)
    registry_path = repo_root / REGISTRY_RELATIVE_PATH
    if not registry_path.exists():
        raise RegistryError(
            f"no registry.yaml at {registry_path} — expected "
            f"{REGISTRY_RELATIVE_PATH} under the repo root"
        )

    data = _load_yaml(registry_path, "registry.yaml")

    defaults = {}
    for kind in KNOWN_KINDS:
        defaults[kind] = _require(data, f"default_{kind}", "registry.yaml")

    entries_raw = _require(data, "templates", "registry.yaml")
    if not isinstance(entries_raw, list):
        raise RegistryError(
            f"{'templates'!r} in registry.yaml must be a list, got {entries_raw!r}"
        )

    templates = {}
    for idx, entry in enumerate(entries_raw):
        if not isinstance(entry, dict):
            raise RegistryError(
                f"registry.yaml templates[{idx}] must be a mapping, got {entry!r}"
            )
        name = _require(entry, "name", f"registry.yaml templates[{idx}]")
        where = f"registry.yaml entry {name!r}"

        source_raw = _require(entry, "source", where)
        kind = _require(entry, "kind", where)
        if kind not in KNOWN_KINDS:
            raise RegistryError(
                f"{where} has unknown kind {kind!r} — must be one of {', '.join(KNOWN_KINDS)}"
            )
        page_limit = _require_int(entry, "page_limit", where)

        source = (repo_root / source_raw).resolve()
        if not source.exists():
            raise RegistryError(f"{where} source {source} does not exist")

        if name in templates:
            raise RegistryError(f"registry.yaml has duplicate entry {name!r}")

        templates[name] = Template(name=name, source=source, kind=kind, page_limit=page_limit)

    for kind, default_name in defaults.items():
        if default_name not in templates:
            raise RegistryError(
                f"registry.yaml default_{kind} {default_name!r} is not a known template"
            )

    return Registry(templates=templates, defaults=defaults)
