"""Install a pinned HashiCorp release binary, checked against its published SHA256SUMS (S-17).

    python3 scripts/install_hashicorp.py nomad 2.0.7 .state/bin
    python3 scripts/install_hashicorp.py nomad-driver-podman 0.6.5 .state/nomad/plugins

Downloads https://releases.hashicorp.com/<product>/<version>/<product>_<version>_<os>_<arch>.zip, refuses it
unless its hash matches the SHA256SUMS file next to it, and extracts the one binary into the folder.
Does nothing when that version is already there.
"""
from __future__ import annotations

import hashlib
import io
import platform
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://releases.hashicorp.com"
ARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    product, version, dest = sys.argv[1], sys.argv[2].lstrip("v"), Path(sys.argv[3])
    os_name = platform.system().lower()
    arch = ARCH.get(platform.machine().lower())
    if os_name not in ("linux", "darwin") or not arch:
        sys.exit(f"no {product} build for {platform.system()} {platform.machine()}")
    target = dest / product
    stamp = dest / f".{product}.version"
    if target.exists() and stamp.exists() and stamp.read_text().strip() == version:
        print(f"  {product} {version}: present")
        return
    name = f"{product}_{version}_{os_name}_{arch}.zip"
    sums = fetch(f"{BASE}/{product}/{version}/{product}_{version}_SHA256SUMS").decode()
    expected = next((line.split()[0] for line in sums.splitlines() if line.endswith(name)), None)
    if not expected:
        sys.exit(f"{name} is not in the published SHA256SUMS")
    blob = fetch(f"{BASE}/{product}/{version}/{name}")
    if hashlib.sha256(blob).hexdigest() != expected:
        sys.exit(f"{name}: checksum mismatch, not installed")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        target.write_bytes(z.read(product))
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    stamp.write_text(version + "\n")
    print(f"  {product} {version}: installed in {dest} (sha256 checked)")


if __name__ == "__main__":
    main()
