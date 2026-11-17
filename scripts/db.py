#!/usr/bin/env python3
"""The store's database (S-135): made once beside v1's, which stay in the same volume until imported from.

    bin/in-tools python3 scripts/db.py init    # wait for Postgres, then make the `substrate` database if missing

It waits up to a minute for Postgres to take connections, and stops at once on a refused password: that never
comes right by waiting, and most often means the volume outlived the .env that made it (the setup skill says how
to keep the data). The store's schema arrives in step 3b; until then this only makes the database.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__file__))
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
            return
        c.execute(f"create database {DB} encoding 'UTF8' template template0")
    print(f"  database {DB}: made (pg_cron runs in it from Postgres's next start)")


def main() -> None:
    if sys.argv[1:] == ["init"]:
        init(settings())
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
