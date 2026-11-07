#!/usr/bin/env python3
"""Send this project's Claude Code telemetry to substrate's OpenTelemetry collector, or stop (S-28). Edits only
the env keys it owns in .claude/settings.local.json, keeping what kk up and gateway.py wrote. Takes effect in the
next Claude Code session.

    scripts/telemetry.py on        # metrics, events and (beta) traces to 127.0.0.1:OTEL_GRPC_PORT
    scripts/telemetry.py off
    scripts/telemetry.py status

Variables from Claude Code's monitoring docs (code.claude.com/docs/en/monitoring-usage, read 2026-11-07):
CLAUDE_CODE_ENABLE_TELEMETRY turns it on; traces need CLAUDE_CODE_ENHANCED_TELEMETRY_BETA as well; Claude Code
has no default protocol, so it is set. Prompt text is not exported (OTEL_LOG_USER_PROMPTS stays unset). The
catalog names Claude Code `cycle`; its service name maps there through the annotation substrate.dev/otel-service.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNED = ("CLAUDE_CODE_ENABLE_TELEMETRY", "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA", "OTEL_METRICS_EXPORTER",
         "OTEL_LOGS_EXPORTER", "OTEL_TRACES_EXPORTER", "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_ENDPOINT",
         "OTEL_RESOURCE_ATTRIBUTES")


def port() -> str:
    path = ROOT / ".env"
    for line in (path.read_text().splitlines() if path.exists() else []):
        k, sep, v = line.partition("=")
        if sep and k.strip() == "OTEL_GRPC_PORT" and v.strip():
            return v.strip()
    return "4317"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("on", "off", "status"))
    ap.add_argument("--project", type=Path, default=ROOT, help="the project whose settings to change")
    a = ap.parse_args()
    path = a.project / ".claude/settings.local.json"
    settings = json.loads(path.read_text()) if path.exists() and path.read_text().strip() else {}
    env = settings.setdefault("env", {})

    if a.action == "status":
        if env.get("CLAUDE_CODE_ENABLE_TELEMETRY") != "1":
            print("Claude Code telemetry is off")
            sys.exit(1)
        print(f"Claude Code telemetry goes to {env.get('OTEL_EXPORTER_OTLP_ENDPOINT')}")
        return

    for k in OWNED:
        env.pop(k, None)
    if a.action == "on":
        env.update({
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{port()}",
            "OTEL_RESOURCE_ATTRIBUTES": f"substrate.project={a.project.resolve().name}",
        })
    if not env:
        settings.pop("env")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Claude Code telemetry {a.action} in {path} (from the next session"
          + ("; undo: scripts/telemetry.py off)" if a.action == "on" else ")"))


if __name__ == "__main__":
    main()
