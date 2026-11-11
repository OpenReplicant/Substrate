#!/usr/bin/env python3
"""A hook's own record of each run, for handlers:run (plugins/handlers/README.md, "Sources": jsonl). Standard library
only: hooks run on the host. One JSON line per run in .state/calls/hooks.jsonl (gitignored); no input content, only
which hook, when, how long and its exit code.

    python3 scripts/calls.py record STREAM HANDLER STARTED EXIT    # STARTED: epoch seconds, from `date +%s.%N`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / ".state" / "calls" / "hooks.jsonl"


def record(stream: str, handler: str, started: float, exit_code: int, note: str | None = None) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        line = {"stream": stream, "handler": handler, "started": round(started, 3),
                "seconds": round(max(time.time() - started, 0), 3), "exit": int(exit_code)}
        if note:
            line["note"] = note
        with LOG.open("a") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass   # a record that cannot be written must never fail the hook


if __name__ == "__main__":
    if len(sys.argv) != 6 or sys.argv[1] != "record":
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        sys.exit(2)
    try:
        record(sys.argv[2], sys.argv[3], float(sys.argv[4]), int(sys.argv[5]))
    except ValueError:
        pass
