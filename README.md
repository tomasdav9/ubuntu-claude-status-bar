# claude-tray

A GNOME system tray indicator for [Claude Code](https://claude.ai/code) on Ubuntu — shows live activity in the top bar so you always know what Claude is doing.

Inspired by [claude-status-bar](https://github.com/m1ckc3s/claude-status-bar) for macOS, reimplemented for Linux/GNOME in Python.

> **Unofficial community project.** Not affiliated with or endorsed by Anthropic.

---

## What it shows

| State | Appearance |
|---|---|
| Claude is working | Orange spinner + verb + elapsed timer (e.g. `⣾ Editing 0:12`) |
| Awaiting your input or permission | Yellow dot + label (e.g. `● Waiting for you`) |
| Idle | Dim glyph `✦` |

Verbs shown while working: Thinking, Editing, Writing, Reading, Running command, Searching, Browsing web, Planning, Delegating, and more.

Right-click the tray icon for a menu. **Show text** toggles between the full label and an icon-only mode (just the spinner/dot, no verb or timer). The choice is saved to `~/.claude/statusbar/config.json`.

## Requirements

- Ubuntu with GNOME (22.04 or later recommended)
- The **ubuntu-appindicators** GNOME extension (pre-installed on Ubuntu)
- Python 3
- [Claude Code](https://claude.ai/code) installed and in `$PATH`

## Install

```bash
git clone https://github.com/tomasdav9/ubuntu-claude-status-bar.git
cd ubuntu-claude-status-bar
./install.sh
```

`install.sh` does the following (non-destructively, safe to re-run):

1. Installs missing apt packages: `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-ayatanaappindicator3-0.1`, `python3-pil` (only those that are missing, requires sudo).
2. Enables the `ubuntu-appindicators` GNOME extension if available.
3. Copies `hook.py` and `tray.py` to `~/.claude/statusbar/`.
4. Registers Claude Code hooks in `~/.claude/settings.json`, first writing a one-time backup to `~/.claude/settings.json.bak-claude-tray`. Existing hooks from other tools are preserved.
5. Adds a GNOME autostart entry so the tray starts on login.
6. Launches the tray immediately.

The tray icon will appear in your top bar. It activates on your next Claude Code prompt or tool use.

## Uninstall

```bash
./uninstall.sh
```

Stops the tray, removes the hooks from `~/.claude/settings.json`, removes the autostart entry, and deletes the installed scripts and state files. The `settings.json` backup is left in place. Installed apt packages are not removed.

## How it works

Claude Code supports lifecycle hooks that run external commands at key moments. `install.sh` registers hooks for `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Notification`, `Stop`, `StopFailure`, and `SessionEnd`. Each calls `hook.py`, which maps the event and tool name to a status label and writes it atomically to `~/.claude/statusbar/state.json`.

`tray.py` polls that file every 200 ms and re-renders the tray icon only when the displayed status changes. Because GNOME's AppIndicator extension caches icons by name and ignores text labels set via the API, the status text is drawn directly into a PNG with Pillow and passed as the icon image. A unique icon filename is used on each change to force a clean refresh (reusing a name shows GNOME's cached pixmap).

Claude Code does **not** fire any hook when you interrupt it with `ESC`, so the tray also uses a liveness fallback: while busy it watches the session transcript's modification time (Claude streams into it as it writes). If activity goes quiet — about 12 s while thinking, 60 s during a tool — the indicator returns to idle on its own.

## Troubleshooting

**Icon does not appear in the top bar**

- Make sure the `ubuntu-appindicators` extension is enabled:
  ```bash
  gnome-extensions enable ubuntu-appindicators@ubuntu.com
  ```
  You can also check it in the GNOME Extensions app.
- On X11: press `Alt+F2`, type `r`, press Enter to restart the GNOME shell.
- On Wayland: log out and log back in.

**Checking logs**

```bash
cat ~/.claude/statusbar/tray.log
```

**Status is stale / stuck**

If a busy state ever hangs (e.g. you interrupted Claude with `ESC`), the tray clears it automatically once activity goes quiet — roughly 12 s after a thinking state and 60 s during a tool. You can tune `STALE_THINK` / `STALE_TOOL` at the top of `tray.py`.

**Restarting the tray manually**

```bash
pkill -f ~/.claude/statusbar/tray.py
python3 ~/.claude/statusbar/tray.py &
```

## Credits

Inspired by [m1ckc3s/claude-status-bar](https://github.com/m1ckc3s/claude-status-bar) — the macOS menu bar equivalent.

## Trademark / not affiliated

This is an unofficial, open-source side project. It is not affiliated with, endorsed by, or sponsored by Anthropic. "Claude" and the Claude spark logo are trademarks of Anthropic, used here nominatively. This project is MIT licensed, but that covers the source code only and conveys no rights to Anthropic's trademarks or brand.

If I'm violating or impeding your trademark, DM me on X ([@tomm_david](https://x.com/tomm_david)) and I'll rename this repo. This is a free side project; I'm not monetizing it.

## License

MIT
