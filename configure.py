#!/usr/bin/env python3
"""Add or remove the claude-tray hooks in ~/.claude/settings.json.

Usage: configure.py <add|remove> <hook_py_path>

Merges non-destructively: existing hooks from other tools are preserved, and our
own entries (identified by the hook.py path) are stripped before re-adding, so the
script is safe to re-run. A one-time backup is written to settings.json.bak-claude-tray.
"""
import json
import os
import shlex
import shutil
import sys

SETTINGS = os.path.expanduser("~/.claude/settings.json")

# event name in settings.json -> argument passed to hook.py (+ optional matcher)
EVENTS = [
    ("UserPromptSubmit", "prompt", None),
    ("PreToolUse", "pre", ""),
    ("PostToolUse", "post", ""),
    ("Notification", "notify", None),
    ("Stop", "stop", None),
]


def load():
    if os.path.exists(SETTINGS):
        with open(SETTINGS) as f:
            return json.load(f)
    return {}


def save(data):
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def strip_ours(hooks, evt, marker):
    out = []
    for entry in hooks.get(evt, []):
        kept = [h for h in entry.get("hooks", []) if marker not in (h.get("command") or "")]
        if kept:
            entry["hooks"] = kept
            out.append(entry)
    hooks[evt] = out


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("add", "remove"):
        sys.exit("usage: configure.py <add|remove> <hook_py_path>")
    action, hook_py = sys.argv[1], os.path.abspath(sys.argv[2])
    marker = hook_py  # our entries are the ones invoking this exact script

    data = load()
    if data and not os.path.exists(SETTINGS + ".bak-claude-tray"):
        shutil.copy(SETTINGS, SETTINGS + ".bak-claude-tray")

    hooks = data.setdefault("hooks", {})
    for evt, arg, matcher in EVENTS:
        strip_ours(hooks, evt, marker)
        if action == "add":
            entry = {"hooks": [{"type": "command",
                                "command": f"python3 {shlex.quote(hook_py)} {arg}"}]}
            if matcher is not None:
                entry["matcher"] = matcher
            hooks.setdefault(evt, []).append(entry)

    # drop now-empty event arrays we may have emptied on remove
    data["hooks"] = {k: v for k, v in hooks.items() if v}
    save(data)
    print(f"{action}: claude-tray hooks {'installed' if action == 'add' else 'removed'}")


if __name__ == "__main__":
    main()
