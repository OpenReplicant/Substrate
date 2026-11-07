"""Settings for substrate's Python scripts: .env, with the secrets read through the secrets slot (S-31).

    from settings import read
    env = read()          # every setting; secrets from OpenBao when SECRETS=openbao
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    path = ROOT / ".env"
    for line in (path.read_text().splitlines() if path.exists() else []):
        k, sep, v = line.partition("=")
        if sep and not k.lstrip().startswith("#"):
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def secret_names() -> list[str]:
    return re.findall(r"^([A-Z][A-Z0-9_]*)\s", (ROOT / "deploy/secrets.txt").read_text(), re.M)


def read() -> dict[str, str]:
    env = env_file()
    if env.get("SECRETS", "env") not in ("", "env"):
        for name in secret_names():
            if os.environ.get(name):
                env[name] = os.environ[name]
                continue
            env[name] = subprocess.run([str(ROOT / "scripts/secrets.sh"), "get", name], capture_output=True,
                                       text=True, check=True).stdout
    return env
