"""Detect controllers started before the advisory lock was introduced.

A status file alone is not proof: its phase may remain 'running' after a crash. Check the
recorded PID against the live process command and working directory before blocking work.
"""
from __future__ import annotations

import json
import os
import pathlib


def _controller_process(root, proc):
    try:
        # `uv run python scripts/tm.py eval` keeps a uv parent with the same
        # command line. Only its Python child can hold the game connection.
        if not proc.joinpath("exe").resolve(strict=True).name.startswith("python"):
            return None
        parts = proc.joinpath("cmdline").read_bytes().split(b"\0")
        args = [part.decode("utf-8", "replace") for part in parts if part]
        if proc.joinpath("cwd").resolve(strict=True) != root:
            return None
        script = root / "scripts" / "tm.py"
        for i, arg in enumerate(args[:-1]):
            if arg.endswith("tm.py") and (root / arg).resolve() == script:
                if args[i + 1] in ("train", "resume", "eval"):
                    return args[i + 1]
    except (OSError, ValueError):
        pass
    return None


def legacy_controller(root: pathlib.Path):
    root = pathlib.Path(root).resolve()
    runs = root / "runs" / "j4"
    for status in runs.glob("*/status.json"):
        try:
            data = json.loads(status.read_text(encoding="utf-8"))
            pid = data.get("pid")
            if data.get("phase") != "running" or type(pid) is not int or pid == os.getpid():
                continue
            command = _controller_process(root, pathlib.Path("/proc") / str(pid))
            if command:
                return {"pid": pid, "command": command,
                        "run": str(status.parent), "legacy": True}
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    # Old evaluations have no training status. Scan live processes as a fallback;
    # never connect to the bridge just to test if the game is occupied.
    for proc in pathlib.Path("/proc").glob("[0-9]*"):
        pid = int(proc.name)
        if pid == os.getpid():
            continue
        command = _controller_process(root, proc)
        if command:
            return {"pid": pid, "command": command, "legacy": True}
    return None
