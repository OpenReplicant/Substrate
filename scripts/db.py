#!/usr/bin/env python3
"""One database, the kernel's (S-202; the kernel's D-126): `kernel` holds the Knowledge Kernel's schemas (S-154) and the
environment's schema `env` beside them. v1's databases stay in the same volume.

    bin/in-tools python3 scripts/db.py init        # wait for Postgres, make the `kernel` database if missing, and apply
                                                   # the environment's schema (environment/sql/) not yet applied

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

KERNEL_DB = "kernel"      # the Knowledge Kernel's database in the same Postgres (S-154); its schema is installed by kk init
DB = KERNEL_DB            # the environment's schema lives there too (S-202); the `substrate` database is gone


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
        if c.execute("select 1 from pg_database where datname = %s", (KERNEL_DB,)).fetchone():
            print(f"  database {KERNEL_DB}: present (the kernel's schema: scripts/kernel.sh init)")
        else:
            c.execute(f"create database {KERNEL_DB} encoding 'UTF8' template template0")
            print(f"  database {KERNEL_DB}: made (the kernel's schema: scripts/kernel.sh init; pg_cron runs in it from Postgres's next start)")
    from environment.db import migrate
    with connect(env, DB) as c:
        applied = migrate(c)
    print(f"  the environment's schema: {'applied ' + ', '.join(applied) if applied else 'up to date'}")


def main() -> None:
    if sys.argv[1:] == ["init"]:
        init(settings())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
