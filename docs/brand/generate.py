"""Generate the IRIS identity-direction SVGs into docs/brand/.

Every mark is drawn on a 120x120 grid. Negative space is real transparency
(SVG masks), so a mark works on any ground; the reversed variant only swaps
the foreground colour. The wordmark and tagline are EB Garamond outlines, so
no file depends on an installed font.
"""
import math
import os
import shutil
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = sys.argv[1]
OUT = os.path.join(ROOT, "docs", "brand")
FONTS = os.path.join(ROOT, "frontend", "node_modules", "@fontsource", "eb-garamond", "files")
INTER = os.path.join(ROOT, "frontend", "node_modules", "@fontsource-variable", "inter", "files")

MAROON = "#6B0F12"
GOLD = "#C9973A"
WHITE = "#FFFFFF"
INK_QUIET = "#57534E"

G600 = TTFont(os.path.join(FONTS, "eb-garamond-latin-600-normal.woff"))
G500 = TTFont(os.path.join(FONTS, "eb-garamond-latin-500-normal.woff"))


# --------------------------------------------------------------------------- text
def text_path(font, text, size, tracking_em=0.0):
    """Return (path d at origin baseline 0, advance width) for `text`."""
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    upm = font["head"].unitsPerEm
    s = size / upm
    x = 0.0
    parts = []
    names = [cmap[ord(c)] for c in text]
    for i, name in enumerate(names):
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (s, 0, 0, -s, x, 0)))
        parts.append(pen.getCommands())
        x += hmtx[name][0] * s
        if i < len(names) - 1:
            x += tracking_em * size
    return " ".join(p for p in parts if p), x


def text_el(font, text, size, tracking, cx, baseline, fill, anchor="middle"):
    d, w = text_path(font, text, size, tracking)
    x = cx - w / 2 if anchor == "middle" else cx
    return f'<path transform="translate({x:.2f} {baseline:.2f})" fill="{fill}" d="{d}"/>', w


# --------------------------------------------------------------------------- marks
# Each builder returns (defs, body) drawn on the 120 grid. `u` keeps mask ids
# unique when several marks share one document.
def folio(fg, gold, u, anim=False):
    # a serif I standing in the gutter of an open folio; the leaves twist
    # like a ribbon (180-degree rotational symmetry) and never touch the I
    leaf_l = "M10 22 L50 41 L50 80 C37 82 22 89 10 100 Z"
    leaf_r = "M110 98 L70 79 L70 40 C83 38 98 31 110 20 Z"
    i_body = ("M46 26 H74 V36 Q65 36 65 44 V76 Q65 84 74 84 V94 H46 V84 "
              "Q55 84 55 76 V44 Q55 36 46 36 Z")
    cl = ' class="lf-l"' if anim else ""
    cr = ' class="lf-r"' if anim else ""
    ci = ' class="lf-i"' if anim else ""
    defs = f'''<mask id="fo-{u}" maskUnits="userSpaceOnUse" x="0" y="0" width="120" height="120">
  <rect width="120" height="120" fill="#fff"/>
  <path d="M8 73 C25 64 38 69 51 78" fill="none" stroke="#000" stroke-width="3.4"/>
  <path d="M112 47 C95 56 82 51 69 42" fill="none" stroke="#000" stroke-width="3.4"/>
</mask>'''
    body = f'''<g mask="url(#fo-{u})" fill="{fg}">
  <path{cl} d="{leaf_l}"/>
  <path{cr} d="{leaf_r}"/>
</g>
<path{ci} d="{i_body}" fill="{fg}"/>'''
    return defs, body


def arch(fg, gold, u, anim=False):
    left = ("M20 102 V38 Q20 16 42 16 H58 V26.2 A10 10 0 0 0 58 45.8 V49 "
            "L54 54 V102 Z")
    right = ("M100 102 V38 Q100 16 78 16 H62 V26.2 A10 10 0 0 1 62 45.8 V49 "
             "L66 54 V102 Z")
    cl = ' class="ar-l"' if anim else ""
    cr = ' class="ar-r"' if anim else ""
    cb = ' class="ar-b"' if anim else ""
    defs = f'''<mask id="ar-{u}" maskUnits="userSpaceOnUse" x="0" y="0" width="120" height="120">
  <rect width="120" height="120" fill="#fff"/>
  <rect x="29.5" y="36" width="7" height="58" rx="1" fill="#000"/>
  <rect x="83.5" y="36" width="7" height="58" rx="1" fill="#000"/>
</mask>'''
    body = f'''<g mask="url(#ar-{u})" fill="{fg}">
  <path{cl} d="{left}"/>
  <path{cr} d="{right}"/>
</g>
<g fill="{gold}"{cb}>
  <rect x="31.5" y="38" width="3" height="54" rx="1"/>
  <rect x="85.5" y="38" width="3" height="54" rx="1"/>
</g>'''
    return defs, body


