/**
 * The mark drawn over each page the paper reader shows (IR-1128, ADR-048
 * decision 1 as amended): a faint diagonal "CIT-U" and a line naming the
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
import { useAuthStore } from "@/store/auth.store";

/** Mirrors `watermark.py`: grey 0.45 at opacity 0.18, 45 degrees, as wide as the page's short side. */
const MARK_COLOUR = "rgb(115, 115, 115)";
const MARK_OPACITY = 0.18;
const MARK_ANGLE_DEGREES = 45;
const MARK_STROKE = 0.24; // Of a letter's height
const MARK_GAP = 0.2; // Clear space between letters, of a letter's height
const ADVANCE = MARK_STROKE + MARK_GAP;

/** "CIT-U", one unit tall, y up, from the origin rightwards; and its width, strokes included. */
function citU(): { d: string; width: number } {
  const parts: string[] = [];
  let x = 0;
  // C: an open ellipse from 50 to 310 degrees
  const cx = x + 0.35;
  const at = (deg: number) => {
    const r = (deg * Math.PI) / 180;
    return `${cx + 0.35 * Math.cos(r)} ${0.5 + 0.5 * Math.sin(r)}`;
  };
  parts.push(`M ${at(50)} A 0.35 0.5 0 1 1 ${at(310)}`);
  x += 0.7 + ADVANCE;
  // I
  parts.push(`M ${x} 0 L ${x} 1`);
  x += ADVANCE;
  // T
  parts.push(`M ${x} 1 L ${x + 0.7} 1 M ${x + 0.35} 1 L ${x + 0.35} 0`);
  x += 0.7 + ADVANCE;
  // -
  parts.push(`M ${x} 0.45 L ${x + 0.4} 0.45`);
  x += 0.4 + ADVANCE;
  // U: two sides joined by a half ellipse
  parts.push(`M ${x} 1 L ${x} 0.35 A 0.35 0.35 0 0 1 ${x + 0.7} 0.35 L ${x + 0.7} 1`);
  return { d: parts.join(" "), width: x + 0.7 + MARK_STROKE };
}

const CIT_U = citU();

/** The download copy's footer is 8pt at its margin of 12pt; the reader's scales with the zoom. */
const FOOTER_SIZE_PT = 8;
const FOOTER_MARGIN_PT = 12;

export function readerWatermarkLine(user: { first_name: string; last_name: string; email: string }): string {
  const name = `${user.first_name} ${user.last_name}`.trim();
  return `Viewed by ${name ? `${name} (${user.email})` : user.email} via CIT-U IRIS`;
}

export function ReaderWatermark({ width, height, scale }: { width: number; height: number; scale: number }) {
  const user = useAuthStore((state) => state.user);
  const letter = Math.min(width, height) / CIT_U.width;

  return (
    <div
      aria-hidden
      className="absolute inset-0 overflow-hidden"
      style={{ pointerEvents: "none", userSelect: "none", WebkitUserSelect: "none" }}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="absolute inset-0">
        <path
          d={CIT_U.d}
          // To the page's centre, tilted up to the right, one letter tall, y up, centred on the word.
          transform={
            `translate(${width / 2} ${height / 2}) rotate(${-MARK_ANGLE_DEGREES}) ` +
            `scale(${letter} ${-letter}) translate(${-CIT_U.width / 2 + MARK_STROKE / 2} -0.5)`
          }
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
