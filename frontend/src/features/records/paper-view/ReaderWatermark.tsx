/**
 * The mark drawn over each page the paper reader shows (IR-1128, ADR-048
 * decision 1 as amended): a faint diagonal "PROPERTY OF / CIT-U / DO NOT
 * DISTRIBUTE" (IR-1198) and a line naming the
 * signed-in reader, so a screenshot or a print from the reader carries both.
 *
 * Drawn in the browser, over the page, so it costs the server nothing. It is
 * not a control: the PDF the reader fetched is still unmarked, and a reader
 * who saves it with browser tools gets a copy without the mark (ADR-048,
 * Consequences). A saved copy is marked on the server (`watermark.py`).
 *
 * Kept out of everything a reader does with the page: it takes no pointer
 * events, cannot be selected, lives outside pdf.js's text layer (so the
 * reader's find, selection and highlights see only the paper), and is hidden
 * from assistive technology, which reads the paper, not the mark.
 *
 * The letters are the download copy's (`apps/records/watermark.py`), stroked
 * lines and arcs with flat ends, so the two marks look the same.
 */
import { useId } from "react";

import { useAuthStore } from "@/store/auth.store";

/** Mirrors `watermark.py`: grey 0.45 at opacity 0.18, 45 degrees, the longest line as wide as the page's short side. */
const MARK_COLOUR = "rgb(115, 115, 115)";
const MARK_OPACITY = 0.18;
const MARK_ANGLE_DEGREES = 45;
const MARK_STROKE = 0.24; // Of a letter's height
const MARK_GAP = 0.2; // Clear space between letters, of a letter's height
const ADVANCE = MARK_STROKE + MARK_GAP;

/** The mark's words, one line each, centred on one another (IR-1198). Mirrors `watermark.py`. */
export const MARK_LINES = ["PROPERTY OF", "CIT-U", "DO NOT DISTRIBUTE"] as const;
const MARK_WORD_GAP = 0.6; // A space between words, of a letter's height
const MARK_LINE_GAP = 0.7; // Clear space between lines, of a letter's height

type Command =
  | ["M", number, number]
  | ["L", number, number]
  // Centre, radii, start and extent in degrees, counterclockwise when positive
  | ["A", number, number, number, number, number, number]
  | ["Z"];

/**
 * Each letter as strokes, one unit tall, y up, from x = 0. Mirrors `MARK_GLYPHS` in `watermark.py`.
 * A stroke that ends open at the top or the bottom runs past it (y = 1.2 or -0.2) and
 * `MARK.bands` cuts it flat at the ink's edge, which makes every letter the same height.
 */
const GLYPHS: Record<string, { width: number; strokes: Command[][] }> = {
  B: {
    width: 0.7,
    strokes: [
      [["M", 0.38, 0.5], ["L", 0, 0.5], ["L", 0, 1], ["L", 0.38, 1], ["A", 0.38, 0.75, 0.28, 0.25, 90, -180]],
      [["M", 0, 0.5], ["L", 0.4, 0.5], ["A", 0.4, 0.25, 0.3, 0.25, 90, -180], ["L", 0, 0], ["L", 0, 0.5]],
    ],
  },
  C: { width: 0.7, strokes: [[["M", 0.35 + 0.35 * 0.6427876, 0.5 + 0.5 * 0.7660444], ["A", 0.35, 0.5, 0.35, 0.5, 50, 260]]] },
  D: { width: 0.7, strokes: [[["M", 0, 0], ["L", 0, 1], ["L", 0.25, 1], ["A", 0.25, 0.5, 0.45, 0.5, 90, -180], ["Z"]]] },
  E: {
    width: 0.6,
    strokes: [
      [["M", 0.6, 1], ["L", 0, 1], ["L", 0, 0], ["L", 0.6, 0]],
      [["M", 0, 0.5], ["L", 0.5, 0.5]],
    ],
  },
  F: {
    width: 0.6,
    strokes: [
      [["M", 0.6, 1], ["L", 0, 1], ["L", 0, -0.2]],
      [["M", 0, 0.5], ["L", 0.5, 0.5]],
    ],
  },
  I: { width: 0, strokes: [[["M", 0, -0.2], ["L", 0, 1.2]]] },
  N: {
    width: 0.7,
    strokes: [
      [["M", 0, -0.2], ["L", 0, 1.2]],
      [["M", 0, 1], ["L", 0.7, 0]],
      [["M", 0.7, -0.2], ["L", 0.7, 1.2]],
    ],
  },
  O: { width: 0.7, strokes: [[["M", 0.7, 0.5], ["A", 0.35, 0.5, 0.35, 0.5, 0, 360], ["Z"]]] },
  P: { width: 0.7, strokes: [[["M", 0, -0.2], ["L", 0, 1], ["L", 0.4, 1], ["A", 0.4, 0.725, 0.3, 0.275, 90, -180], ["L", 0, 0.45]]] },
  R: {
    width: 0.7,
    strokes: [
      [["M", 0, -0.2], ["L", 0, 1], ["L", 0.4, 1], ["A", 0.4, 0.725, 0.3, 0.275, 90, -180], ["L", 0, 0.45]],
      [["M", 0.36, 0.45], ["L", 0.724, -0.2]],
    ],
  },
  S: {
    width: 0.7,
    strokes: [
      [
        ["M", 0.35 + 0.35 * 0.8660254, 0.75 + 0.25 * 0.5],
        ["A", 0.35, 0.75, 0.35, 0.25, 30, 240],
        ["A", 0.35, 0.25, 0.35, 0.25, 90, -240],
      ],
    ],
  },
  T: {
    width: 0.7,
    strokes: [
      [["M", 0, 1], ["L", 0.7, 1]],
      [["M", 0.35, 1], ["L", 0.35, -0.2]],
    ],
  },
  U: { width: 0.7, strokes: [[["M", 0, 1.2], ["L", 0, 0.35], ["A", 0.35, 0.35, 0.35, 0.35, 180, 180], ["L", 0.7, 1.2]]] },
  Y: {
    width: 0.7,
    strokes: [
      [["M", -0.025, 1.2], ["L", 0.35, 0.45], ["L", 0.725, 1.2]],
      [["M", 0.35, 0.45], ["L", 0.35, -0.2]],
    ],
  },
  "-": { width: 0.4, strokes: [[["M", 0, 0.45], ["L", 0.4, 0.45]]] },
};