def orbit(fg, gold, u, anim=False):
    cx, cy, R = 58, 64, 48
    a0, a1 = math.radians(-38), math.radians(212)
    p0 = (cx + R * math.cos(a0), cy + R * math.sin(a0))
    p1 = (cx + R * math.cos(a1), cy + R * math.sin(a1))
    dot = (cx + R * math.cos(math.radians(-62)), cy + R * math.sin(math.radians(-62)))
    arc = f"M{p0[0]:.2f} {p0[1]:.2f} A{R} {R} 0 1 1 {p1[0]:.2f} {p1[1]:.2f}"
    stem = "M52 54 Q52 51 55 51 H61 Q64 51 64 54 V104 H52 Z"
    ro = ' class="or-ring"' if anim else ""
    defs = f'''<mask id="or-{u}" maskUnits="userSpaceOnUse" x="0" y="0" width="120" height="120">
  <rect width="120" height="120" fill="#fff"/>
  <path d="{stem}" fill="#000"/>
</mask>'''
    body = f'''<circle cx="{cx}" cy="{cy}" r="34" fill="{fg}" mask="url(#or-{u})"/>
<g{ro}>
  <path d="{arc}" fill="none" stroke="{fg}" stroke-width="4.5" stroke-linecap="round"/>
  <circle cx="{dot[0]:.2f}" cy="{dot[1]:.2f}" r="7.5" fill="{gold}"/>
</g>'''
    return defs, body


def aperture_geometry(cx=60, cy=60, R=50, h=14, rot=15):
    verts = [(cx + h * math.cos(math.radians(rot + 60 * k)),
              cy + h * math.sin(math.radians(rot + 60 * k))) for k in range(6)]
    lines = []
    for k in range(6):
        vx, vy = verts[k]
        nx, ny = verts[(k + 1) % 6]
        dx, dy = nx - vx, ny - vy
        L = math.hypot(dx, dy)
        dx, dy = dx / L, dy / L
        # solve |v + t d - c| = R
        ox, oy = vx - cx, vy - cy
        b = ox * dx + oy * dy
        c = ox * ox + oy * oy - R * R
        t = -b + math.sqrt(b * b - c)
        lines.append((vx, vy, vx + t * dx, vy + t * dy))
    hexd = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in verts) + " Z"
    return hexd, lines


def aperture(fg, gold, u, anim=False, R=50, h=14, sw=3.2):
    hexd, lines = aperture_geometry(R=R + 2, h=h)
    blades = "".join(f'<line x1="{a:.2f}" y1="{b:.2f}" x2="{c:.2f}" y2="{d:.2f}"/>'
                     for a, b, c, d in lines)
    cb = ' class="ap-blades"' if anim else ""
    ch = ' class="ap-hole"' if anim else ""
    defs = f'''<mask id="ap-{u}" maskUnits="userSpaceOnUse" x="0" y="0" width="120" height="120">
  <rect width="120" height="120" fill="#fff"/>
  <g{cb} stroke="#000" stroke-width="{sw}" stroke-linecap="butt">{blades}</g>
  <path{ch} d="{hexd}" fill="#000" stroke="#000" stroke-width="1" stroke-linejoin="round"/>
</mask>'''
    body = f'''<circle cx="60" cy="60" r="{R}" fill="{fg}" mask="url(#ap-{u})"/>
<circle cx="60" cy="60" r="{h * 0.36:.2f}" fill="{gold}"/>'''
    return defs, body


MARKS = {"folio-ribbon": folio, "citation-arch": arch, "index-orbit": orbit, "aperture": aperture}


