import type { RemovalLeaving, RemovalUnresolved } from "@/types/records";

/** Who is being taken off: an Adviser stops reading the review, office staff stop acting on it. */
export type RemovalRole = "adviser" | "office";

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * What a person leaves when taken off a paper (IR-1226, ADR-032 §10), one
 * sentence each, from the server's counts: the screen never counts. Their
 * drafts are discarded; their threads and requests stay open.
 */
export function removalLines(unresolved: RemovalUnresolved, role: RemovalRole): string[] {
  const lines: string[] = [];
  if (unresolved.drafts > 0) {
    lines.push(`${count(unresolved.drafts, "unsent draft", "unsent drafts")} will be discarded.`);
  }
  if (unresolved.open_threads > 0) {
    lines.push(
      `${count(unresolved.open_threads, "open thread", "open threads")} they posted ${unresolved.open_threads === 1 ? "stays" : "stay"} open, for the authors and whoever holds the seat.`,
    );
  }
  if (unresolved.document_requests > 0) {
    lines.push(
      `${count(unresolved.document_requests, "document request", "document requests")} they made ${unresolved.document_requests === 1 ? "stays" : "stay"} open.`,
    );
  }
  if (unresolved.revision_requests > 0) {
    lines.push(
      `${count(unresolved.revision_requests, "revision request", "revision requests")} they made ${unresolved.revision_requests === 1 ? "stays" : "stay"} open.`,
    );
  }
  lines.push(
    role === "adviser"
      ? "They will no longer read this review."
      : "They will no longer act on this review. They can still read it.",
  );
  return lines;
}

/**
 * A Decision's line for one reviewer it takes off (IR-1226). Their threads and
 * requests are already in what the Decision closes, so only the drafts and
 * the loss of acting are said here.
 */
export function decisionLeavingLine({ name, unresolved }: RemovalLeaving): string {
  const drafts = unresolved.drafts > 0
    ? `, and ${count(unresolved.drafts, "unsent draft", "unsent drafts")} of theirs will be discarded`
    : "";
  return `${name} will no longer act on this review${drafts}.`;
}

/**
 * The warning before a removal (IR-1226): what `leaving` leaves unresolved.
 * It warns and never blocks; the dialog's own button goes ahead.
 */
export function RemovalWarning({ leaving, role }: { leaving: RemovalLeaving; role: RemovalRole }) {
  return (
    <section
      aria-label={`What ${leaving.name} leaves`}
      className="space-y-1 rounded-control bg-stone-100 px-3 py-2 text-small text-stone-800"
    >
      <p className="break-words font-semibold">Before you take {leaving.name} off this paper</p>
      <ul className="list-disc pl-5">
        {removalLines(leaving.unresolved, role).map((line) => <li key={line}>{line}</li>)}
      </ul>
    </section>
  );
}
