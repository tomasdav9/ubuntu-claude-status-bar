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
# Claude Code fires NO hook when the user interrupts with ESC, so a busy state
# would otherwise hang forever. Fall back to staleness: if the state timestamp
# (refreshed by every hook) goes quiet past these thresholds, return to idle.
STALE_THINK = 20   # thinking: no tool running; cleared soon after an interrupt
STALE_TOOL = 60    # tool: no hook fires mid-tool, so allow long commands to run
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

        # A reusable fully transparent icon used to "flush" the panel slot when the
        # icon shrinks, so GNOME reclaims the vacated width instead of leaving a
        # ghost of the previous wider frame behind.
        Image.new("RGBA", (1, H), (0, 0, 0, 0)).save(
            os.path.join(RENDER_DIR, "blank.png"))

        self.counter = 0
        self.recent = []   # recently written icon files, for cleanup
        self.last_sig = None
        self.last_w = 0    # width of the last icon shown
        self.pending = None  # icon name to apply on the next tick (after a flush)
        self.shown = True  # whether the indicator is currently visible
        self.tick()
        GLib.timeout_add(TICK_MS, self.tick)

    def read_state(self):
        try:
            d = json.load(open(STATE_FILE))
            return (d.get("state", "idle"), d.get("label", ""),
                    float(d.get("startedAt", 0)), float(d.get("ts", 0)),
                    d.get("transcript", ""))
        except Exception:
            return "idle", "", 0.0, 0.0, ""

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

        # Use a unique name every time: the GNOME appindicator extension caches
        # icons by name, so reusing a name shows the stale cached pixmap (e.g. a
        # wide active frame lingering behind a narrow idle glyph). A fresh name
        # forces a clean reload and lets the panel reclaim vacated width.
        self.counter += 1
        name = f"c{self.counter}"
        path = os.path.join(RENDER_DIR, name + ".png")
        img.save(path)
        self.recent.append(path)
        while len(self.recent) > 3:
            try:
                os.remove(self.recent.pop(0))
            except OSError:
                pass
        return name, width

    def tick(self):
        # Apply an icon deferred from a flush on the previous tick.
        if self.pending:
            self.ind.set_icon_full(self.pending, "Claude")
            self.pending = None
            return True

        state, label, started, ts, _ = self.read_state()
        now = time.time()
        if state in ("thinking", "tool") and ts:
            limit = STALE_THINK if state == "thinking" else STALE_TOOL
            if now - ts > limit:
                state = "idle"

        if state not in ("thinking", "tool", "waiting", "permission"):
            # Idle: hide the indicator entirely. Drawing a static idle glyph left a
            # GNOME ghost of the previous wider frame; a hidden indicator can't.
            self.status_item.set_label("Claude: idle")
            if self.shown:
                self.ind.set_status(AppIndicator.IndicatorStatus.PASSIVE)
                self.shown = False
                self.last_sig = None
                self.last_w = 0
            return True

        if not self.shown:
            self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.shown = True

        if state in ("thinking", "tool"):
            # Advance the spinner once per second so the icon changes (and GNOME
            # crossfades) at most ~once per second instead of every tick.
            glyph = SPINNER[int(now) % len(SPINNER)]
            elapsed = fmt(now - started) if started else ""
            text = f"{label} {elapsed}".strip()
            grgb, trgb = CLAUDE_ORANGE, WHITE
            self.status_item.set_label(f"Claude: {text}")
        else:  # waiting / permission
            glyph, text, grgb, trgb = "●", label or "needs you", YELLOW, YELLOW
            self.status_item.set_label(f"Claude: {label or 'awaiting input'}")

        # Only redraw when the displayed content changes (GNOME crossfades on every
        # icon change, so needless swaps leave a faint ghost of the previous frame).
        sig = (glyph, grgb, text, trgb)
        if sig != self.last_sig:
            self.last_sig = sig
            name, w = self.render(glyph, grgb, text, trgb)
            if w < self.last_w - 6:
                # Shrinking: blank the slot this tick, apply the real icon next
                # tick, so GNOME fully reclaims the width with no leftover ghost.
                self.ind.set_icon_full("blank", "Claude")
                self.pending = name
            else:
                self.ind.set_icon_full(name, "Claude")
            self.last_w = w
        return True


if __name__ == "__main__":
    Tray()
    Gtk.main()
