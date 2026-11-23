"""The environment's database: where it is, and its schema `env` (plan step 3c; moved out of `store/` in S-156).

    from environment.db import database_url, migrate
    migrate(conn)          # apply the files in environment/sql/ not yet applied; returns their names

The address is ENV_URL, else STORE_URL, else the kernel's database (`kernel`) from .env: the schema lives beside the
kernel's (S-202, the kernel's D-126). The files keep the numbers they had beside the old store's; what is applied is
recorded in `public.env_migration`.
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
