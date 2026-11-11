"""Put every Section D PNG on a canvas of one width (IR-1022).

The diagrams are drawn at one font size and one dpi. Placing each on a canvas
of the same width means that, inserted at full page width, every figure prints
at the same scale: about 6.7 pt text on a 6.5-inch page. A narrow diagram keeps
white margins rather than being enlarged. Needs Pillow.

    python docs/diagrams/section-d/tools/pad_png.py
"""
import pathlib
import sys

from PIL import Image

CANVAS_WIDTH = 1500
PNG = pathlib.Path(__file__).resolve().parent.parent / "png"


def pad(path: pathlib.Path) -> str:
    with Image.open(path) as img:
        width, height = img.size
        if width == CANVAS_WIDTH:
            return "already padded"
        if width > CANVAS_WIDTH:
            sys.exit(f"{path.name} is {width} px wide, over the {CANVAS_WIDTH} px canvas: tighten its layout")
        canvas = Image.new("RGB", (CANVAS_WIDTH, height), "white")
        canvas.paste(img.convert("RGB"), ((CANVAS_WIDTH - width) // 2, 0))
    canvas.save(path, optimize=True)
    return f"{width} -> {CANVAS_WIDTH} px"


def main() -> None:
    for path in sorted(PNG.glob("*.png")):
        print(f"{path.name:45s} {pad(path)}")


if __name__ == "__main__":
    main()