# --------------------------------------------------------------------------- loaders
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
LOAD_CSS = {
    "folio-ribbon": """
.lf-l,.lf-r{transform-box:fill-box;animation:fold 1.8s cubic-bezier(.16,1,.3,1) infinite}
.lf-l{transform-origin:100% 50%}
.lf-r{transform-origin:0 50%;animation-delay:.18s}
.lf-i{animation:ink 1.8s ease-out infinite}
@keyframes fold{0%{transform:scaleX(.08);opacity:.25}45%,80%{transform:scaleX(1);opacity:1}100%{transform:scaleX(.08);opacity:.25}}
@keyframes ink{0%,20%{opacity:0}45%,85%{opacity:1}100%{opacity:0}}""",
    "citation-arch": """
.ar-l,.ar-r{animation:close 1.8s cubic-bezier(.16,1,.3,1) infinite}
.ar-l{--x:-14px}.ar-r{--x:14px}
.ar-b{transform-box:fill-box;transform-origin:50% 100%;animation:rise 1.8s cubic-bezier(.16,1,.3,1) infinite}
@keyframes close{0%{transform:translateX(var(--x));opacity:.3}40%,80%{transform:none;opacity:1}100%{transform:translateX(var(--x));opacity:.3}}
@keyframes rise{0%,25%{transform:scaleY(0)}60%,85%{transform:scaleY(1)}100%{transform:scaleY(0)}}""",
    "index-orbit": """
.or-ring{transform-origin:58px 64px;animation:spin 1.6s cubic-bezier(.65,0,.35,1) infinite}
@keyframes spin{to{transform:rotate(360deg)}}""",
    "aperture": """
.ap-blades{transform-origin:60px 60px;animation:turn 2s cubic-bezier(.65,0,.35,1) infinite alternate}
.ap-hole{transform-origin:60px 60px;animation:dilate 2s cubic-bezier(.65,0,.35,1) infinite alternate}
@keyframes turn{from{transform:rotate(-24deg)}to{transform:rotate(18deg)}}
@keyframes dilate{from{transform:scale(.45)}to{transform:scale(1.55)}}""",
}


# --------------------------------------------------------------------------- icons
LINES = ('<g stroke="{fg}" stroke-width="7" stroke-linecap="round">'
         '<line x1="44" y1="46" x2="76" y2="46"/><line x1="44" y1="60" x2="76" y2="60"/>'
         '<line x1="44" y1="74" x2="66" y2="74"/></g>')


def search_icon(slug, fg, gold, u):
    handle = f'<line x1="74" y1="74" x2="102" y2="102" stroke="{fg}" stroke-width="13" stroke-linecap="round"/>'
    if slug == "folio-ribbon":
        lens = (f'<circle cx="50" cy="50" r="31" fill="none" stroke="{fg}" stroke-width="11"/>'
                f'<path d="M41 34 H59 V39 Q54 39 54 43 V57 Q54 61 59 61 V66 H41 V61 Q46 61 46 57 V43 '
                f'Q46 39 41 39 Z" fill="{fg}"/>')
    elif slug == "citation-arch":
        lens = (f'<circle cx="50" cy="50" r="31" fill="none" stroke="{fg}" stroke-width="11"/>'
                f'<path d="M30.6 37 A24 24 0 0 0 30.6 63" fill="none" stroke="{gold}" stroke-width="4" '
                f'stroke-linecap="round" transform="translate(-1 0)"/>'
                f'<circle cx="50" cy="38" r="5.5" fill="{fg}"/><rect x="45.5" y="47" width="9" height="19" rx="1.5" fill="{fg}"/>')
    elif slug == "index-orbit":
        a0, a1 = math.radians(-30), math.radians(250)
        p0 = (50 + 31 * math.cos(a0), 50 + 31 * math.sin(a0))
        p1 = (50 + 31 * math.cos(a1), 50 + 31 * math.sin(a1))
        d = (50 + 31 * math.cos(math.radians(-62)), 50 + 31 * math.sin(math.radians(-62)))
        lens = (f'<path d="M{p0[0]:.2f} {p0[1]:.2f} A31 31 0 1 1 {p1[0]:.2f} {p1[1]:.2f}" fill="none" '
                f'stroke="{fg}" stroke-width="11" stroke-linecap="round"/>'
                f'<circle cx="{d[0]:.2f}" cy="{d[1]:.2f}" r="7.5" fill="{gold}"/>')
    else:
        defs, body = aperture(fg, gold, u, R=36, h=10, sw=3)
        lens = f'<defs>{defs}</defs><g transform="translate(-10 -10)">{body}</g>'
        handle = f'<line x1="78" y1="78" x2="104" y2="104" stroke="{fg}" stroke-width="13" stroke-linecap="round"/>'
    return lens + handle


