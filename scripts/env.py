#!/usr/bin/env python3
"""The real-time environment from the command line (plan step 3c). A proposal is decided in the desktop's Review (the
kernel's review lane, S-219), not here: the environment module records that decision on the action.

    bin/in-tools python3 scripts/env.py waiting                        # proposals waiting for a person
    bin/in-tools python3 scripts/env.py publish KEY JSON --as SOURCE   # e.g. owner.inbox.message '{"text":"hi"}'
    bin/in-tools python3 scripts/env.py actuators                      # each actuator, its gate and queue
    bin/in-tools python3 scripts/env.py gate NAME free|propose|deny --as NAME
    bin/in-tools python3 scripts/env.py queues                         # each queue: waiting, hidden, archived
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT)]
from db import DB, connect  # noqa: E402
from gateway import settings  # noqa: E402
from environment import Env  # noqa: E402


def main(argv: list[str]) -> None:
    who = None
    if "--as" in argv:
        i = argv.index("--as")
        who, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    with connect(settings(), DB) as c:
        e = Env(c)
        if cmd == "waiting":
            for w in e.waiting():
                print(f"{w['id']}  {w['actuator']}  {json.dumps(w['input'])}  by {w['caller']}  at {w['at']:%Y-%m-%d %H:%M}")
        elif cmd == "publish" and len(args) == 2 and who:
            print(f"signal {e.publish(args[0], json.loads(args[1]), who)}")
        elif cmd == "actuators":
            for n, g, q, d in c.execute("select name, gate, queue, coalesce(description, '') from env.actuator order by name"):
                print(f"{n}  {g}  {q}  {d}")
        elif cmd == "gate" and len(args) == 2 and who:
            print(e.actuator(args[0], args[1], who))
        elif cmd == "queues":
            for q, in c.execute("select queue_name from pgmq.meta order by 1"):
                vis, hid = c.execute(f"select count(*) filter (where vt <= now()), count(*) filter (where vt > now()) "
                                     f"from pgmq.q_{q}").fetchone()
                arch = c.execute(f"select count(*) from pgmq.a_{q}").fetchone()[0]
                print(f"{q}  {vis} waiting, {hid} hidden, {arch} archived")
        else:
            sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
