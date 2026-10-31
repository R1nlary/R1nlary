#!/usr/bin/env python3
"""Build the profile README images in assets/.

Every image has a light and a dark variant; README.md switches between them
with <picture> and prefers-color-scheme. Fonts are embedded as subsets, so the
images look the same on every machine.

Fonts (OFL, Google Fonts) go into tools/fonts/ and are not committed:
  Unbounded_500Medium.ttf, Unbounded_700Bold.ttf,
  GolosText_400Regular.ttf, GolosText_500Medium.ttf,
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
        glow="#ff9d4d", city="#ffc27a", star="#ffffff", moon="#f3efe2",
        title="#eef2fb", text="#a7b3ca", muted="#7885a1",
        amber="#ffb454", blue="#82aaff",
        card="#0e1527", card_hi="#141d35", border="#222d4a",
    ),
    "light": dict(
        sky=("#c4d8f5", "#e2ebfa", "#fce5d2"),
        far="#a9badb", snow="#ffffff", mid="#8498c2", near="#5d72a0",
        glow="#ffb36b", city=None, star=None, moon=None, sun="#fff6e8",
        title="#0f1a33", text="#46536b", muted="#5f6b82",
        amber="#a65600", blue="#2b55c7",
        card="#f7f9fd", card_hi="#edf2fa", border="#d9e1ee",
    ),
}

LANG_COLORS = {"JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Dart": "#00b4ab"}


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
    "title": Face("r1-title", "Unbounded_500Medium.ttf"),
    "body": Face("r1-body", "GolosText_400Regular.ttf"),
    "medium": Face("r1-medium", "GolosText_500Medium.ttf"),
    "mono": Face("r1-mono", "JetBrainsMono-VariableFont_wght.ttf", 400),
    "monob": Face("r1-monob", "JetBrainsMono-VariableFont_wght.ttf", 700),
}

MOTION = """
.rise{animation:rise 1s cubic-bezier(.2,.7,.2,1) both}
@keyframes rise{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
.blink{animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.tw{animation:tw 3.4s ease-in-out infinite}
@keyframes tw{0%,100%{opacity:.2}50%{opacity:1}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
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
    s = Svg(W, H, "R1nlary, fullstack developer from Almaty: backend, web and mobile apps, servers")
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
        f'<radialGradient id="glow" cx=".5" cy="1" r=".5">'
        f'<stop offset="0" stop-color="{t["glow"]}" stop-opacity=".42"/>'
        f'<stop offset="1" stop-color="{t["glow"]}" stop-opacity="0"/></radialGradient>'
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
            op = rng.uniform(.35, .9)
            cls = ' class="tw"' if rng.random() < .35 else ""
            style = f' style="animation-delay:{-rng.uniform(0, 4):.2f}s;animation-duration:{rng.uniform(2.6, 5.2):.2f}s"' if cls else ""
            s.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{t["star"]}" opacity="{op:.2f}"{cls}{style}/>')
    if t["moon"]:
        mx, my = 1046, 92
        s.defs.append(
            f'<radialGradient id="moonglow"><stop offset="0" stop-color="{t["moon"]}" stop-opacity=".22"/>'
            f'<stop offset="1" stop-color="{t["moon"]}" stop-opacity="0"/></radialGradient>'
            f'<mask id="crescent"><circle cx="{mx}" cy="{my}" r="21" fill="#fff"/>'
            f'<circle cx="{mx + 9}" cy="{my - 6}" r="18" fill="#000"/></mask>'
        )
        s.add(
            f'<circle cx="{mx}" cy="{my}" r="70" fill="url(#moonglow)"/>',
            f'<circle cx="{mx}" cy="{my}" r="21" fill="{t["moon"]}" mask="url(#crescent)"/>',
        )
    if t.get("sun"):
        sx, sy = 1046, 104
        s.defs.append(
            f'<radialGradient id="sunglow"><stop offset="0" stop-color="#ffd9ab" stop-opacity=".9"/>'
            f'<stop offset="1" stop-color="#ffd9ab" stop-opacity="0"/></radialGradient>'
        )
        s.add(
            f'<circle cx="{sx}" cy="{sy}" r="120" fill="url(#sunglow)"/>',
            f'<circle cx="{sx}" cy="{sy}" r="28" fill="{t["sun"]}"/>',
        )

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
    s.add(f'<ellipse cx="520" cy="{H + 30}" rx="780" ry="140" fill="url(#glow)"/>')
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
            cls = ' class="tw"' if rng.random() < .16 else ""
            style = f' style="animation-delay:{-rng.uniform(0, 4):.2f}s"' if cls else ""
            s.add(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.choice([.7, .8, 1, 1.1, 1.3, 1.6])}" '
                f'fill="{t["city"]}" opacity="{rng.uniform(.4, .95):.2f}"{cls}{style}/>'
            )
    s.add("</g>")

    s.add('<g class="rise" style="animation-delay:.05s">')
    prompt = [("~/almaty", t["blue"]), (" $ ", t["muted"]), ("whoami", t["title"])]
    s.text(78, 108, prompt, "mono", 22)
    cursor_x = 78 + FACES["mono"].width("~/almaty $ whoami ", 22)
    s.add(f'<rect x="{cursor_x:.1f}" y="90" width="12" height="23" rx="2" fill="{t["amber"]}" class="blink"/>', "</g>")
    s.add('<g class="rise" style="animation-delay:.25s">')
    s.text(72, 222, "R1nlary", "display", 100, t["title"], tracking=-1)
    s.add("</g>", '<g class="rise" style="animation-delay:.45s">')
    s.text(80, 276, "Fullstack developer", "medium", 30, t["title"])
    s.text(80, 314, "Backend, web & mobile apps, and the servers they run on.", "body", 21, t["text"])
    s.add("</g>")
    coords_fill = t["muted"] if t["star"] else t["text"]
    s.text(W - 64, 52, "43.24°N  76.89°E", "mono", 14, coords_fill, anchor="end", tracking=2)
    return s


ICONS = {
    "code": '<path d="M8 7 3 12l5 5M16 7l5 5-5 5M13.5 4.5l-3 15"/>',
    "screens": '<rect x="2" y="4" width="14" height="12" rx="2"/><path d="M2 7.5h14"/><rect x="17.5" y="8" width="5" height="11" rx="1.4"/><path d="M7 20h5"/>',
    "link": '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l3.2-3.2a4.5 4.5 0 0 0-6.4-6.4L11.6 6"/><path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3.2 3.2a4.5 4.5 0 0 0 6.4 6.4l1.6-1.6"/>',
    "server": '<rect x="3" y="3.5" width="18" height="7" rx="2"/><rect x="3" y="13.5" width="18" height="7" rx="2"/><path d="M7 7h.01M7 17h.01M11 7h6M11 17h6"/>',
}

WHAT_I_DO = [
    ("code", "Backend & APIs", "Node.js & TypeScript (NestJS, Express), PHP & Laravel. REST APIs, queues and background jobs."),
    ("screens", "Web & Mobile", "React & Next.js admin panels and client apps. Cross-platform mobile apps in Flutter."),
    ("link", "Integrations", "CRMs (Bitrix24, amoCRM), payment providers, WhatsApp & Telegram bots, marketplace APIs."),
    ("server", "DevOps", "Linux, Docker, nginx, Ansible. Zero-downtime deploys, monitoring and incident response."),
]

DOMAINS = ["E-learning platforms", "Logistics & delivery", "CRM automation", "Booking & marketplaces", "Geo services (OSM)"]


def wrap(text, face, size, max_width):
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and FACES[face].width(candidate, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current]


def label(s, y, num, title, t):
    s.text(0, y, [(num, t["amber"])], "monob", 17)
    x = FACES["monob"].width(num, 17) + 10
    s.text(x, y, [("/", t["muted"])], "mono", 17)
    x += FACES["mono"].width("/", 17) + 12
    s.text(x, y, title.upper(), "mono", 17, t["title"], tracking=3.5)
    x += FACES["mono"].width(title.upper(), 17, 3.5) + 18
    s.add(f'<path d="M{x:.1f} {y - 6} H{W}" stroke="{t["border"]}" stroke-width="1.5"/>')


def section_label(t, num, title):
    s = Svg(W, 52, title)
    label(s, 32, num, title, t)
    return s


def pill(s, x, y, text, t, size=17, dot=True):
    face = "medium"
    pad = 18
    inner = FACES[face].width(text, size)
    w = pad * 2 + inner + (16 if dot else 0)
    s.add(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="38" rx="19" fill="{t["card"]}" stroke="{t["border"]}" stroke-width="1.5"/>')
    tx = x + pad
    if dot:
        s.add(f'<circle cx="{tx + 4:.1f}" cy="{y + 19}" r="4" fill="{t["amber"]}"/>')
        tx += 16
    s.text(tx, y + 25, text, face, size, t["text"])
    return w


def about(t):
    cw, ch, gap, top = 588, 192, 24, 66
    s = Svg(W, top + 2 * ch + gap + 128, "What I do: backend and APIs, web and mobile apps, integrations, DevOps")
    label(s, 32, "01", "What I do", t)
    for i, (icon, title, body) in enumerate(WHAT_I_DO):
        x = (i % 2) * (cw + gap)
        y = top + (i // 2) * (ch + gap)
        s.add(
            f'<g transform="translate({x},{y})">',
            f'<rect x=".75" y=".75" width="{cw - 1.5}" height="{ch - 1.5}" rx="20" fill="{t["card"]}" stroke="{t["border"]}" stroke-width="1.5"/>',
            f'<rect x="28" y="28" width="54" height="54" rx="15" fill="{t["card_hi"]}" stroke="{t["border"]}" stroke-width="1.5"/>',
            f'<g transform="translate(37 37) scale(1.5)" fill="none" stroke="{t["blue"]}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</g>',
        )
        s.text(104, 64, title, "title", 24, t["title"])
        s.text(cw - 28, 52, f"0{i + 1}", "mono", 14, t["muted"], anchor="end")
        for j, row in enumerate(wrap(body, "body", 19, cw - 56)):
            s.text(28, 124 + j * 29, row, "body", 19, t["text"])
        s.add("</g>")
    y = top + 2 * ch + gap + 44
    s.text(0, y, "SHIPPED TO PRODUCTION", "mono", 14, t["muted"], tracking=3)
    x, y = 0.0, y + 18
    for domain in DOMAINS:
        w = FACES["medium"].width(domain, 17) + 52
        if x + w > W:
            x, y = 0.0, y + 50
        x += pill(s, x, y, domain, t) + 12
    s.h = y + 40
    return s


PROJECTS = [
    ("aroma", "Aroma Lab ERP for a coffee chain: sales, inventory and finance modules.", "JavaScript", ["React", "Express", "SQLite"]),
    ("dev-test-assignment", "Backend take-home I designed for hiring: order dispatch to branches and online booking.", "TypeScript", ["Node.js 22"]),
    ("flutter-travel-tours", "Mobile app for finding and booking tours. Capstone project, milestone 1 MVP.", "Dart", ["Flutter"]),
    ("flutter-lab8-smart-catalog", "Catalog with list and grid views, pull-to-refresh and swipe-to-delete with undo.", "Dart", ["Flutter"]),
]


def project(t, name, desc, lang, tags):
    cw, ch = 600, 214
    s = Svg(cw, ch, f"{name}: {desc}")
    s.add(f'<rect x=".75" y=".75" width="{cw - 1.5}" height="{ch - 1.5}" rx="20" fill="{t["card"]}" stroke="{t["border"]}" stroke-width="1.5"/>')
    s.add(
        f'<g transform="translate(28 30)" fill="none" stroke="{t["muted"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M4 3.5h11a2 2 0 0 1 2 2v13H6a2 2 0 0 0-2 2z"/><path d="M4 20.5a2 2 0 0 1 2-2h11"/></g>'
    )
    size = 22
    while FACES["monob"].width(name, size) > cw - 130:
        size -= 1
    s.text(62, 49, name, "monob", size, t["blue"])
    s.add(
        f'<g transform="translate({cw - 50} 31)" fill="none" stroke="{t["muted"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5 15 15 5M7 5h8v8"/></g>'
    )
    for j, row in enumerate(wrap(desc, "body", 19, cw - 56)):
        s.text(28, 100 + j * 28, row, "body", 19, t["text"])
    s.add(f'<circle cx="35" cy="{ch - 38}" r="6.5" fill="{LANG_COLORS[lang]}"/>')
    s.text(50, ch - 32, lang, "medium", 16, t["muted"])
    x = cw - 28
    for tag in reversed(tags):
        w = FACES["mono"].width(tag, 14) + 24
        x -= w
        s.add(f'<rect x="{x:.1f}" y="{ch - 54}" width="{w:.1f}" height="30" rx="8" fill="{t["card_hi"]}" stroke="{t["border"]}" stroke-width="1.2"/>')
        s.text(x + w / 2, ch - 34, tag, "mono", 14, t["text"], anchor="middle")
        x -= 8
    return s


def footer(t):
    H = 120
    s = Svg(W, H, "Almaty mountains")
    s.css = MOTION
    rng = random.Random(3)
    hills = ridge(17, 96, 70, [(0, .22), (420, .32), (760, .7), (920, 1), (1200, .58)], rough=.6, base=.3)
    s.defs.append(
        f'<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{t["blue"]}" stop-opacity=".14"/>'
        f'<stop offset="1" stop-color="{t["blue"]}" stop-opacity="0"/></linearGradient>'
    )
    s.add(f'<path d="{area(hills, H - 22)}" fill="url(#fade)"/>')
    s.add(f'<path d="{line(hills)}" fill="none" stroke="{t["blue"]}" stroke-opacity=".5" stroke-width="1.5" stroke-linejoin="round"/>')
    if t["city"]:
        for _ in range(120):
            x = rng.uniform(4, W - 4)
            y = rng.uniform(at(hills, x) + 6, H - 24)
            if y > H - 24:
                continue
            cls = ' class="tw"' if rng.random() < .2 else ""
            style = f' style="animation-delay:{-rng.uniform(0, 4):.2f}s"' if cls else ""
            s.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.choice([.7, .9, 1.2])}" fill="{t["city"]}" opacity="{rng.uniform(.3, .9):.2f}"{cls}{style}/>')
    s.text(W / 2, H - 4, "R1NLARY · ALMATY, KAZAKHSTAN", "mono", 13, t["muted"], anchor="middle", tracking=3)
    return s


def main():
    OUT.mkdir(exist_ok=True)
    for theme, t in THEMES.items():
        files = {
            "header": header(t),
            "about": about(t),
            "label-stack": section_label(t, "02", "Tech stack"),
            "label-projects": section_label(t, "03", "Featured projects"),
            "label-activity": section_label(t, "04", "Contributions"),
            "footer": footer(t),
        }
        for name, desc, lang, tags in PROJECTS:
            files[f"project-{name}"] = project(t, name, desc, lang, tags)
        for name, svg in files.items():
            path = OUT / f"{name}-{theme}.svg"
            path.write_text(svg.render(), encoding="utf-8")
            print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
