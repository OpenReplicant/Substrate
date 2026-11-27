"""Copy PM-1a's harness without the Claude Code driver, for a Kaggle job (MetaSoar's trials/kaggle/job.py clones MetaSoar
at one pushed commit, so the harness goes into MetaSoar as a copy). The subscription login stays on this machine: the copy has
no claude_driver.py. Writes SOURCE with Substrate's commit.

    python3 -I scripts/trials/manager/export_eval.py /path/to/MetaSoar/trials/manager-eval/pm1a
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["stub_pm.py", "drivers.py", "score.py", "replay.py", "manager.md", "scenarios.json", "portfolio_fixture.json"]

dest = sys.argv[1]
os.makedirs(dest, exist_ok=True)
for f in FILES:
    shutil.copy2(os.path.join(HERE, f), dest)
sha = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
dirty = subprocess.run(["git", "-C", HERE, "status", "--porcelain", "--", HERE], capture_output=True, text=True).stdout.strip()
with open(os.path.join(dest, "SOURCE"), "w") as f:
    f.write(f"copied from OpenReplicant/Substrate scripts/trials/manager at {sha}{' (+ uncommitted changes)' if dirty else ''}\n"
            "without claude_driver.py: the Claude Code driver never runs on Kaggle.\n")
print("copied", len(FILES), "files to", dest)
