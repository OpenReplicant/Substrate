#!/usr/bin/env python3
"""The databases beside v1's, which stay in the same volume: `substrate` (the environment's schema `env`) and `kernel`
(the Knowledge Kernel's, S-154).

    bin/in-tools python3 scripts/db.py init        # wait for Postgres, make the `substrate` and `kernel` databases if
                                                   # missing, and apply the environment's schema (environment/sql/) not yet
                                                   # applied

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
KERNEL_DB = "kernel"      # the Knowledge Kernel's database in the same Postgres (S-154); its schema is installed by kk init


def admin_url(env: dict[str, str], db: str = "postgres") -> str:
    return f"postgresql://postgres:{env['POSTGRES_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}/{db}"


def kernel_url(env: dict[str, str]) -> str:
    """The UI's way in to the kernel: KERNEL_URL from .env, else the kernel's own login kk_authenticator (which the
    UI switches to the read model's role) on the `kernel` database, from the host."""
    if env.get("KERNEL_URL"):
        return env["KERNEL_URL"]
    return (f"postgresql://kk_authenticator:{env['KK_AUTHENTICATOR_PASSWORD']}@127.0.0.1:{env.get('DB_PORT') or 5432}"
            f"/{KERNEL_DB}")


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
    with connect(env) as c:
        if c.execute("select 1 from pg_database where datname = %s", (KERNEL_DB,)).fetchone():
            print(f"  database {KERNEL_DB}: present (the kernel's schema: scripts/kernel.sh init)")
        else:
            c.execute(f"create database {KERNEL_DB} encoding 'UTF8' template template0")
            print(f"  database {KERNEL_DB}: made (the kernel's schema: scripts/kernel.sh init)")
    from environment.db import migrate
    with connect(env, DB) as c:
        applied = migrate(c)
    print(f"  the environment's schema: {'applied ' + ', '.join(applied) if applied else 'up to date'}")
    if env.get("COMPANION_DB_PASSWORD"):
        companion_login(env)
    if env.get("JUDGE_DB_PASSWORD"):
        judge_login(env)
    if env.get("WORKER_DB_PASSWORD"):
        worker_login(env)


def companion_login(env: dict[str, str]) -> None:
    """The companion's container's login (environment/sql/006_logins.sql): a member of env_agent, so it may publish, act
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


def worker_login(env: dict[str, str]) -> None:
    """The worker's container's login (S-163): a member of env_agent like the companion's; its actuators and queue
    (environment.worker)."""
    from psycopg import sql
    with connect(env, DB) as c:
        c.autocommit = True
        if not c.execute("select 1 from pg_roles where rolname = 'worker'").fetchone():
            c.execute("create role worker login")
        c.execute(sql.SQL("alter role worker password {}").format(sql.Literal(env["WORKER_DB_PASSWORD"])))
        c.execute("grant env_agent to worker")
        from environment import Env
        from environment.worker import setup
        setup(Env(c))


def judge_login(env: dict[str, str]) -> None:
    """The judge's login (environment/sql/007_components.sql): a member of env_judge, so it reads the record and records
    verdicts, and cannot activate a component or decide a proposal."""
    from psycopg import sql
    with connect(env, DB) as c:
        c.autocommit = True
        if not c.execute("select 1 from pg_roles where rolname = 'judge'").fetchone():
            c.execute("create role judge login")
        c.execute(sql.SQL("alter role judge password {}").format(sql.Literal(env["JUDGE_DB_PASSWORD"])))
        c.execute("grant env_judge to judge")
    print("  judge: login judge (env_judge)")


def main() -> None:
    if sys.argv[1:] == ["init"]:
        init(settings())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
