"""Real names live only under gitignored paths. Pinned with git itself, so a
.gitignore edit that would publish someone's network fails here first."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _ignored(rel: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO).returncode == 0


def test_network_and_outreach_drafts_are_gitignored():
    assert _ignored("config/network/connections.csv")
    assert _ignored("config/network/touches.csv")
    assert _ignored("config/network/people/harborlight.yaml")
    assert _ignored("apply-out/harborlight/outreach-ana-rivera.md")
