import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { ChangeSide, PageRegion, VersionChange } from "@/types/records";

import { KIND_LABEL } from "./changesModel";

export type ChangesView = "inline" | "side";

export interface ShowPlace {
  version: number;
  page:    number;
  regions: PageRegion[];
}

interface Props {
  change:  VersionChange;
  from:    number;
  to:      number;
  view:    ChangesView;
  /** The section heading each side's key names, for a move's "from … to …". */
  sectionName: (side: "from" | "to", key: string) => string | null;
  onShow:  (place: ShowPlace) => void;
}

// Removed and added text are told apart by a word, a strikethrough or an
// underline, never by colour alone (12-accessibility.md); the palette is grey
// and maroon only (IR-358).
const DELETED = "line-through decoration-stone-500 text-stone-600 bg-stone-200 rounded-sm px-0.5";
const INSERTED = "no-underline border-b-2 border-brand text-stone-900 bg-brand-50 rounded-sm px-0.5";

function Deleted({ text }: { text: string }) {
  return <del className={DELETED}><span className="sr-only">Removed: </span>{text}</del>;
}

function Inserted({ text }: { text: string }) {
  return <ins className={INSERTED}><span className="sr-only">Added: </span>{text}</ins>;
}

/** A changed passage's words: both sides in one line, or one side only. */
function Words({ change, show }: { change: VersionChange; show: "both" | "from" | "to" }) {
  const words = change.words ?? [];
  return (
    <p className="leading-relaxed">
      {words.map((w, i) => {
        const gap = i > 0 ? " " : "";
        if (w.op === "equal") return <span key={i}>{gap}{w.text}</span>;
        if (w.op === "delete") return show === "to" ? null : <span key={i}>{gap}<Deleted text={w.text} /></span>;
        return show === "from" ? null : <span key={i}>{gap}<Inserted text={w.text} /></span>;
      })}
    </p>
  );
}

function sideText(change: VersionChange, side: "from" | "to") {
  const part = change[side];
  if (!part) return <p className="italic text-stone-500">Not in this Version.</p>;
  if (change.kind === "changed" && change.words) return <Words change={change} show={side} />;
  if (change.kind === "removed") return <p className="leading-relaxed"><Deleted text={part.text} /></p>;
  if (change.kind === "added") return <p className="leading-relaxed"><Inserted text={part.text} /></p>;
  return <p className="leading-relaxed">{part.text}</p>;
}

function inlineText(change: VersionChange) {
  if (change.kind === "changed" && change.words) return <Words change={change} show="both" />;
  if (change.kind === "removed" && change.from) return <p className="leading-relaxed"><Deleted text={change.from.text} /></p>;
  if (change.kind === "added" && change.to) return <p className="leading-relaxed"><Inserted text={change.to.text} /></p>;
  return <p className="leading-relaxed">{(change.to ?? change.from)?.text}</p>;
}

/** One change: what kind, the text with its differences marked, and where it is. */
export function ChangeItem({ change, from, to, view, sectionName, onShow }: Props) {
  const where = (side: "from" | "to", part: ChangeSide | null) => {
    if (!part) return null;
    const version = side === "from" ? from : to;
    return (
      <button type="button" onClick={() => onShow({ version, page: part.page, regions: part.regions })}
        className={cn("review-control text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
        Show in v{version}, p. {part.page}
      </button>
    );
  };
  const label = KIND_LABEL[change.kind];
  const page = (change.to ?? change.from)?.page;
  const moved = change.kind === "moved" && change.from && change.to
    ? `From ${sectionName("from", change.from.section) ?? "another section"} (v${from}, p. ${change.from.page}) to ${sectionName("to", change.to.section) ?? "this section"} (v${to}, p. ${change.to.page}).`
    : null;
  return (
    <article aria-label={`${label}, page ${page ?? "unknown"}`}
      className="rounded-lg border border-stone-200 bg-white p-3 text-small text-stone-800">
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <span className={cn("review-tag font-semibold",
          change.kind === "added" && "border-brand/40 text-brand",
          change.kind === "removed" && "line-through decoration-stone-500")}>
          {label}
        </span>
        {change.certainty === "tentative" && (
          <span className="review-tag border-dashed">Check against the PDF</span>
        )}
      </header>
      {change.certainty === "tentative" && (
        <p className="mb-2 text-2xs text-stone-600">
          This may be text that wasn&apos;t read, not an edit. Check it against the PDF before relying on it.
        </p>
      )}
      {moved && <p className="mb-2 text-2xs text-stone-600">{moved}</p>}
      {view === "side" && change.kind !== "moved" ? (
        <div className="grid grid-cols-2 gap-3">
          {(["from", "to"] as const).map((side) => (
            <div key={side} className="min-w-0">
              <p className="mb-1 text-2xs font-semibold uppercase tracking-wider text-stone-600">v{side === "from" ? from : to}</p>
              {sideText(change, side)}
            </div>
          ))}
        </div>
      ) : inlineText(change)}
      <footer className="mt-2 flex flex-wrap gap-x-2">
        {where("to", change.to)}
        {where("from", change.from)}
      </footer>
    </article>
  );
}
