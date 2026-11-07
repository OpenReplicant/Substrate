"""The message bus (S-21, S-24): pgmq in its own database, `substrate`, beside kernel's `kk` in the same Postgres.
kernel's Postgres image carries the extension (kernel D-94); this creates it where substrate uses it.

Idempotent, run by scripts/bus.sh on every `scripts/up.sh`: the login `substrate_bus` (password on stdin), the
database it owns, the pgmq extension (updated in place when the image carries a newer version), the queues in
deploy/bus/queues.txt, and that login's rights on them. Kernel's database is never touched: claims stay
kernel's (change sets only); the bus carries work and notices between the parts.

Runs inside the substrate-tools container (kernel's Python, psycopg), as the Postgres superuser from
KK_ADMIN_URL.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROLE, DB = "substrate_bus", "substrate"


def queues(root: Path) -> list[str]:
    out = []
    for line in (root / "deploy/bus/queues.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line.split()[0])
    return out


def check(admin: str, root: Path) -> int:
    """For scripts/check.sh: the extension is there and every queue in queues.txt exists."""
    params = conninfo_to_dict(admin)
    params["dbname"] = DB
    try:
        with psycopg.connect(make_conninfo(**params), connect_timeout=5) as c:
            have = {r[0] for r in c.execute("select queue_name from pgmq.list_queues()")}
            version = c.execute("select extversion from pg_extension where extname = 'pgmq'").fetchone()[0]
    except Exception as e:
        print(f"no bus: {type(e).__name__} (scripts/bus.sh)")
        return 1
    missing = [q for q in queues(root) if q not in have]
    print(f"pgmq {version}, queues {', '.join(sorted(have))}" + (f"; missing {', '.join(missing)}" if missing else ""))
    return 1 if missing else 0


def main() -> int:
    admin = os.environ.get("KK_ADMIN_URL")
    if "--check" in sys.argv:
        return check(admin or "", Path(__file__).resolve().parent.parent)
    password = sys.stdin.read().strip()
    if not admin or not password:
        print("needs KK_ADMIN_URL and the bus password on stdin", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parent.parent

    with psycopg.connect(admin, autocommit=True) as c:
        if c.execute("select 1 from pg_roles where rolname = %s", (ROLE,)).fetchone():
            c.execute(sql.SQL("alter role {} with login password {}").format(sql.Identifier(ROLE), sql.Literal(password)))
        else:
            c.execute(sql.SQL("create role {} with login password {}").format(sql.Identifier(ROLE), sql.Literal(password)))
        if not c.execute("select 1 from pg_database where datname = %s", (DB,)).fetchone():
            c.execute(sql.SQL("create database {} owner {}").format(sql.Identifier(DB), sql.Identifier(ROLE)))

    params = conninfo_to_dict(admin)
    params["dbname"] = DB
    with psycopg.connect(make_conninfo(**params), autocommit=True) as c:
        avail = c.execute("select default_version, installed_version from pg_available_extensions where name = 'pgmq'").fetchone()
        if not avail:
            print("pgmq is not in this Postgres image: update repos/kernel (kernel D-94), scripts/build.sh db, then restart db",
                  file=sys.stderr)
            return 1
        if avail[1] is None:
            c.execute("create extension pgmq")
        elif avail[1] != avail[0]:
            c.execute("alter extension pgmq update")
        have = {r[0] for r in c.execute("select queue_name from pgmq.list_queues()")}
        made = []
        for q in queues(root):
            if q not in have:
                c.execute("select pgmq.create(%s)", (q,))
                made.append(q)
        r = sql.Identifier(ROLE)
        c.execute(sql.SQL("grant usage on schema pgmq to {}").format(r))
        c.execute(sql.SQL("grant select, insert, update, delete on all tables in schema pgmq to {}").format(r))
        c.execute(sql.SQL("grant usage, select on all sequences in schema pgmq to {}").format(r))
        c.execute(sql.SQL("grant execute on all functions in schema pgmq to {}").format(r))
        version = c.execute("select extversion from pg_extension where extname = 'pgmq'").fetchone()[0]
    print(f"  bus: pgmq {version} in database {DB}; queues {', '.join(queues(root))}"
          + (f" (created {', '.join(made)})" if made else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
