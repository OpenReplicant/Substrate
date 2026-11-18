#!/usr/bin/env python3
"""The store's database (S-135): made once beside v1's, which stay in the same volume until imported from.

    bin/in-tools python3 scripts/db.py init        # wait for Postgres, make the `substrate` database if missing,
                                                   # and apply the store's schema (store/sql/) not yet applied
    bin/in-tools python3 scripts/db.py import-v1   # v1's people's statements and open decisions (store/import_v1.py)

It waits up to a minute for Postgres to take connections, and stops at once on a refused password: that never
comes right by waiting, and most often means the volume outlived the .env that made it (the setup skill says how
to keep the data).
"""
from __future__ import annotations

import sys
import time

HERE = __import__("os").path.dirname(__file__)
sys.path.insert(0, HERE)
sys.path.insert(0, __import__("os").path.join(HERE, ".."))
from gateway import settings  # noqa: E402  (the same env_value path, so the secrets slot is honoured)

DB = "substrate"


def admin_url(env: dict[str, str], db: str = "postgres") -> str:
    return f"postgresql://postgres:{env['POSTGRES_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}/{db}"


def connect(env: dict[str, str], db: str = "postgres"):
    import psycopg
    last = None
    for _ in range(30):
        try:
            return psycopg.connect(admin_url(env, db), autocommit=True, connect_timeout=5)
        except psycopg.OperationalError as e:
            if "password authentication failed" in str(e):
                raise SystemExit("  Postgres refused POSTGRES_PASSWORD from .env: the volume (DB_VOLUME) was made with another\n"
                                 "  one. Set the old one in .env, or reset it in the container (the setup skill, step 3).")
            last = e
            time.sleep(2)
    raise SystemExit(f"  Postgres did not take connections within a minute (scripts/logs.sh db): {last}")


def init(env: dict[str, str]) -> None:
    with connect(env) as c:
        if c.execute("select 1 from pg_database where datname = %s", (DB,)).fetchone():
            print(f"  database {DB}: present")
        else:
            c.execute(f"create database {DB} encoding 'UTF8' template template0")
            print(f"  database {DB}: made (pg_cron runs in it from Postgres's next start)")
    import store
    with connect(env, DB) as c:
        applied = store.migrate(c)
        graph = store.project(c)
    print(f"  the store's schema: {'applied ' + ', '.join(applied) if applied else 'up to date'}")
    if env.get("COMPANION_DB_PASSWORD"):
        companion_login(env)
    if env.get("JUDGE_DB_PASSWORD"):
        judge_login(env)
    print(f"  the store's graph: built, {graph['nodes']} nodes and {graph['edges']} edges")


def companion_login(env: dict[str, str]) -> None:
    """The companion's container's login (store/sql/006_logins.sql): a member of env_agent, so it may publish, act
    and read the queues it is given, and nothing else; then its actuators and queues (environment.companion)."""
    from psycopg import sql
    with connect(env, DB) as c:
        c.autocommit = True
        if not c.execute("select 1 from pg_roles where rolname = 'companion'").fetchone():
            c.execute("create role companion login")
        c.execute(sql.SQL("alter role companion password {}").format(sql.Literal(env["COMPANION_DB_PASSWORD"])))
        c.execute("grant env_agent to companion")
        from environment import Env
        from environment.companion import setup
        setup(Env(c))


def judge_login(env: dict[str, str]) -> None:
    """The judge's login (store/sql/007_components.sql): a member of env_judge, so it reads the record and records
    verdicts, and cannot activate a component or decide a proposal."""
    from psycopg import sql
    with connect(env, DB) as c:
        c.autocommit = True
        if not c.execute("select 1 from pg_roles where rolname = 'judge'").fetchone():
            c.execute("create role judge login")
        c.execute(sql.SQL("alter role judge password {}").format(sql.Literal(env["JUDGE_DB_PASSWORD"])))
        c.execute("grant env_judge to judge")
    print("  judge: login judge (env_judge)")


def import_v1(env: dict[str, str]) -> None:
    import store
    from store import import_v1
    with connect(env, "workbench") as v1, connect(env, DB) as c:
        v1.execute("set default_transaction_read_only = on")
        counts = import_v1.run(v1, store.Store(c, actor="store:import-v1"))
    print("  imported from v1: " + ", ".join(f"{v} {k}" for k, v in counts.items()))


def main() -> None:
    if sys.argv[1:] == ["init"]:
        init(settings())
    elif sys.argv[1:] == ["import-v1"]:
        import_v1(settings())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
