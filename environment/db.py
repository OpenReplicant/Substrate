"""The environment's database: where it is, and its schema `env` (plan step 3c; moved out of `store/` in S-156).

    from environment.db import database_url, migrate
    migrate(conn)          # apply the files in environment/sql/ not yet applied; returns their names

The address is STORE_URL (the name the compose services already set; ENV_URL is read first if it is set), else the
`substrate` database from .env. The schema files keep the names 005, 006 and 007 they had when they lived beside the
store's: a database that applied them then has them recorded in `public.store_migration`, and `migrate` carries
those records into `public.env_migration` the first time it runs, so nothing is applied twice.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SQL = Path(__file__).parent / "sql"


def database_url() -> str:
    for name in ("ENV_URL", "STORE_URL"):
        if os.environ.get(name):
            return os.environ[name]
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from db import DB, admin_url  # noqa: E402
    from gateway import settings  # noqa: E402
    return admin_url(settings(), DB)


def migrate(conn) -> list[str]:
    """Apply the schema files not yet applied, each in its own transaction; returns their names."""
    conn.execute("create table if not exists public.env_migration (name text primary key, applied_at timestamptz not null default now())")
    names = [f.name for f in sorted(SQL.glob("*.sql"))]
    if conn.execute("select to_regclass('public.store_migration')").fetchone()[0]:      # applied while they were the store's
        conn.execute("insert into public.env_migration (name, applied_at) select name, applied_at from public.store_migration "
                     "where name = any(%s) on conflict do nothing", (names,))
    done = {r[0] for r in conn.execute("select name from public.env_migration")}
    applied = []
    for f in sorted(SQL.glob("*.sql")):
        if f.name in done:
            continue
        with conn.transaction():
            conn.execute(f.read_text())
            conn.execute("insert into public.env_migration (name) values (%s)", (f.name,))
        applied.append(f.name)
    return applied
