#!/usr/bin/env python3
"""Build the profile README header in assets/.

The header has a light and a dark variant; README.md switches between them
with <picture> and prefers-color-scheme. Fonts are embedded as subsets, so the
image looks the same on every machine.

Fonts (OFL, Google Fonts) go into tools/fonts/ and are not committed:
  Unbounded_700Bold.ttf, GolosText_500Medium.ttf,
  JetBrainsMono-VariableFont_wght.ttf

Run:  pip install fonttools && python3 tools/build.py
"""
import base64
import io
import random
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "tools" / "fonts"
OUT = ROOT / "assets"
W = 1200

THEMES = {
    "dark": dict(
        sky=("#060a16", "#0b1229", "#1b1d40"),
        far="#29355e", snow="#c9d5f0", mid="#19213f", near="#0a0f21",
        city="#ffc27a", star="#ffffff", moon="#f3efe2", sun=None,
        title="#eef2fb", muted="#7885a1", amber="#ffb454", blue="#82aaff",
    ),
    "light": dict(
        sky=("#c4d8f5", "#e2ebfa", "#fce5d2"),
        far="#a9badb", snow="#ffffff", mid="#8498c2", near="#5d72a0",
        city=None, star=None, moon=None, sun="#fff6e8",
        title="#0f1a33", muted="#5f6b82", amber="#a65600", blue="#2b55c7",
    ),
}


class Face:
    def __init__(self, family, file, wght=None):
        self.family = family
        font = TTFont(FONT_DIR / file)
        if wght is not None:
            font = instancer.instantiateVariableFont(font, {"wght": wght})
        buf = io.BytesIO()
        font.save(buf)
        self.data = buf.getvalue()
        font = TTFont(io.BytesIO(self.data))
        self.cmap = font.getBestCmap()
        self.advance = {g: m[0] for g, m in font["hmtx"].metrics.items()}
        self.upm = font["head"].unitsPerEm

    def width(self, text, size, tracking=0.0):
        units = 0
        for ch in text:
            glyph = self.cmap.get(ord(ch))
            units += self.advance[glyph] if glyph else self.upm * 0.6
        return units * size / self.upm + tracking * len(text)

    def woff(self, chars):
        font = TTFont(io.BytesIO(self.data))
        options = subset.Options()
        options.layout_features = ["kern"]
        options.hinting = False
        options.flavor = "woff"
        subsetter = subset.Subsetter(options)
        subsetter.populate(text="".join(sorted(chars)))
        subsetter.subset(font)
        buf = io.BytesIO()
        subset.save_font(font, buf, options)
        return base64.b64encode(buf.getvalue()).decode()


FACES = {
    "display": Face("r1-display", "Unbounded_700Bold.ttf"),
    "medium": Face("r1-medium", "GolosText_500Medium.ttf"),
    "mono": Face("r1-mono", "JetBrainsMono-VariableFont_wght.ttf", 400),
}

MOTION = """
.blink{animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
@media (prefers-reduced-motion:reduce){.blink{animation:none}}
"""


class Svg:
    def __init__(self, w, h, title):
        self.w, self.h, self.title = w, h, title
        self.defs, self.body = [], []
        self.css = ""
        self.chars = defaultdict(set)

    def add(self, *parts):
        self.body.extend(parts)

    def text(self, x, y, runs, face, size, fill=None, anchor="start", tracking=0, attrs=""):
        """runs: a string, or a list of (text, fill) pairs rendered as one line."""
        if isinstance(runs, str):
            runs = [(runs, fill)]
        inner = ""
        for chunk, color in runs:
            self.chars[face].update(chunk)
            inner += f'<tspan fill="{color}">{escape(chunk)}</tspan>'
        extra = f' letter-spacing="{tracking}"' if tracking else ""
        if anchor != "start":
            extra += f' text-anchor="{anchor}"'
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{face}" font-size="{size}"{extra} {attrs}>{inner}</text>')

    def render(self):
        fonts = "".join(
            f'@font-face{{font-family:"{FACES[k].family}";src:url(data:font/woff;base64,{FACES[k].woff(chars)}) format("woff")}}'
            f'.{k}{{font-family:"{FACES[k].family}",sans-serif}}'
            for k, chars in sorted(self.chars.items())
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.title)}">'
            f"<title>{escape(self.title)}</title>"
            f"<style>{fonts}text{{font-variant-ligatures:none}}{self.css}</style>"
            f'<defs>{"".join(self.defs)}</defs>{"".join(self.body)}</svg>'
        )


def interp(points, x):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def ridge(seed, ground, amp, envelope, rough=0.56, sharp=1.35, base=0.5, width=W):
    """Mountain silhouette by midpoint displacement; envelope shapes the range."""
    rng = random.Random(seed)
    n = 256
    h = [0.0] * (n + 1)
    h[0], h[n] = rng.random(), rng.random()
    step, disp = n, 1.0
    while step > 1:
        half = step // 2
        for i in range(half, n, step):
            h[i] = (h[i - half] + h[i + half]) / 2 + rng.uniform(-disp, disp)
        disp *= rough
        step = half
    lo, hi = min(h), max(h)
    pts = []
    for i, v in enumerate(h):
        x = width * i / n
        v = ((v - lo) / (hi - lo)) ** sharp
        pts.append((x, ground - interp(envelope, x) * amp * (base + (1 - base) * v)))
    return pts