/** A line's width between the outer edges of its first and last strokes. */
export function markLineWidth(text: string): number {
  let x = 0;
  for (const char of text) x += char === " " ? MARK_WORD_GAP : GLYPHS[char].width + ADVANCE;
  return x - ADVANCE + MARK_STROKE;
}

const round = (n: number) => Math.round(n * 1e5) / 1e5;

/** One stroke as SVG path data, moved by (dx, dy). An arc of a full turn is drawn as two halves. */
function strokeData(stroke: Command[], dx: number, dy: number): string {
  const out: string[] = [];
  const point = (x: number, y: number) => `${round(x + dx)} ${round(y + dy)}`;
  for (const command of stroke) {
    if (command[0] === "M" || command[0] === "L") out.push(`${command[0]} ${point(command[1], command[2])}`);
    else if (command[0] === "Z") out.push("Z");
    else {
      const [, cx, cy, rx, ry, start, extent] = command;
      const at = (deg: number) => {
        const r = (deg * Math.PI) / 180;
        return point(cx + rx * Math.cos(r), cy + ry * Math.sin(r));
      };
      out.push(`L ${at(start)}`); // As reportlab's arcTo: a line to the arc's start
      const pieces = Math.abs(extent) >= 360 ? 2 : 1;
      for (let i = 1; i <= pieces; i++) {
        const part = extent / pieces;
        out.push(`A ${rx} ${ry} 0 ${Math.abs(part) > 180 ? 1 : 0} ${part > 0 ? 1 : 0} ${at(start + part * i)}`);
      }
    }
  }
  return out.join(" ");
}

export type Band = { x: number; y: number; width: number; height: number };

/**
 * MARK_LINES, each centred on x = 0 and the block on y = 0, y up; the widest line's width; and
 * each line's ink as a band, from the outer edge of its bottom strokes to that of its top ones.
 */
export function markPath(): { d: string; width: number; bands: Band[] } {
  const block = MARK_LINES.length + (MARK_LINES.length - 1) * MARK_LINE_GAP;
  const width = Math.max(...MARK_LINES.map(markLineWidth));
  const parts: string[] = [];
  const bands: Band[] = [];
  MARK_LINES.forEach((text, row) => {
    const y = block / 2 - 1 - row * (1 + MARK_LINE_GAP);
    bands.push({ x: round(-width / 2 - 1), y: round(y - MARK_STROKE / 2), width: round(width + 2), height: 1 + MARK_STROKE });
    let x = -markLineWidth(text) / 2 + MARK_STROKE / 2;
    for (const char of text) {
      if (char === " ") {
        x += MARK_WORD_GAP;
        continue;
      }
      const glyph = GLYPHS[char];
      for (const stroke of glyph.strokes) parts.push(strokeData(stroke, x, y));
      x += glyph.width + ADVANCE;
    }
  });
  return { d: parts.join(" "), width, bands };
}

const MARK = markPath();

/** The download copy's footer is 8pt at its margin of 12pt; the reader's scales with the zoom. */
const FOOTER_SIZE_PT = 8;
const FOOTER_MARGIN_PT = 12;

export function readerWatermarkLine(user: { first_name: string; last_name: string; email: string }): string {
  const name = `${user.first_name} ${user.last_name}`.trim();
  return `Viewed by ${name ? `${name} (${user.email})` : user.email} via CIT-U IRIS`;
}

export function ReaderWatermark({ width, height, scale }: { width: number; height: number; scale: number }) {
  const user = useAuthStore((state) => state.user);
  const bandsId = `mark-bands-${useId().replace(/:/g, "")}`; // One per page, and safe inside url(#...)
  const letter = Math.min(width, height) / MARK.width;

  return (
    <div
      aria-hidden
      className="absolute inset-0 overflow-hidden"
      style={{ pointerEvents: "none", userSelect: "none", WebkitUserSelect: "none" }}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="absolute inset-0">
        <clipPath id={bandsId}>
          {MARK.bands.map((band) => (
            <rect key={band.y} {...band} />
          ))}
        </clipPath>
        <path
          d={MARK.d}
          clipPath={`url(#${bandsId})`} // In the path's own tilted units, so each line is cut flat
          // To the page's centre, tilted up to the right, y up; the path is already centred.
          transform={`translate(${width / 2} ${height / 2}) rotate(${-MARK_ANGLE_DEGREES}) scale(${letter} ${-letter})`}
          fill="none"
          stroke={MARK_COLOUR}
          strokeOpacity={MARK_OPACITY}
          strokeWidth={MARK_STROKE}
          strokeLinecap="butt"
          strokeLinejoin="miter"
        />
      </svg>
      {user && (
        <p
          className="absolute inset-x-0 text-center text-stone-700 whitespace-nowrap truncate"
          style={{ bottom: FOOTER_MARGIN_PT * scale, fontSize: FOOTER_SIZE_PT * scale }}
        >
          {readerWatermarkLine(user)}
        </p>
      )}
    </div>
  );
}
