"""A throwaway Knowledge Kernel for the tests that read Substrate's store from it (S-154).

    k = Kernel(ADMIN_URL)          # a database, `kk init`, and the kernel's validator running
    k.export(store_url)            # the store's items and statements as change sets, applied
    k.url                          # the kernel's login (kk_authenticator): the UI switches it to the read model's role
    k.close()                      # stops the validator and drops the database

Needs the kernel's `kk` command and its modules importable (`pip install -e repos/kernel`, or the kernel's image
(scripts/build.sh kernel), where scripts/test.sh runs the tests that need it), and a superuser in ADMIN_URL. Where
the kernel is not importable `available()` says why, and the tests that need it fail naming it.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from urllib.parse import quote, urlsplit

import psycopg

NEEDS = "needs the Knowledge Kernel's `kk` command and its modules (pip install -e repos/kernel, or scripts/build.sh kernel and scripts/test.sh)"


def available() -> str | None:
    """None when the kernel can be started here, else what is missing."""
    try:
        import encoder_substrate  # noqa: F401
        import kk  # noqa: F401
    except ImportError as e:
        return f"{e}: {NEEDS}"
    return None


def swap_db(url: str, db: str, user: str | None = None, password: str | None = None) -> str:
    u = urlsplit(url)
    host = u.hostname or "127.0.0.1"
    cred = f"{user}:{quote(password or '', safe='')}" if user else u.netloc.rsplit("@", 1)[0]
    return f"postgresql://{cred}@{host}:{u.port or 5432}/{db}"


class Kernel:
    def __init__(self, admin_url: str):
        why = available()
        if why:
            raise RuntimeError(why)
        self.admin_url = admin_url
        self.db = f"kernel_test_{os.getpid()}"
        self.password = secrets.token_hex(12)
        self.proc: subprocess.Popen | None = None
        with psycopg.connect(admin_url, autocommit=True) as a:
            a.execute(f'create database "{self.db}"')
        self.admin = swap_db(admin_url, self.db)
        self.url = swap_db(admin_url, self.db, "kk_authenticator", self.password)
        self.env = {**os.environ, "KK_ADMIN_URL": self.admin, "KK_AUTHENTICATOR_PASSWORD": self.password,
                    "KK_JWT_SECRET": secrets.token_hex(24), "DATABASE_URL": self.url}
        subprocess.run([sys.executable, "-m", "kk", "init"], check=True, env=self.env, capture_output=True)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.proc = subprocess.Popen([sys.executable, "-m", "kk", "serve", "--only", "validator", "--port", str(port)],
                                     env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def wait_applied(self, seconds: int = 60) -> None:
        with psycopg.connect(self.admin, autocommit=True) as c:
            for _ in range(seconds * 2):
                if not c.execute("select count(*) from kernel.change_set where status not in "
                                 "('applied', 'invalid', 'rejected', 'conflict')").fetchone()[0]:
                    return
                time.sleep(0.5)
        raise RuntimeError("change sets did not apply: is the validator running?")

    def export(self, store_url: str) -> dict:
        """encoder-substrate over the store, as the kernel's own module; waits for the validator to apply it."""
        out = subprocess.run([sys.executable, "-m", "encoder_substrate", "--store", store_url], check=True, env=self.env,
                             capture_output=True, text=True).stdout
        self.wait_applied()
        with psycopg.connect(self.admin, autocommit=True) as c:
            bad = c.execute("select count(*) from kernel.change_set where status in ('invalid', 'rejected', 'conflict')").fetchone()[0]
        summary = json.loads(out.strip().splitlines()[-1])
        summary["not_applied"] = bad
        return summary

    def agent(self, name: str) -> str:
        """An agent's own login (kk agent add), as the URL a harness's stdio MCP server connects with."""
        out = subprocess.run([sys.executable, "-m", "kk", "agent", "add", name], check=True, env=self.env,
                             capture_output=True, text=True).stdout
        made = json.loads(out.strip().splitlines()[-1])
        return swap_db(self.admin_url, self.db, made["role"], made["password"])

    def close(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        with psycopg.connect(self.admin_url, autocommit=True) as a:
            a.execute(f'drop database if exists "{self.db}" with (force)')