def ask_icon(slug, fg, gold, u):
    lines = LINES.format(fg=fg)
    if slug == "folio-ribbon":
        frame = (f'<path d="M16 20 L34 28 V92 L16 100 Z" fill="{fg}"/>'
                 f'<path d="M104 100 L86 92 V28 L104 20 Z" fill="{fg}"/>')
    elif slug == "citation-arch":
        frame = (f'<path d="M34 22 H28 Q18 22 18 32 V98 H34" fill="none" stroke="{fg}" stroke-width="9" stroke-linejoin="round"/>'
                 f'<path d="M86 22 H92 Q102 22 102 32 V98 H86" fill="none" stroke="{fg}" stroke-width="9" stroke-linejoin="round"/>'
                 f'<rect x="26" y="40" width="3" height="44" rx="1" fill="{gold}"/>'
                 f'<rect x="91" y="40" width="3" height="44" rx="1" fill="{gold}"/>')
    elif slug == "index-orbit":
        frame = (f'<path d="M34 20 A44 44 0 0 0 34 100" fill="none" stroke="{fg}" stroke-width="9" stroke-linecap="round"/>'
                 f'<path d="M86 100 A44 44 0 0 0 92 28" fill="none" stroke="{fg}" stroke-width="9" stroke-linecap="round"/>'
                 f'<circle cx="86" cy="17" r="7" fill="{gold}"/>')
    else:
        pts = [(60 + 46 * math.cos(math.radians(30 + 60 * k)), 58 + 46 * math.sin(math.radians(30 + 60 * k)))
               for k in range(6)]
        d = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z"
        a, b = pts[2], pts[1]  # lower-left vertex to bottom vertex
        e1 = (a[0] + (b[0] - a[0]) * .28, a[1] + (b[1] - a[1]) * .28)
        e2 = (a[0] + (b[0] - a[0]) * .62, a[1] + (b[1] - a[1]) * .62)
        frame = (f'<path d="{d}" fill="none" stroke="{fg}" stroke-width="8" stroke-linejoin="round"/>'
                 f'<path d="M{e1[0]:.2f} {e1[1]:.2f} L20 111 L{e2[0]:.2f} {e2[1]:.2f} Z" fill="{fg}" '
                 f'stroke="{fg}" stroke-width="5" stroke-linejoin="round"/>'
                 f'<circle cx="94" cy="24" r="6.5" fill="{gold}"/>')
    return frame + lines


# --------------------------------------------------------------------------- files
def svg(view, inner, title, extra=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img" aria-label="{title}">'
            f'<title>{title}</title>{extra}{inner}</svg>\n')


def mark_svg(slug, fg, u="m", anim=False):
    defs, body = MARKS[slug](fg, GOLD, u, anim)
    return f"<defs>{defs}</defs>{body}"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


NAMES = {"folio-ribbon": "Folio Ribbon", "citation-arch": "Citation Arch",
         "index-orbit": "Index Orbit", "aperture": "Aperture"}

for slug in MARKS:
    d = os.path.join(OUT, slug)
    nm = NAMES[slug]
    write(os.path.join(d, "mark.svg"), svg("0 0 120 120", mark_svg(slug, MAROON), f"IRIS {nm} mark"))
    write(os.path.join(d, "mark-reversed.svg"), svg("0 0 120 120", mark_svg(slug, WHITE), f"IRIS {nm} mark, reversed"))

    style = f"<style>{LOAD_CSS[slug]}{REDUCED}</style>"
    write(os.path.join(d, "loading.svg"),
          svg("0 0 120 120", mark_svg(slug, MAROON, "l", anim=True), "Loading", style))

    write(os.path.join(d, "icon-search.svg"), svg("0 0 120 120", search_icon(slug, MAROON, GOLD, "s"), "Search"))
    write(os.path.join(d, "icon-ask-iris.svg"), svg("0 0 120 120", ask_icon(slug, MAROON, GOLD, "a"), "Ask IRIS"))

    # stacked lockup
    word, ww = text_el(G600, "IRIS", 66, 0.16, 160, 222, MAROON)
    tag, _ = text_el(G500, "Research · Review · Discovery", 15, 0.22, 160, 254, INK_QUIET)
    m = f'<g transform="translate(100 12)">{mark_svg(slug, MAROON, "k")}</g>'
    write(os.path.join(d, "lockup-stacked.svg"), svg("0 0 320 270", m + word + tag, "IRIS"))

    # horizontal lockups, light and reversed banner
    for name, fg, bg in (("lockup-horizontal.svg", MAROON, None), ("banner-reversed.svg", WHITE, MAROON)):
        dpath, w = text_path(G600, "IRIS", 64, 0.16)
        mark_w, gap = 96, 30
        total = mark_w + gap + w
        x0 = (640 - total) / 2
        rect = f'<rect width="640" height="160" rx="16" fill="{bg}"/>' if bg else ""
        mk = f'<g transform="translate({x0:.2f} 32) scale(0.8)">{mark_svg(slug, fg, "h")}</g>'
        tx = f'<path transform="translate({x0 + mark_w + gap:.2f} 103)" fill="{fg}" d="{dpath}"/>'
        write(os.path.join(d, name), svg("0 0 640 160", rect + mk + tx, "IRIS"))

# fonts for the board (OFL)
fd = os.path.join(OUT, "fonts")
os.makedirs(fd, exist_ok=True)
for f in ("eb-garamond-latin-600-normal.woff2", "eb-garamond-latin-500-normal.woff2"):
    shutil.copy(os.path.join(FONTS, f), fd)
shutil.copy(os.path.join(INTER, "inter-latin-wght-normal.woff2"), fd)
print("ok", OUT)
