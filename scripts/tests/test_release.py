"""A release's versions agree everywhere they are written. No database, no containers: the files only.
It should:
- read the release from VERSION, a semantic version
- find the same Substrate version, and one kernel version, as the image defaults of scripts/lib.sh, .env.example and
  every ghcr.io/openreplicant image in deploy/compose.yaml (none left on `main`)
- find the images workflow publishing on v* tags, with the version as pushed and without the v
- find release notes for this version under docs/release-notes/

    python3 scripts/tests/test_release.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = []
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")


def check(name, ok, detail=""):
    checks.append(bool(ok))
    print(("ok  " if ok else "FAIL"), name, "" if ok else detail)


def main():
    version = (ROOT / "VERSION").read_text().strip()
    check("VERSION is a semantic version", SEMVER.match(version), version)

    lib = (ROOT / "scripts/lib.sh").read_text()
    sv = re.search(r"^SUBSTRATE_VERSION=(\S+)", lib, re.M)
    kv = re.search(r"^KERNEL_VERSION=(\S+)", lib, re.M)
    check("scripts/lib.sh defaults Substrate's images to VERSION", sv and sv.group(1) == version, sv and sv.group(1))
    kernel = kv.group(1) if kv else ""
    check("scripts/lib.sh pins a kernel release", SEMVER.match(kernel), kernel)

    env = (ROOT / ".env.example").read_text()
    st = re.search(r"^SUBSTRATE_IMAGE_TAG=(.*)$", env, re.M)
    kt = re.search(r"^KERNEL_IMAGE_TAG=(.*)$", env, re.M)
    check(".env.example's SUBSTRATE_IMAGE_TAG is VERSION", st and st.group(1) == version, st and st.group(1))
    check(".env.example's KERNEL_IMAGE_TAG is the kernel release", kt and kt.group(1) == kernel, kt and kt.group(1))

    compose = (ROOT / "deploy/compose.yaml").read_text()
    ours = re.findall(r"image: (ghcr\.io/openreplicant/[a-z-]+):(\S+)", compose)
    check("compose names our images", len(ours) >= 6, ours)
    wrong = [(i, t) for i, t in ours
             if t != ("${KERNEL_IMAGE_TAG:-%s}" % kernel if i.endswith("/kernel") else "${SUBSTRATE_IMAGE_TAG:-%s}" % version)]
    check("every one of them defaults to this release (the kernel's to its release)", not wrong, wrong)

    wf = (ROOT / ".github/workflows/images.yml").read_text()
    check("the images workflow runs on v* tags", re.search(r'tags: \["v\*"\]', wf), "on.push.tags")
    check("it tags the image with the git tag and with the version without the v",
          "type=ref,event=tag" in wf and "type=semver,pattern={{version}}" in wf, "metadata-action tags")

    notes = ROOT / "docs/release-notes" / f"v{version}.md"
    check(f"release notes for v{version}", notes.exists(), notes)

    print(f"{sum(checks)}/{len(checks)} checks passed")
    sys.exit(0 if all(checks) else 1)


if __name__ == "__main__":
    main()
