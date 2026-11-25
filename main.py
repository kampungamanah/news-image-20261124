#!/usr/bin/env python3
"""The Daily Globe: one day's world news in one image, Tuesday 24 November 2026.

A pure-standard-library Python program. It draws a newspaper front page
summarising five stories first reported on 24 November 2026 and writes it
as a deterministic 1024x1024 PNG to $MAKEFUN_OUTPUT_DIR/entry.png
(or /output/entry.png). No network, no randomness, no clock, no fonts
from disk: text is drawn with a 5x7 block font defined below, and the PNG
bytes are encoded by hand with zlib.

Stories baked in (all first reported on Tue 24 Nov 2026):
  1. Russia / Ukraine (lead) -- Putin admits Ukraine's strikes on Russian
     oil plants have hit the budget hard; Moscow curbs fuel exports and
     pays subsidies to oil firms. A Russian strike on Zaporizhzhia kills
     two and wounds dozens, including children.
  2. NATO / Poland -- A Russian drone crosses into Polish airspace
     overnight; Warsaw calls it deliberate and renews its call for
     permanent US troops. NATO sends an AWACS radar plane east.
  3. Middle East / Iran -- Israel says Iran is developing chemical
     weapons, a game changer it will not allow; US and Israeli strike
     plans are drawn up. Trump calls toppling Tehran probably doable.
  4. Trade -- Washington readies a fresh wave of tariffs on China, the
     EU and 14 other partners over subsidised production, AP sources say.
  5. China -- Xi's purge takes down Shanghai party boss Chen Jining,
     the fourth Politburo member to fall since 2022.
Ticker: North Korea orders Switzerland to shut its Pyongyang office;
Huawei is convicted of trade-secret theft in a US court; Zelenskyy
lashes out at Washington over delayed Patriot missiles.
Sources: AP, Reuters, ISW, FT, WSJ.
"""

import binascii
import os
import struct
import sys
import zlib

W = 1024
H = 1024

# Palette: broadsheet paper, dark ink, signal red, deep blue, gold.
PAPER = (248, 244, 232)
CARD = (255, 253, 247)
INK = (26, 32, 44)
RED = (178, 44, 32)
RED_SOFT = (204, 84, 66)
BLUE = (28, 68, 128)
BLUE_LIGHT = (88, 128, 178)
GOLD = (198, 158, 42)
TEAL = (32, 96, 88)
SKY = (168, 205, 225)
SKY_DEEP = (110, 165, 200)
SEA = (36, 88, 118)
SAND = (222, 196, 148)
GREY = (96, 104, 116)
BODY = (52, 58, 70)
WHITE = (255, 255, 255)
ORANGE = (226, 118, 40)
YELLOW = (242, 194, 64)
GREEN = (72, 122, 72)


