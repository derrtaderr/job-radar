#!/usr/bin/env python3
"""job-radar entry point. All behavior lives in engine/radar/cli.py; this file
exists so `python3 radar.py` works from a fresh clone."""
import sys

from engine.radar.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
