#!/usr/bin/env python3
"""Claude Code -> tray state writer. Runs on every hook; stays tiny & non-blocking.

Reads the hook JSON payload on stdin, maps the event to a status, and writes
~/.claude/statusbar/state.json atomically.

Usage: hook.py <prompt|pre|post|postfail|notify|permreq|stop|stopfail|end>

Set CLAUDE_TRAY_DEBUG=1 to append every invocation to ~/.claude/statusbar/hooks.log.
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

# events that mean "Claude is no longer busy"
DONE_EVENTS = {"stop", "stopfail", "end"}


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        p = json.load(sys.stdin)
    except Exception:
        p = {}

    if os.environ.get("CLAUDE_TRAY_DEBUG") == "1":
        try:
            os.makedirs(DIR, exist_ok=True)
            with open(os.path.join(DIR, "hooks.log"), "a") as f:
                f.write(f"{time.strftime('%H:%M:%S')} event={event} "
                        f"keys={','.join(p.keys())} "
                        f"tool={p.get('tool_name', '-')} "
                        f"reason={p.get('reason', p.get('stop_reason', '-'))}\n")
        except Exception:
            pass

    try:
        prev = json.load(open(STATE))
    except Exception:
        prev = {}

    ts = int(time.time())
    started = prev.get("startedAt", 0)
    tool = p.get("tool_name", "")
    transcript = p.get("transcript_path") or prev.get("transcript", "")
    state, label = "idle", ""

    if event == "prompt":
        state, label, started = "thinking", "Thinking", ts
    elif event == "pre":
        state, label = "tool", TOOL_LABELS.get(tool, "Using tool")
        if not started:
            started = ts
    elif event in ("post", "postfail"):
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
    elif event in DONE_EVENTS:
        state, label, started = "idle", "", 0
    else:
        return

    out = {"state": state, "label": label, "tool": tool,
           "startedAt": started, "ts": ts, "transcript": transcript}
    os.makedirs(DIR, exist_ok=True)
    tmp = f"{STATE}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(out, f)
    os.replace(tmp, STATE)


if __name__ == "__main__":
    main()
