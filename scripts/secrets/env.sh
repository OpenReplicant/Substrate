# The `env` secrets backend: secrets live in .env (mode 600) beside every other setting. The one backend (S-41).
# shellcheck shell=sh

sec_start() { :; }
sec_stop() { :; }
sec_get() { env_file_value "$1"; }
sec_put() {   # NAME, the value on stdin (the program is an argument, so stdin stays the value's)
  python3 -c '
import os, sys
path, name = sys.argv[1], sys.argv[2]
value = sys.stdin.read().rstrip("\n")
lines = open(path).read().splitlines() if os.path.exists(path) else []
for i, line in enumerate(lines):
    if line.partition("=")[0] == name:
        lines[i] = f"{name}={value}"
        break
else:
    lines.append(f"{name}={value}")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(path, 0o600)
' "$ENV_FILE" "$1"
}
sec_status() {
  [ -f "$ENV_FILE" ] || { echo ".env (not created yet: scripts/up.sh makes it)"; return 0; }
  echo ".env (mode $(stat -c %a "$ENV_FILE" 2>/dev/null || stat -f %Lp "$ENV_FILE" 2>/dev/null))"
}
