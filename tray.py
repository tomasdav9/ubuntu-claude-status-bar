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
CONFIG_FILE = os.path.join(DIR, "config.json")
RENDER_DIR = os.path.join(DIR, "render")
LOG_FILE = os.path.join(DIR, "tray.log")

DEBUG = os.environ.get("CLAUDE_TRAY_DEBUG") == "1"


def log(msg):
    if not DEBUG:
        return
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.time():.3f} {msg}\n")
    except OSError:
        pass
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


def load_config():
    try:
        return json.load(open(CONFIG_FILE))
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
    except OSError:
        pass


class Tray:
    def __init__(self):
        os.makedirs(RENDER_DIR, exist_ok=True)
        self.config = load_config()
        self.show_text = self.config.get("show_text", True)

        # A reusable fully transparent icon used to "flush" the panel slot when the
        # icon shrinks, so GNOME reclaims the vacated width instead of leaving a
        # ghost of the previous wider frame behind.
        Image.new("RGBA", (1, H), (0, 0, 0, 0)).save(
            os.path.join(RENDER_DIR, "blank.png"))

        self.counter = 0
        self.recent = []   # recently written icon files, for cleanup
        self.ind_seq = 0   # bumped to give each rebuilt indicator a fresh id
        self.ind = None
        self.build_indicator()

        self.last_sig = None
        self.last_w = 0    # width of the last icon shown
        self.pending = None  # icon name to apply on the next tick (after a flush)
        self.shown = True  # whether the indicator is currently visible
        self.tick()
        GLib.timeout_add(TICK_MS, self.tick)

    def build_indicator(self):
        """Create (or recreate) the AppIndicator from scratch.

        GNOME's appindicator extension reuses the icon actor across icon swaps and
        won't reliably resize it when the icon's width changes a lot (e.g. toggling
        between the wide text frame and the narrow dot) — it leaves a ghost of the
        old frame. No redraw/PASSIVE trick clears that. Building a brand-new
        indicator with a fresh id forces the extension to drop the stale actor and
        start with a clean slot, so a mode switch never ghosts.
        """
        old = self.ind
        self.ind_seq += 1
        self.ind = AppIndicator.Indicator.new(
            f"claude-statusbar-{self.ind_seq}", "",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.ind.set_icon_theme_path(RENDER_DIR)
        self.ind.set_title("Claude")

        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="Claude: idle")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())
        text_item = Gtk.CheckMenuItem(label="Show text")
        text_item.set_active(self.show_text)
        text_item.connect("toggled", self.on_toggle_text)
        menu.append(text_item)
        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        menu.append(quit_item)
        menu.show_all()
        self.ind.set_menu(menu)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        if old is not None:
            # Retire the previous indicator so only the fresh one remains.
            old.set_status(AppIndicator.IndicatorStatus.PASSIVE)
        log(f"build_indicator id=claude-statusbar-{self.ind_seq} show_text={self.show_text}")

    def on_toggle_text(self, item):
        self.show_text = item.get_active()
        self.config["show_text"] = self.show_text
        save_config(self.config)
        # Rebuild the indicator from scratch: switching modes changes the icon
        # width drastically and GNOME leaves a ghost of the old-width actor on the
        # existing indicator. A fresh indicator has no stale actor to ghost.
        self.pending = None
        self.last_sig = None
        self.last_w = 0
        self.shown = True
        self.build_indicator()

    def read_state(self):
        try:
            d = json.load(open(STATE_FILE))
            return (d.get("state", "idle"), d.get("label", ""),
                    float(d.get("startedAt", 0)), float(d.get("ts", 0)),
                    d.get("transcript", ""))
        except Exception:
            return "idle", "", 0.0, 0.0, ""

    def render_dot(self, rgb, spin):
        """Icon-only mode: a centered disc (spin=False) or a rotating ring
        (spin=True) so the single-glyph version doesn't look like stray noise."""
        d_px = int(H * 0.5)
        m = (H - d_px) / 2
        box = (m, m, m + d_px, m + d_px)
        img = Image.new("RGBA", (H, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if spin:
            start = (time.time() * 300) % 360
            draw.arc(box, start, start + 270, fill=rgb, width=max(3, d_px // 6))
        else:
            draw.ellipse(box, fill=rgb)
        return self._save(img, H)

    def _save(self, img, width):
        # Unique name every time: GNOME caches icons by name, so reusing one shows
        # the stale pixmap. A fresh name forces a clean reload.
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

        return self._save(img, width)

    def tick(self):
        # Apply an icon deferred from a flush on the previous tick.
        if self.pending:
            log(f"pending apply icon={self.pending}")
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
            log("reactivate -> ACTIVE")

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

        # Icon-only mode: drop the drawn text (it stays in the menu) and show a
        # clean disc/ring instead of the bare glyph, which looked like stray noise.
        spin = state in ("thinking", "tool")
        if not self.show_text:
            # The ring animates, so redraw a few times a second while working; the
            # static waiting disc only redraws on a state (colour) change.
            sig = ("dot", grgb, spin, int(now * 4) if spin else 0)
        else:
            sig = (glyph, grgb, text, trgb)

        if sig != self.last_sig:
            self.last_sig = sig
            if not self.show_text:
                name, w = self.render_dot(grgb, spin)
            else:
                name, w = self.render(glyph, grgb, text, trgb)
            if w < self.last_w - 6:
                # Shrinking: blank the slot this tick, apply the real icon next
                # tick, so GNOME fully reclaims the width with no leftover ghost.
                log(f"shrink {self.last_w}->{w} blank+pending={name} show_text={self.show_text}")
                self.ind.set_icon_full("blank", "Claude")
                self.pending = name
            else:
                log(f"set icon={name} w={w} last_w={self.last_w} show_text={self.show_text}")
                self.ind.set_icon_full(name, "Claude")
            self.last_w = w
        return True


if __name__ == "__main__":
    Tray()
    Gtk.main()