class Sheet:
    """An RGB framebuffer with flat drawing primitives."""

    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)
        self.fill(0, 0, w, h, bg)

    def _off(self, x, y):
        return (y * self.w + x) * 3

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = self._off(x, y)
            self.buf[o:o + 3] = bytes(c)

    def fill(self, x, y, w, h, c):
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.w, int(x + w))
        y1 = min(self.h, int(y + h))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(c) * (x1 - x0)
        for yy in range(y0, y1):
            o = self._off(x0, yy)
            self.buf[o:o + len(row)] = row

    def box(self, x, y, w, h, c, t=2):
        self.fill(x, y, w, t, c)
        self.fill(x, y + h - t, w, t, c)
        self.fill(x, y, t, h, c)
        self.fill(x + w - t, y, t, h, c)

    def blot(self, cx, cy, r, c):
        """A filled circle."""
        cx = int(round(cx))
        cy = int(round(cy))
        r = int(r)
        if r <= 0:
            self.px(cx, cy, c)
            return
        for dy in range(-r, r + 1):
            dx = int((r * r - dy * dy) ** 0.5)
            self.fill(cx - dx, cy + dy, 2 * dx + 1, 1, c)

    def ring(self, cx, cy, r, c, t=3):
        for k in range(t):
            rr = r - k
            if rr <= 0:
                break
            for dy in range(-rr, rr + 1):
                dx = int((rr * rr - dy * dy) ** 0.5)
                self.px(cx - dx, cy + dy, c)
                self.px(cx + dx, cy + dy, c)

    def stroke(self, x0, y0, x1, y1, c, t=2):
        """A thick line: Bresenham walk with a square brush."""
        x0 = int(round(x0))
        y0 = int(round(y0))
        x1 = int(round(x1))
        y1 = int(round(y1))
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        half = t // 2
        while True:
            self.fill(x0 - half, y0 - half, t, t, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def poly(self, pts, c):
        """Scanline fill of a simple polygon."""
        pts = [(float(x), float(y)) for x, y in pts]
        if len(pts) < 3:
            return
        y0 = max(0, int(min(p[1] for p in pts)))
        y1 = min(self.h - 1, int(max(p[1] for p in pts)) + 1)
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if (ay <= y < by) or (by <= y < ay):
                    f = (y - ay) / (by - ay)
                    xs.append(ax + f * (bx - ax))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                self.fill(int(xs[k]), y, int(xs[k + 1]) - int(xs[k]) + 1, 1, c)

    def shade(self, x, y, w, h, top, bottom):
        """A vertical gradient band."""
        for yy in range(int(y), int(y + h)):
            f = (yy - y) / max(1, h - 1)
            c = tuple(int(top[i] + (bottom[i] - top[i]) * f) for i in range(3))
            self.fill(x, yy, w, 1, c)

# ---------------------------------------------------------------------------
# PNG output: hand-written encoder, filter none, zlib level 6.
# ---------------------------------------------------------------------------

def _chunk(kind, data):
    out = struct.pack(">I", len(data)) + kind + data
    out += struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    return out


def encode_png(sheet, path):
    raw = bytearray()
    stride = sheet.w * 3
    for y in range(sheet.h):
        raw.append(0)
        raw += sheet.buf[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", sheet.w, sheet.h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ---------------------------------------------------------------------------
# Block font: each glyph is 7 rows of 5 bits (bit 4 is the leftmost pixel).
# Lowercase renders as uppercase. Written from scratch for this page.
# ---------------------------------------------------------------------------

GLYPHS = {
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C],
    ",": [0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08],
    ":": [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00],
    ";": [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x04, 0x08],
    "'": [0x04, 0x04, 0x08, 0x00, 0x00, 0x00, 0x00],
    "-": [0x00, 0x00, 0x00, 0x0E, 0x00, 0x00, 0x00],
    "(": [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
    ")": [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
    "/": [0x01, 0x01, 0x02, 0x04, 0x08, 0x10, 0x10],
    "%": [0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13],
    "!": [0x04, 0x04, 0x04, 0x04, 0x04, 0x00, 0x04],
    "?": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04],
    "+": [0x00, 0x04, 0x04, 0x1F, 0x04, 0x04, 0x00],
    "=": [0x00, 0x00, 0x1F, 0x00, 0x1F, 0x00, 0x00],
    '"': [0x0A, 0x0A, 0x0A, 0x00, 0x00, 0x00, 0x00],
    "*": [0x00, 0x04, 0x15, 0x0E, 0x15, 0x04, 0x00],
    "\u2022": [0x00, 0x04, 0x0E, 0x0E, 0x0E, 0x04, 0x00],
    "\u2014": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
}

CELL = 6  # advance per character, in font pixels (5 glyph + 1 gap)


def measure(text, s):
    """Width in pixels of text at scale s."""
    if not text:
        return 0
    return len(text) * CELL * s - s


def draw_glyph(sh, x, y, ch, s, color):
    rows = GLYPHS.get(ch.upper())
    if not rows:
        return
    for r, bits in enumerate(rows):
        for c in range(5):
            if bits & (0x10 >> c):
                sh.fill(x + c * s, y + r * s, s, s, color)


def draw_line(sh, x, y, text, s, color, align="left"):
    """Draw one line; y is the top of the 7-row glyph box."""
    w = measure(text, s)
    if align == "center":
        x = x - w // 2
    elif align == "right":
        x = x - w
    cx = int(x)
    for ch in text:
        if ch == " ":
            cx += CELL * s
        else:
            draw_glyph(sh, cx, y, ch, s, color)
            cx += CELL * s
    return cx


def wrap_text(text, s, max_w):
    """Greedy word wrap; returns lines fitting max_w pixels."""
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for wd in words:
            trial = wd if not cur else cur + " " + wd
            if measure(trial, s) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
    return lines


def draw_para(sh, x, y, text, s, color, max_w, leading=None):
    """Draw wrapped text; returns the y just below the last line."""
    if leading is None:
        leading = int(round(9.6 * s))
    for ln in wrap_text(text, s, max_w):
        draw_line(sh, x, y, ln, s, color)
        y += leading
    return y

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def card(sh, x, y, w, h, accent):
    sh.fill(x, y, w, h, CARD)
    sh.box(x, y, w, h, INK, 2)
    sh.fill(x, y, w, 5, accent)


def tag(sh, x, y, text, s=2, color=RED):
    draw_line(sh, x, y, text, s, color)
    w = measure(text, s)
    sh.fill(x, y + 7 * s + 3, w, 3, GOLD)
    return y + 7 * s + 10


def head(sh, x, y, lines, s, color=INK):
    for ln in lines:
        draw_line(sh, x, y, ln, s, color)
        y += int(round(9.2 * s))
    return y


def para(sh, x, y, text, s, max_w, color=BODY):
    return draw_para(sh, x, y, text, s, color, max_w, int(round(9.6 * s)))


# ---------------------------------------------------------------------------
# Small flat illustrations, drawn with the same primitives
# ---------------------------------------------------------------------------

def draw_refinery(sh, x, y, w, h):
    """Oil refinery: tanks, stacks, smoke and a flame. All sizes relative."""
    sh.shade(x, y, w, h, SKY, (232, 228, 210))
    gy = y + int(h * 0.62)
    sh.fill(x, gy, w, h - int(h * 0.62), SAND)
    # storage tanks
    specs = [(0.03, 0.20, 0.34), (0.28, 0.26, 0.42), (0.58, 0.18, 0.30)]
    for fx, fw, fh in specs:
        tx = x + int(w * fx)
        tw = int(w * fw)
        th = int(h * fh)
        sh.fill(tx, gy - th, tw, th, WHITE)
        sh.box(tx, gy - th, tw, th, INK, 2)
        sh.poly([(tx, gy - th), (tx + tw // 2, gy - th - int(h * 0.07)),
                 (tx + tw, gy - th)], GREY)
    # smokestacks with smoke
    for fx in (0.80, 0.90):
        sx = x + int(w * fx)
        sw = max(4, int(w * 0.035))
        sh.fill(sx, gy - int(h * 0.55), sw, int(h * 0.55), INK)
        sh.blot(sx + sw // 2, gy - int(h * 0.60), max(3, int(h * 0.06)), GREY)
        sh.blot(sx + sw + int(w * 0.02), gy - int(h * 0.68), max(3, int(h * 0.08)),
                GREY)
        sh.blot(sx - int(w * 0.01), gy - int(h * 0.72), max(3, int(h * 0.05)),
                GREY)
    # flame on the middle tank
    fx = x + int(w * 0.41)
    fy = gy - int(h * 0.42)
    fh = int(h * 0.16)
    sh.poly([(fx - fh // 2, fy), (fx, fy - fh), (fx + fh // 2, fy)], ORANGE)
    sh.poly([(fx - fh // 4, fy), (fx, fy - fh // 2), (fx + fh // 4, fy)], YELLOW)


def draw_jet(sh, x, y, w, h):
    """A fighter jet under radar arcs, over a dashed border."""
    sh.shade(x, y, w, h, SKY, (238, 240, 230))
    cx, cy = x + int(w * 0.50), y + int(h * 0.42)
    m = min(w, h)
    for fr in (0.20, 0.32, 0.44):
        sh.ring(cx, cy, int(m * fr), BLUE_LIGHT, 2)
    # jet, drawn in units of u pixels; the jet spans 128 by 60 units
    u = min(w / 140.0, h / 70.0)

    def J(dx, dy):
        return (cx + dx * u, cy + dy * u)

    sh.poly([J(-52, 0), J(58, -8), J(66, 0), J(58, 8)], INK)
    sh.poly([J(-8, -6), J(-34, -30), J(-22, -4)], INK)
    sh.poly([J(-8, 6), J(-34, 30), J(-22, 4)], INK)
    sh.poly([J(-48, -4), J(-62, -18), J(-54, 0)], INK)
    sh.blot(cx + 30 * u, cy - 3 * u, max(2, int(h * 0.035)), SKY)
    # dashed border line at the bottom
    step = max(10, int(w * 0.055))
    for dx in range(0, w - 14, step):
        sh.fill(x + 8 + dx, y + h - 12, max(6, step - 10), 4, RED)


def draw_warning(sh, x, y, w, h):
    """A warning triangle with a missile beside it."""
    cx, cy = x + int(w * 0.34), y + int(h * 0.52)
    s = min(w, h) / 100.0
    sh.poly([(cx, cy - 52 * s), (cx - 48 * s, cy + 34 * s),
             (cx + 48 * s, cy + 34 * s)], GOLD)
    sh.poly([(cx, cy - 40 * s), (cx - 37 * s, cy + 26 * s),
             (cx + 37 * s, cy + 26 * s)], INK)
    draw_line(sh, cx, cy - 24 * s, "!", max(2, int(5 * s)), GOLD)
    # missile, nose up-right
    mx, my = x + int(w * 0.72), y + int(h * 0.60)
    sh.poly([(mx, my - 34 * s), (mx + 10 * s, my - 8 * s),
             (mx + 6 * s, my + 26 * s), (mx - 6 * s, my + 26 * s),
             (mx - 10 * s, my - 8 * s)], RED)
    sh.poly([(mx - 6 * s, my + 26 * s), (mx - 20 * s, my + 38 * s),
             (mx - 6 * s, my + 30 * s)], RED)
    sh.poly([(mx + 6 * s, my + 26 * s), (mx + 20 * s, my + 38 * s),
             (mx + 6 * s, my + 30 * s)], RED)
    sh.poly([(mx - 5 * s, my + 26 * s), (mx + 5 * s, my + 26 * s),
             (mx, my + 44 * s)], ORANGE)


def draw_crates(sh, x, y, w, h):
    """Stacked cargo containers with a big percent sign."""
    s = min(w, h) / 100.0
    # containers, bottom row
    for i, fw in enumerate((0.28, 0.34, 0.26)):
        cx0 = x + int(w * (0.03 + i * 0.32))
        cw = int(w * fw)
        chh = int(h * 0.34)
        cy0 = y + h - 14 - chh
        sh.fill(cx0, cy0, cw, chh, BLUE if i != 1 else TEAL)
        sh.box(cx0, cy0, cw, chh, INK, 2)
        for rib in range(1, 5):
            sh.fill(cx0 + rib * (cw // 5), cy0, 2, chh, INK)
    # one container on top
    tx0 = x + int(w * 0.17)
    ty0 = y + h - 14 - int(h * 0.34) - int(h * 0.30)
    tw = int(w * 0.30)
    th = int(h * 0.30)
    sh.fill(tx0, ty0, tw, th, RED)
    sh.box(tx0, ty0, tw, th, INK, 2)
    for rib in range(1, 5):
        sh.fill(tx0 + rib * (tw // 5), ty0, 2, th, INK)
    # percent sign, top left
    draw_line(sh, x + 6, y + 6, "%", max(3, int(5 * s)), GOLD)


def draw_skyline(sh, x, y, w, h):
    """A city skyline with a red downward arrow."""
    sh.shade(x, y, w, h, SKY, (238, 236, 224))
    base = y + h - 10
    heights = [0.35, 0.55, 0.42, 0.70, 0.48, 0.62, 0.38]
    bw = w // 7
    for i, fh in enumerate(heights):
        bx = x + i * bw + 3
        hh = int(h * fh)
        sh.fill(bx, base - hh, bw - 6, hh, BLUE if i % 2 else INK)
        wy = base - hh + 8
        while wy < base - 6:
            sh.fill(bx + 4, wy, 4, 6, YELLOW)
            wy += 14
    # tallest tower with a spire
    tx = x + 3 * bw + 3
    mid = tx + (bw - 6) // 2
    sh.stroke(mid, base - int(h * 0.70), mid, base - int(h * 0.82), INK, 3)
    # red down arrow over the skyline
    ax = x + int(w * 0.86)
    ay = y + int(h * 0.08)
    ah = int(h * 0.30)
    hw = max(4, ah // 4)
    sh.poly([(ax - hw, ay), (ax + hw, ay), (ax, ay + ah // 2)], RED)
    sh.fill(ax - hw // 2, ay + ah // 2 - 2, hw, ah // 2, RED)

# ---------------------------------------------------------------------------
# Composition: a newspaper front page
# ---------------------------------------------------------------------------

def compose():
    sh = Sheet(W, H, PAPER)
    sh.fill(0, 0, W, 6, RED)
    draw_line(sh, W // 2, 22, "THE DAILY GLOBE", 5, INK, align="center")
    draw_line(sh, W // 2, 70, "TUESDAY, 24 NOVEMBER 2026", 3, RED,
              align="center")
    draw_line(sh, W // 2, 104, "RUSSIA \u2022 POLAND \u2022 IRAN \u2022 TRADE \u2022 CHINA",
              2, BODY, align="center")
    sh.fill(28, 128, 968, 3, INK)
    sh.fill(28, 134, 968, 1, INK)

    # ---- Lead story: Russia / Ukraine ------------------------------------
    lx, ly, lw, lh = 28, 150, 968, 290
    card(sh, lx, ly, lw, lh, RED)
    y = tag(sh, lx + 20, ly + 18, "RUSSIA \u2014 UKRAINE", s=2.2)
    y = head(sh, lx + 20, y + 6, ["PUTIN ADMITS", "OIL STRIKES HURT"], 5)
    para(sh, lx + 20, y + 8,
         "Putin admits Ukraine's oil strikes have hit the budget hard. "
         "Moscow curbs fuel exports and subsidises oil firms. A Russian "
         "strike on Zaporizhzhia kills two and wounds dozens, including "
         "children.",
         2.4, 540)
    draw_refinery(sh, lx + 612, ly + 142, 336, 132)

    # ---- Grid stories ------------------------------------------------------
    def grid(x, y, w, h, accent, tag_text, lines, body_text, art):
        card(sh, x, y, w, h, accent)
        yy = tag(sh, x + 16, y + 14, tag_text, s=2)
        yy = head(sh, x + 16, yy + 4, lines, 3.0)
        para(sh, x + 16, yy + 6, body_text, 2.1, 290)
        art(sh, x + 316, y + 12, 144, h - 24)

    grid(28, 452, 476, 227, BLUE, "NATO \u2014 POLAND",
         ["RUSSIAN DRONE", "OVER POLAND"],
         "A Russian drone crosses into Polish airspace overnight. Warsaw "
         "calls it deliberate. NATO sends an AWACS radar plane.",
         draw_jet)
    grid(520, 452, 476, 227, RED, "MIDDLE EAST \u2014 IRAN",
         ["IRAN BUILDS", "CHEMICAL ARMS"],
         "Israel says Iran is developing chemical weapons it will not "
         "allow. US and Israeli strike plans are drawn up.",
         draw_warning)
    grid(28, 691, 476, 215, TEAL, "TRADE",
         ["US READIES", "NEW TARIFFS"],
         "Washington readies new tariffs on China, the EU and 14 others "
         "over subsidised production, AP sources say.",
         draw_crates)
    grid(520, 691, 476, 215, GOLD, "CHINA",
         ["XI PURGE FELLS", "SHANGHAI BOSS"],
         "Xi's purge takes down Shanghai boss Chen Jining, the fourth "
         "Politburo member to fall since 2022.",
         draw_skyline)

    # ---- Ticker ------------------------------------------------------------
    sh.fill(28, 918, 968, 48, RED)
    draw_line(sh, 44, 926,
              "ALSO TODAY: NORTH KOREA ORDERS SWITZERLAND TO SHUT ITS PYONGYANG OFFICE",
              2.1, WHITE)
    draw_line(sh, 44, 946,
              "HUAWEI CONVICTED OF TRADE THEFT \u2022 ZELENSKYY HITS OUT OVER PATRIOTS",
              2.1, WHITE)

    # ---- Footer ------------------------------------------------------------
    draw_line(sh, W // 2, 978,
              "SUMMARY OF STORIES FIRST REPORTED ON 24 NOVEMBER 2026",
              2, INK, align="center")
    draw_line(sh, W // 2, 998, "SOURCES: AP, REUTERS, ISW, FT, WSJ",
              2, GREY, align="center")
    return sh


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    size = encode_png(compose(), path)
    print(f"wrote {path} ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
