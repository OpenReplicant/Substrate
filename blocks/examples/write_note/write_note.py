import os
import re
from pathlib import Path


def run(inp):
    name = inp["name"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("name: letters, digits, - and _ only")
    root = Path(os.environ.get("WORKER_WORKSPACE", "/workspace")).resolve()
    p = root / "notes" / f"{name}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(inp["text"])
    return {"path": f"notes/{name}.txt"}
