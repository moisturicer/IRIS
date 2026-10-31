"""Build the Folio Ribbon asset set from the traced concept artwork.

The shapes in source/paths.json were traced from the approved concept board
(Folio Ribbon, direction 01) by source/trace.py. This script only composes them,
so it needs nothing beyond the standard library:

    python docs/brand/folio-ribbon/final/build.py

Every file is written next to this script. PNGs are rendered separately
(see README.md).
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = json.loads((HERE / "source" / "paths.json").read_text(encoding="utf-8"))

MAROON = "#6B0F12"
INK = "#1C1917"
WHITE = "#FFFFFF"

TL, BR = P["leaf-top-left"], P["leaf-bottom-right"]
TR, BL = P["swoop-top-right"], P["swoop-bottom-left"]
WORD = P["wordmark"]


def bbox(*paths):
    nums = [float(n) for d in paths for n in re.findall(r"-?\d+\.?\d*", d)]
    xs, ys = nums[0::2], nums[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def square(box, pad):
    x0, y0, x1, y1 = box
    s = max(x1 - x0, y1 - y0) + 2 * pad
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return cx - s / 2, cy - s / 2, s, s


def vb(v):
    return " ".join(f"{n:.2f}" for n in v)


def svg(view, body, title, extra=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb(view)}" role="img" '
        f'aria-label="{title}"{extra}><title>{title}</title>{body}</svg>\n'
    )


def mark_paths(fill, cls=False):
    def p(d, c):
        attr = f' class="{c}"' if cls else ""
        return f'<path{attr} d="{d}"/>'
    return (f'<g fill="{fill}" fill-rule="evenodd">'
            + p(TL, "tl") + p(BR, "br") + p(TR, "tr") + p(BL, "bl") + "</g>")


MARK_BOX = bbox(TL, BR, TR, BL)
MARK_VIEW = square(MARK_BOX, 6)
WORD_BOX = bbox(WORD)

# The wordmark sits under the mark exactly where it sat on the concept board:
# the mark was cut from board (180, 280); the wordmark from (176, 498.75).
WORD_IN_MARK = (-4.0, 218.75)

out = {}

# ── marks ──────────────────────────────────────────────────────────────
out["mark.svg"] = svg(MARK_VIEW, mark_paths(MAROON), "IRIS")
out["mark-reversed.svg"] = svg(MARK_VIEW, mark_paths(WHITE), "IRIS")
out["mark-ink.svg"] = svg(MARK_VIEW, mark_paths(INK), "IRIS")


def app_icon(radius_ratio):
    x, y, s, _ = MARK_VIEW
    pad = s * 0.2
    v = (x - pad, y - pad, s + 2 * pad, s + 2 * pad)
    r = v[2] * radius_ratio
    bg = f'<rect x="{v[0]:.2f}" y="{v[1]:.2f}" width="{v[2]:.2f}" height="{v[3]:.2f}" rx="{r:.2f}" fill="{MAROON}"/>'
    return svg(v, bg + mark_paths(WHITE), "IRIS")


out["app-icon.svg"] = app_icon(0.0)          # square; the platform rounds it
out["favicon.svg"] = svg(MARK_VIEW, mark_paths(MAROON), "IRIS")

# ── lockups ────────────────────────────────────────────────────────────
wx, wy = WORD_IN_MARK


def stacked(fill, bg=None):
    x0 = min(MARK_BOX[0], WORD_BOX[0] + wx)
    x1 = max(MARK_BOX[2], WORD_BOX[2] + wx)
    y0, y1 = MARK_BOX[1], WORD_BOX[3] + wy
    pad = 14
    v = (x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
    back = f'<rect x="{v[0]:.2f}" y="{v[1]:.2f}" width="{v[2]:.2f}" height="{v[3]:.2f}" fill="{bg}"/>' if bg else ""
    word = f'<path transform="translate({wx} {wy})" fill="{fill}" fill-rule="evenodd" d="{WORD}"/>'
    return svg(v, back + mark_paths(fill) + word, "IRIS")


# Horizontal: as on the concept's reversed banner, the mark stands about
# 1.85 times the height of the capitals, centred on them.
def horizontal(fill, bg=None, pad=None):
    cap_h = WORD_BOX[3] - WORD_BOX[1]
    mark_h = MARK_BOX[3] - MARK_BOX[1]
    k = cap_h * 1.85 / mark_h
    mark_w = (MARK_BOX[2] - MARK_BOX[0]) * k
    gap = cap_h * 0.55
    total_h = mark_h * k
    word_dx = mark_w + gap - WORD_BOX[0]
    word_dy = (total_h - cap_h) / 2 - WORD_BOX[1]
    width = mark_w + gap + (WORD_BOX[2] - WORD_BOX[0])
    pad = cap_h * 0.3 if pad is None else pad
    v = (-pad, -pad, width + 2 * pad, total_h + 2 * pad)
    back = f'<rect x="{v[0]:.2f}" y="{v[1]:.2f}" width="{v[2]:.2f}" height="{v[3]:.2f}" fill="{bg}"/>' if bg else ""
    m = (f'<g transform="scale({k:.5f}) translate({-MARK_BOX[0]:.2f} {-MARK_BOX[1]:.2f})">'
         + mark_paths(fill) + "</g>")
    w = f'<path transform="translate({word_dx:.2f} {word_dy:.2f})" fill="{fill}" fill-rule="evenodd" d="{WORD}"/>'
    return svg(v, back + m + w, "IRIS")


out["lockup-stacked.svg"] = stacked(MAROON)
out["lockup-stacked-reversed.svg"] = stacked(WHITE)
out["lockup-horizontal.svg"] = horizontal(MAROON)
out["lockup-horizontal-reversed.svg"] = horizontal(WHITE)
out["wordmark.svg"] = svg((WORD_BOX[0] - 4, WORD_BOX[1] - 4, WORD_BOX[2] - WORD_BOX[0] + 8, WORD_BOX[3] - WORD_BOX[1] + 8),
                          f'<path fill="{MAROON}" fill-rule="evenodd" d="{WORD}"/>', "IRIS")


def banner():
    cap_h = WORD_BOX[3] - WORD_BOX[1]
    inner = horizontal(WHITE, pad=0)
    v = [float(n) for n in re.search(r'viewBox="([^"]+)"', inner).group(1).split()]
    body = re.search(r"</title>(.*)</svg>", inner, re.S).group(1)
    padx, pady = cap_h * 2.2, cap_h * 1.1
    view = (v[0] - padx, v[1] - pady, v[2] + 2 * padx, v[3] + 2 * pady)
    bg = f'<rect x="{view[0]:.2f}" y="{view[1]:.2f}" width="{view[2]:.2f}" height="{view[3]:.2f}" rx="{cap_h * 0.35:.2f}" fill="{MAROON}"/>'
    return svg(view, bg + body, "IRIS")


out["banner-reversed.svg"] = banner()

# ── icons ──────────────────────────────────────────────────────────────
for name, label in (("search", "Search"), ("ask", "Ask IRIS")):
    m, k = P[f"{name}-maroon"], P[f"{name}-ink"]
    v = square(bbox(m, k), 3)
    fname = "icon-search" if name == "search" else "icon-ask-iris"
    two = f'<path fill="{MAROON}" fill-rule="evenodd" d="{m}"/><path fill="{INK}" fill-rule="evenodd" d="{k}"/>'
    out[f"{fname}.svg"] = svg(v, two, label)
    mono = f'<g fill="{{c}}" fill-rule="evenodd"><path d="{m}"/><path d="{k}"/></g>'
    out[f"{fname}-maroon.svg"] = svg(v, mono.replace("{c}", MAROON), label)
    out[f"{fname}-reversed.svg"] = svg(v, mono.replace("{c}", WHITE), label)

# ── motion ─────────────────────────────────────────────────────────────
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}.fade{animation:pulse 2s ease-in-out infinite!important}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}}"


def motion_mark(fill, css, title, one_shot=False):
    x0, y0, x1, y1 = MARK_BOX
    clips = (
        f'<clipPath id="ctr"><rect class="wipe-tr" x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}"/></clipPath>'
        f'<clipPath id="cbl"><rect class="wipe-bl" x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}"/></clipPath>'
    )
    body = (
        f"<style>{css}{REDUCED}</style><defs>{clips}</defs>"
        f'<g class="fade" fill="{fill}" fill-rule="evenodd">'
        f'<path class="tl" d="{TL}"/><path class="br" d="{BR}"/>'
        f'<g clip-path="url(#ctr)"><path class="tr" d="{TR}"/></g>'
        f'<g clip-path="url(#cbl)"><path class="bl" d="{BL}"/></g></g>'
    )
    return svg(MARK_VIEW, body, title)


# The spine of the folio, in mark units: the upper-right ribbon starts at
# x 77.5 and the lower-left one ends at x 144.5 (from the traced pieces).
SPINE_TR = 77.5
SPINE_BL = 144.5
x0, _, x1, _ = MARK_BOX
w = x1 - x0
origin_tr = f"{(SPINE_TR - x0) / w * 100:.1f}% 50%"
origin_bl = f"{(SPINE_BL - x0) / w * 100:.1f}% 50%"

BASE = (
    ".tl,.br,.wipe-tr,.wipe-bl{transform-box:fill-box}"
    ".tl{transform-origin:100% 50%}.br{transform-origin:0% 50%}"
    f".wipe-tr{{transform-origin:{origin_tr}}}.wipe-bl{{transform-origin:{origin_bl}}}"
)
EASE = "cubic-bezier(.16,1,.3,1)"
EASE_IO = "cubic-bezier(.65,0,.35,1)"

LOADING = BASE + (
    f".tl{{animation:ltl 2s {EASE} infinite}}.br{{animation:lbr 2s {EASE} infinite}}"
    f".wipe-tr,.wipe-bl{{animation:lw 2s {EASE} infinite}}.tr,.bl{{animation:lf 2s linear infinite}}"
    "@keyframes ltl{0%{opacity:.18;transform:scaleX(.55)}18%,82%{opacity:1;transform:none}100%{opacity:.18;transform:scaleX(.55)}}"
    "@keyframes lbr{0%,14%{opacity:.18;transform:scaleX(.55)}34%,82%{opacity:1;transform:none}100%{opacity:.18;transform:scaleX(.55)}}"
    "@keyframes lw{0%,30%{transform:scaleX(0)}54%,100%{transform:none}}"
    "@keyframes lf{0%,82%{opacity:1}100%{opacity:0}}"
)
OPENING = BASE + (
    f".tl{{animation:otl .76s {EASE} both}}.br{{animation:otl .76s {EASE} .12s both}}"
    f".wipe-tr{{animation:ow .64s {EASE_IO} .38s both}}.wipe-bl{{animation:ow .64s {EASE_IO} .44s both}}"
    "@keyframes otl{from{opacity:.15;transform:scaleX(.04) skewY(-10deg)}to{opacity:1;transform:none}}"
    "@keyframes ow{from{transform:scaleX(0)}to{transform:none}}"
)

out["loading.svg"] = motion_mark(MAROON, LOADING, "Loading")
out["loading-reversed.svg"] = motion_mark(WHITE, LOADING, "Loading")
out["opening.svg"] = motion_mark(MAROON, OPENING, "IRIS")
out["opening-reversed.svg"] = motion_mark(WHITE, OPENING, "IRIS")

# Ask IRIS answering: the brackets hold still and the three lines are
# written one after another, the same rhythm as the loading loop.
ask_m, ask_k = P["ask-maroon"], P["ask-ink"]
ask_v = square(bbox(ask_m, ask_k), 3)
lines_box = bbox(ask_k)
ly0, ly1 = lines_box[1], lines_box[3]
band = (ly1 - ly0) / 3
clips = "".join(
    f'<clipPath id="al{i}"><rect class="line l{i}" x="{lines_box[0] - 1:.2f}" y="{ly0 + i * band - 1:.2f}" '
    f'width="{lines_box[2] - lines_box[0] + 2:.2f}" height="{band + 2:.2f}"/></clipPath>'
    for i in range(3)
)
lines = "".join(f'<g clip-path="url(#al{i})"><path d="{ask_k}"/></g>' for i in range(3))
ask_css = (
    ".line{transform-box:fill-box;transform-origin:0 50%;animation:aw 1.8s cubic-bezier(.16,1,.3,1) infinite}"
    ".l1{animation-delay:.18s}.l2{animation-delay:.36s}"
    "@keyframes aw{0%{transform:scaleX(0)}35%,78%{transform:none}100%{transform:none;opacity:0}}"
)


def ask_answering(fill_m, fill_k):
    return svg(ask_v, f"<style>{ask_css}{REDUCED}</style><defs>{clips}</defs>"
                      f'<path fill="{fill_m}" fill-rule="evenodd" d="{ask_m}"/>'
                      f'<g class="fade" fill="{fill_k}" fill-rule="evenodd">{lines}</g>', "Ask IRIS is answering")


out["ask-iris-answering.svg"] = ask_answering(MAROON, INK)
out["ask-iris-answering-reversed.svg"] = ask_answering(WHITE, WHITE)

for name, text in out.items():
    (HERE / name).write_text(text, encoding="utf-8", newline="\n")
print(f"wrote {len(out)} files; mark box {tuple(round(n, 1) for n in MARK_BOX)}")


# ── frontend module ────────────────────────────────────────────────────
# The app draws the marks as inline SVG in currentColor, so it needs the
# path data, not the files. Coordinates are rounded to 0.1 unit.
def short(d):
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.1f}".rstrip("0").rstrip("."), d)


search_v = square(bbox(P["search-maroon"], P["search-ink"]), 3)
ts = f'''// Generated by docs/brand/folio-ribbon/final/build.py from the traced
// Folio Ribbon artwork (source/paths.json). Do not edit by hand: rebuild.

export const MARK_VIEWBOX = "{vb(MARK_VIEW)}";
export const MARK = {{
  leafTopLeft: "{short(TL)}",
  leafBottomRight: "{short(BR)}",
  ribbonTopRight: "{short(TR)}",
  ribbonBottomLeft: "{short(BL)}",
}} as const;

export const WORDMARK_VIEWBOX = "{vb((WORD_BOX[0], WORD_BOX[1], WORD_BOX[2] - WORD_BOX[0], WORD_BOX[3] - WORD_BOX[1]))}";
export const WORDMARK = "{short(WORD)}";

export const SEARCH_VIEWBOX = "{vb(search_v)}";
export const SEARCH = {{ lens: "{short(P["search-maroon"])}", handle: "{short(P["search-ink"])}" }} as const;

export const ASK_VIEWBOX = "{vb(ask_v)}";
export const ASK = {{ brackets: "{short(ask_m)}", lines: "{short(ask_k)}" }} as const;
'''
TS_OUT = HERE.parents[3] / "frontend" / "src" / "components" / "brand" / "brandPaths.ts"
TS_OUT.parent.mkdir(parents=True, exist_ok=True)
TS_OUT.write_text(ts, encoding="utf-8", newline="\n")
print(f"wrote {TS_OUT.relative_to(HERE.parents[3])} ({len(ts)} bytes)")