def area(pts, bottom):
    d = f"M0,{bottom} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts)
    return d + f" L{pts[-1][0]:.1f},{bottom} Z"


def line(pts):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def at(pts, x):
    return interp(pts, x)


def header(t):
    H = 400
    s = Svg(W, H, "R1nlary, fullstack developer")
    s.css = MOTION
    rng = random.Random(7)
    top, mid, bottom = t["sky"]
    s.defs.append(f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="26"/></clipPath>')
    s.defs.append(
        f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset=".55" stop-color="{mid}"/>'
        f'<stop offset="1" stop-color="{bottom}"/></linearGradient>'
    )
    s.defs.append(
        f'<linearGradient id="haze" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{bottom}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{bottom}" stop-opacity=".55"/></linearGradient>'
    )
    s.add('<g clip-path="url(#frame)">', f'<rect width="{W}" height="{H}" fill="url(#sky)"/>')

    far = ridge(11, 384, 286, [(0, .05), (560, .08), (700, .15), (790, .4), (870, .76), (925, 1),
                               (975, .84), (1030, .92), (1100, .68), (1200, .56)])
    middle = ridge(23, 394, 150, [(0, .12), (520, .2), (700, .34), (860, .72), (960, .86), (1080, .6), (1200, .5)], rough=.5)
    near = ridge(5, 404, 46, [(0, .7), (400, .9), (800, .75), (1200, .9)], rough=.48, sharp=1.1)

    if t["star"]:
        for _ in range(130):
            x, y = rng.uniform(8, W - 8), rng.uniform(10, 300)
            if y > at(far, x) - 12 or (x < 760 and 70 < y < 330 and rng.random() < .65):
                continue
            r = rng.choice([.6, .7, .8, .9, 1.1, 1.4])
            s.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{t["star"]}" opacity="{rng.uniform(.35, .9):.2f}"/>')
    if t["moon"]:
        mx, my = 1046, 92
        s.defs.append(
            f'<mask id="crescent"><circle cx="{mx}" cy="{my}" r="21" fill="#fff"/>'
            f'<circle cx="{mx + 9}" cy="{my - 6}" r="18" fill="#000"/></mask>'
        )
        s.add(f'<circle cx="{mx}" cy="{my}" r="21" fill="{t["moon"]}" mask="url(#crescent)"/>')
    if t["sun"]:
        s.add(f'<circle cx="1046" cy="104" r="28" fill="{t["sun"]}"/>')

    # far range with snow above a ragged snowline
    s.defs.append(f'<clipPath id="farclip"><path d="{area(far, H)}"/></clipPath>')
    s.add(f'<path d="{area(far, H)}" fill="{t["far"]}"/>')
    snow, x, y = [], 0.0, 212.0
    while x <= W + 12:
        snow.append((x, y))
        x += rng.uniform(6, 13)
        y = min(236, max(188, y + rng.uniform(-11, 11)))
    s.add(f'<path d="M0,0 {line(snow)[1:]} L{W},0 Z" fill="{t["snow"]}" opacity=".9" clip-path="url(#farclip)"/>')
    s.add(f'<path d="{line(far)}" fill="none" stroke="{t["snow"]}" stroke-opacity=".35" stroke-width="1.2" stroke-linejoin="round"/>')
    s.add(f'<rect y="200" width="{W}" height="{H - 200}" fill="url(#haze)"/>')
    s.add(f'<path d="{area(middle, H)}" fill="{t["mid"]}"/>')
    s.add(f'<path d="{line(middle)}" fill="none" stroke="{t["snow"]}" stroke-opacity=".12" stroke-width="1" stroke-linejoin="round"/>')
    s.add(f'<path d="{area(near, H)}" fill="{t["near"]}"/>')
    if t["city"]:
        lights = [(rng.uniform(4, W - 4), None) for _ in range(70)]
        for _ in range(18):
            cx = rng.uniform(20, 860)
            lights += [(rng.gauss(cx, 24), cx) for _ in range(rng.randint(5, 16))]
        for x, cluster in lights:
            if not 3 < x < W - 3 or (cluster is None and x > 760 and rng.random() < .6):
                continue
            y = rng.uniform(at(near, x) + 7, H - 3)
            s.add(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.choice([.7, .8, 1, 1.1, 1.3, 1.6])}" '
                f'fill="{t["city"]}" opacity="{rng.uniform(.4, .95):.2f}"/>'
            )
    s.add("</g>")

    prompt = [("~", t["blue"]), (" $ ", t["muted"]), ("whoami", t["title"])]
    s.text(78, 116, prompt, "mono", 22)
    cursor_x = 78 + FACES["mono"].width("".join(chunk for chunk, _ in prompt) + " ", 22)
    s.add(f'<rect x="{cursor_x:.1f}" y="98" width="12" height="23" rx="2" fill="{t["amber"]}" class="blink"/>')
    s.text(72, 230, "R1nlary", "display", 100, t["title"], tracking=-1)
    s.text(80, 284, "Fullstack developer", "medium", 30, t["title"])
    return s


def main():
    OUT.mkdir(exist_ok=True)
    for theme, t in THEMES.items():
        path = OUT / f"header-{theme}.svg"
        path.write_text(header(t).render(), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
