/**
 * The 96 px outline of a page that sits beside a one-column result (IR-1082, D4;
 * spec §4.6). It replaces the abstract-preview panel, and the first-page render
 * that fed it: a drawn outline costs no request per row, so a row stays as short
 * as its text. Decoration only, so a screen reader skips it. Phones drop it, as
 * the prototype does, to give the title the width.
 */
export function PaperThumbnail() {
  return (
    <div
      aria-hidden="true"
      className="hidden aspect-[3/4] w-24 shrink-0 content-start gap-[5px] overflow-hidden rounded-control border border-stone-200 bg-surface px-2 py-2.5 shadow-card sm:grid"
    >
      <span className="mx-auto mb-0.5 h-3.5 w-3.5 rounded-full border-2 border-stone-300" />
      <i className="mx-auto mb-1.5 mt-1 block h-[5px] w-4/5 rounded-full bg-stone-300" />
      {["w-full", "w-full", "w-3/5", "w-full", "w-full", "w-3/5"].map((width, index) => (
        <i key={index} className={`block h-[3px] rounded-full bg-stone-200 ${width}`} />
      ))}
    </div>
  );
}
