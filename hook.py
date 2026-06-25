#!/usr/bin/env python3
"""Claude Code -> tray state writer. Runs on every hook; stays tiny & non-blocking.

Reads the hook JSON payload on stdin, maps the event to a status, and writes
~/.claude/statusbar/state.json atomically.

Usage: hook.py <prompt|pre|post|notify|permreq|stop>
"""
import json
import os
import sys
import time

DIR = os.path.expanduser("~/.claude/statusbar")
STATE = os.path.join(DIR, "state.json")

TOOL_LABELS = {
    "Bash": "Running command", "Edit": "Editing", "Write": "Writing",
    "MultiEdit": "Editing", "NotebookEdit": "Editing", "Read": "Reading",
    "Grep": "Searching", "Glob": "Searching", "WebFetch": "Browsing web",
    "WebSearch": "Searching web", "Task": "Delegating", "TodoWrite": "Planning",
}


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        p = json.load(sys.stdin)
    except Exception:
        p = {}

    try:
        prev = json.load(open(STATE))
    except Exception:
        prev = {}

    ts = int(time.time())
    started = prev.get("startedAt", 0)
    tool = p.get("tool_name", "")
    state, label = "idle", ""

    if event == "prompt":
        state, label, started = "thinking", "Thinking", ts
    elif event == "pre":
        state, label = "tool", TOOL_LABELS.get(tool, "Using tool")
        if not started:
            started = ts
    elif event == "post":
        state, label = "thinking", "Thinking"
        if not started:
            started = ts
    elif event == "notify":
        m = (p.get("message") or "").lower()
        if any(k in m for k in ("permission", "approve", "allow")):
            state, label = "permission", "Awaiting permission"
        else:
            state, label = "waiting", p.get("message") or "Waiting for you"
        started = 0
    elif event == "permreq":
        state, label, started = "permission", "Awaiting permission", 0
    elif event == "stop":
        state, label, started = "idle", "", 0
    else:
        return

    out = {"state": state, "label": label, "tool": tool,
           "startedAt": started, "ts": ts}
    os.makedirs(DIR, exist_ok=True)
    tmp = f"{STATE}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, STATE)


if __name__ == "__main__":
    main()
