#!/usr/bin/env python3
"""Claude Code status tray for GNOME/Ubuntu (Ayatana AppIndicator).

GNOME's appindicator extension won't render a text label next to the icon, so we
draw the whole status (state glyph + verb + elapsed time) into the icon image
itself with Pillow and feed it to the indicator as a PNG. Animation/refresh works
by alternating the icon file name each tick (the extension caches by name).

Reads ~/.claude/statusbar/state.json (written by hook.py).
"""
import json
import os
import time

from PIL import Image, ImageDraw, ImageFont

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, GLib  # noqa: E402
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402

DIR = os.path.expanduser("~/.claude/statusbar")
STATE_FILE = os.path.join(DIR, "state.json")
RENDER_DIR = os.path.join(DIR, "render")
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

TICK_MS = 200
STALE_SEC = 900  # stale running state -> treat as idle
SPINNER = "⣾⣽⣻⢿⡿⣟⣯⣷"

H = 44                 # render height in px (panel scales it to bar height;
                       # extra vertical padding makes the text a touch smaller)
FONT_PX = 26
PAD = 3
CLAUDE_ORANGE = (227, 121, 87, 255)
YELLOW = (240, 189, 77, 255)
WHITE = (235, 235, 235, 255)
DIM = (160, 160, 160, 255)

try:
    _font = ImageFont.truetype(FONT_PATH, FONT_PX)
except OSError:
    _font = ImageFont.load_default()


def fmt(seconds):
    seconds = int(max(0, seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _w(text):
    return _font.getbbox(text)[2] if text else 0


class Tray:
    def __init__(self):
        os.makedirs(RENDER_DIR, exist_ok=True)
        self.ind = AppIndicator.Indicator.new(
            "claude-statusbar", "",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_icon_theme_path(RENDER_DIR)
        self.ind.set_title("Claude")

        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="Claude: idle")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        menu.append(quit_item)
        menu.show_all()
        self.ind.set_menu(menu)

        self.frame = 0
        self.toggle = 0
        self.last_sig = None
        self.tick()
        GLib.timeout_add(TICK_MS, self.tick)

    def read_state(self):
        try:
            d = json.load(open(STATE_FILE))
            return (d.get("state", "idle"), d.get("label", ""),
                    float(d.get("startedAt", 0)), float(d.get("ts", 0)))
        except Exception:
            return "idle", "", 0.0, 0.0

    def render(self, glyph, glyph_rgb, text, text_rgb):
        """Draw 'glyph  text' onto a transparent PNG, return its icon name."""
        gap = "  " if (glyph and text) else ""
        gw = _w(glyph)
        gapw = _w(gap)
        tw = _w(text)
        width = max(8, PAD * 2 + gw + gapw + tw)

        img = Image.new("RGBA", (width, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = PAD
        if glyph:
            d.text((x, H / 2), glyph, font=_font, fill=glyph_rgb, anchor="lm")
            x += gw + gapw
        if text:
            d.text((x, H / 2), text, font=_font, fill=text_rgb, anchor="lm")

        self.toggle ^= 1
        name = f"claude{self.toggle}"
        img.save(os.path.join(RENDER_DIR, name + ".png"))
        return name

    def tick(self):
        state, label, started, ts = self.read_state()
        now = time.time()
        if state in ("thinking", "tool") and ts and now - ts > STALE_SEC:
            state = "idle"

        if state in ("thinking", "tool"):
            self.frame = (self.frame + 1) % len(SPINNER)
            elapsed = fmt(now - started) if started else ""
            text = f"{label} {elapsed}".strip()
            glyph, grgb, trgb = SPINNER[self.frame], CLAUDE_ORANGE, WHITE
            self.status_item.set_label(f"Claude: {text}")
        elif state in ("waiting", "permission"):
            text = label or "needs you"
            glyph, grgb, trgb = "●", YELLOW, YELLOW
            self.status_item.set_label(f"Claude: {label or 'awaiting input'}")
        else:
            text = ""
            glyph, grgb, trgb = "✦", DIM, DIM
            self.status_item.set_label("Claude: idle")

        # Only redraw/swap the icon when what's shown actually changes. The GNOME
        # appindicator extension crossfades on every icon-name change, so swapping
        # each tick would leave a faint ghost of the previous frame behind.
        sig = (glyph, grgb, text, trgb)
        if sig != self.last_sig:
            self.last_sig = sig
            self.ind.set_icon_full(self.render(glyph, grgb, text, trgb), "Claude")
        return True


if __name__ == "__main__":
    Tray()
    Gtk.main()
