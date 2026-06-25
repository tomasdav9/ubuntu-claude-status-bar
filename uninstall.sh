#!/usr/bin/env bash
# Removes claude-tray: stops the tray, strips its hooks from settings.json,
# and deletes the autostart entry. Installed dependencies are left in place.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="$HOME/.claude/statusbar"
AUTOSTART="$HOME/.config/autostart/claude-tray.desktop"

echo "==> Stopping tray"
pkill -f "$DEST_DIR/tray.py" 2>/dev/null || true

echo "==> Removing hooks from settings.json"
python3 "$SRC_DIR/configure.py" remove "$DEST_DIR/hook.py"

echo "==> Removing autostart entry"
rm -f "$AUTOSTART"

echo "==> Removing scripts and state"
rm -rf "$DEST_DIR/hook.py" "$DEST_DIR/tray.py" "$DEST_DIR/render" \
       "$DEST_DIR/state.json" "$DEST_DIR/tray.log"

echo "==> Done. A settings backup remains at:"
echo "    $HOME/.claude/settings.json.bak-claude-tray"
