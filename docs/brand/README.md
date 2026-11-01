# IRIS identity directions (proposals)

Four logo directions for IRIS. **Folio Ribbon (01) is the chosen direction**, adopted in the app by IR-744; the other three are kept for the record.

Open `index.html` in a browser to compare them side by side.

| Folder | Direction | Source |
|---|---|---|
| `folio-ribbon/` | 01 Folio Ribbon | concept sheet |
| `citation-arch/` | 02 Citation Arch | concept sheet |
| `index-orbit/` | 03 Index Orbit | concept sheet |
| `aperture/` | 04 Aperture | new: an iris diaphragm, the name taken literally |

Each folder contains `mark.svg`, `mark-reversed.svg`, `lockup-stacked.svg`, `lockup-horizontal.svg`, `banner-reversed.svg`, `loading.svg` (animated, and it stops under reduced motion), `icon-search.svg` and `icon-ask-iris.svg`.

Maroon `#6B0F12` is the only brand colour. Gold `#C9973A` is ornament only. The wordmark is EB Garamond 600, converted to outlines.

## Folio Ribbon final assets

The chosen direction. `folio-ribbon/final/` holds the vector set traced from the concept board: mark, lockups, wordmark, banner, app icon, favicons, Search and Ask IRIS icons, the animated opening, loading and answering SVGs, and PNG rasters. See `folio-ribbon/final/README.md`.

## Folio Ribbon animation

`folio-ribbon/animation.html` animates the original concept artwork, unchanged: the opening, the loading loop and hover, in maroon and reversed. The four maroon pieces were cut from the concept board along its own white lines (`folio-ribbon/motion/*.png`, alpha masks at 4x, coloured by CSS) and are embedded in the page, so it opens from disk with nothing else. The masks are upscaled from a 230 px bitmap, so they stay sharp to about 300 px; a vector trace is needed before production use.

## Regenerate

All the SVGs come from `generate.py`. It needs `fonttools` and the repo's `frontend/node_modules` (for the EB Garamond files):

```bash
pip install fonttools
python docs/brand/generate.py .
```

Adopting a direction means replacing the mark in the sidebar, the sign-in panel and the favicon, and recording the change in `docs/ui-ux/01-design-system.md`.
