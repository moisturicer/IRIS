# Folio Ribbon: final assets

The approved Folio Ribbon direction (01), traced to vectors from the concept board. Open `index.html` to see every file.

**Status: adopted by IR-744.** The app draws these shapes from `frontend/src/components/brand/brandPaths.ts`, which `build.py` writes; the change is recorded in `docs/ui-ux/01-design-system.md`.

## Colours

| Name | Hex | Use |
|---|---|---|
| Binding Maroon | `#6B0F12` | the mark, wordmark and the maroon half of the icons |
| Ink | `#1C1917` | the Search handle and the Ask IRIS lines (two-tone icons only) |
| White | `#FFFFFF` | every `-reversed` file, for use on maroon |

## Files

| File | Use |
|---|---|
| `mark.svg`, `mark-reversed.svg`, `mark-ink.svg` | the mark alone: maroon, white on maroon, one-colour black |
| `lockup-horizontal.svg`, `-reversed.svg` | sidebar, page headers, the sign-in panel |
| `lockup-stacked.svg`, `-reversed.svg` | title pages and posters; the composition of the concept board |
| `wordmark.svg` | IRIS alone |
| `banner-reversed.svg` | a maroon banner with the white lockup, for slides and covers |
| `app-icon.svg` | white mark on a square maroon tile; platforms round the corners |
| `favicon.svg`, `favicon.ico` | browser tab (the `.ico` holds 16, 32 and 48 px) |
| `icon-search.svg`, `-maroon.svg`, `-reversed.svg` | Search: two-tone, all maroon, white |
| `icon-ask-iris.svg`, `-maroon.svg`, `-reversed.svg` | Ask IRIS: two-tone, all maroon, white |
| `opening.svg`, `-reversed.svg` | the mark assembling once (1.1 s): splash and sign-in |
| `loading.svg`, `-reversed.svg` | loading loop (2 s), the concept board's storyboard |
| `ask-iris-answering.svg`, `-reversed.svg` | Ask IRIS writing an answer (1.8 s loop) |
| `png/` | rasters: favicons 16/32/48, `apple-touch-icon-180`, `icon-192`, `icon-512`, the mark at 512, the lockups at 800–1200 px, the icons at 256 |

The animated SVGs carry their own CSS and run inside an `<img>` tag. Under `prefers-reduced-motion` the loops become a slow fade and the opening shows the finished mark.

## Motion

- **Opening:** the upper-left leaf unfolds from the spine (0 ms), the lower-right leaf follows (120 ms), then both ribbons unspool outward from the gutter (380 and 440 ms). The I is never drawn: it is the space the four pieces leave.
- **Loading:** one leaf, then its partner, then the ribbons close and the I appears; hold; fade; repeat.
- **Ask IRIS answering:** the brackets hold still while the three lines are written one after another, 180 ms apart.

The interactive versions (hover, replay, quarter speed) are in `../animation.html`.

## Rebuild

`build.py` composes every SVG from `source/paths.json` and needs only the standard library:

```bash
python docs/brand/folio-ribbon/final/build.py
```

`source/paths.json` was traced from the concept board by `source/trace.py` (Pillow, NumPy and the pure-Python `potracer`). Re-trace only if the artwork changes. The PNGs were rendered from the SVGs with headless Chrome at the sizes in their names.

## Known limits

- The source artwork was a raster concept board, so the shapes are traces, not hand-drawn curves. The mark and wordmark came from about 230 px of artwork and hold up well. The Search and Ask IRIS icons came from tiles of about 85 px, so their edges show slight unevenness above 128 px. A designer redrawing those two curves by hand would fix it.
- The two-tone icons put Ink beside maroon; inside the app they should normally be used as `-maroon` or `-reversed`, which keeps to one colour.
