#!/usr/bin/env bash
# claude-tray installer for Ubuntu/GNOME.
# - installs runtime dependencies (with apt, if missing)
# - copies hook.py + tray.py into ~/.claude/statusbar/
# - registers the Claude Code hooks in ~/.claude/settings.json (non-destructive)
# - installs a GNOME autostart entry and launches the tray
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="$HOME/.claude/statusbar"
AUTOSTART="$HOME/.config/autostart/claude-tray.desktop"

echo "==> claude-tray installer"

# 1. Dependencies -----------------------------------------------------------
need_apt=()
have() { python3 -c "$1" >/dev/null 2>&1; }

have "import gi" || need_apt+=(python3-gi)
have "import gi; gi.require_version('Gtk','3.0')" || need_apt+=(gir1.2-gtk-3.0)
have "import gi; gi.require_version('AyatanaAppIndicator3','0.1')" || need_apt+=(gir1.2-ayatanaappindicator3-0.1)
have "import PIL" || need_apt+=(python3-pil)

if [ "${#need_apt[@]}" -gt 0 ]; then
  echo "==> Installing missing packages: ${need_apt[*]}"
  sudo apt-get update -qq
  sudo apt-get install -y "${need_apt[@]}"
fi

# The GNOME extension that actually renders tray icons (pre-installed on Ubuntu).
if command -v gnome-extensions >/dev/null 2>&1; then
  gnome-extensions enable ubuntu-appindicators@ubuntu.com 2>/dev/null || true
fi

# 2. Copy scripts -----------------------------------------------------------
echo "==> Installing scripts to $DEST_DIR"
mkdir -p "$DEST_DIR"
cp "$SRC_DIR/hook.py" "$DEST_DIR/hook.py"
cp "$SRC_DIR/tray.py" "$DEST_DIR/tray.py"
chmod +x "$DEST_DIR/hook.py" "$DEST_DIR/tray.py"

# 3. Register hooks ---------------------------------------------------------
echo "==> Registering Claude Code hooks"
python3 "$SRC_DIR/configure.py" add "$DEST_DIR/hook.py"

# 4. Autostart --------------------------------------------------------------
echo "==> Installing autostart entry"
mkdir -p "$(dirname "$AUTOSTART")"
cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Tray
Comment=Tray indicator for Claude Code activity
Exec=python3 $HOME/.claude/statusbar/tray.py
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

# 5. (Re)launch -------------------------------------------------------------
pkill -f "$DEST_DIR/tray.py" 2>/dev/null || true
sleep 1
setsid python3 "$DEST_DIR/tray.py" >"$DEST_DIR/tray.log" 2>&1 </dev/null &

echo "==> Done. The Claude tray icon should appear in your top bar."
echo "    It activates on your next Claude Code prompt/tool use."
