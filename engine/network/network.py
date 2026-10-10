"""Everything under config/network/ that path resolution reads, loaded once.
A missing directory is an empty network: the warm path is off, not broken."""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engine.network.company import load_aliases
from engine.network.connections import load_connections
from engine.network.people import load_people_dir


@dataclass(frozen=True)
class Network:
    connections: tuple
    export_date: Optional[datetime.date]
    people: dict
    aliases: dict


def load_network(network_dir) -> Network:
    if network_dir is None or not Path(network_dir).is_dir():
        return Network((), None, {}, {})
    d = Path(network_dir)
    aliases = load_aliases(d / "aliases.yaml")
    connections, exported = load_connections(d / "connections.csv")
    return Network(tuple(connections), exported,
                   load_people_dir(d / "people", aliases), aliases)
