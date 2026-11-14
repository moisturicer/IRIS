/**
 * What a record of the author's is waiting on, as one sentence (IR-1084,
 * spec §3 story 8).
 *
 * Built only from facts the server sent on `/records/mine/`: the open
 * requests (`waiting_on_you`, worded by the server), who holds the record now
 * (`holders`, in tracker order) and which version each office is reviewing
 * (`clearance_strip`). Nothing is worked out beyond choosing the words around
 * them, and no stage is derived: when the server names nobody, the sentence
 * says nothing is waiting.
 */
import type { ClearanceStripEntry, MyResearchItem, Party } from "@/types/records";

const OFFICES: readonly Party[] = ["itso", "ierc", "ktto"];

/** "IERC", "IERC and KTTO", "ITSO, IERC and KTTO". */
function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** The version every named office is reviewing, or null when they differ or none is known. */
function reviewedVersion(strip: ClearanceStripEntry[], offices: Party[]): number | null {
  const versions = offices.map((party) =>
    strip.find((entry) => entry.party === party && entry.kind === "reviewing")?.version ?? null);
  const first = versions[0] ?? null;
  return first != null && versions.every((v) => v === first) ? first : null;
}

/**
 * The sentence for one row. A list from an older server may lack a field, so
 * each is read as empty rather than thrown on (CODING_STANDARDS F1): the row
 * then says less, never nothing.
 */
export function waitingOn(item: MyResearchItem): string {
  if (item.pipeline_status === "draft") return "Not submitted yet. It waits on you to finish and send it.";

  const owed = item.submitter_status?.waiting_on_you ?? [];
  if (owed.length > 0) return `Waiting on you: ${owed.map((request) => request.label).join(", ")}.`;

  if (item.can_continue) return "Approved. It waits on you to continue it as a Thesis or a Project.";

  const holders = item.holders ?? [];
  const held = new Set(holders.map((holder) => holder.party));
  const offices = OFFICES.filter((party) => held.has(party));
  if (offices.length > 0) {
    const names = offices.map((party) => holders.find((h) => h.party === party)?.label ?? party.toUpperCase());
    const version = reviewedVersion(item.clearance_strip ?? [], offices);
    return `${joinNames(names)} ${names.length === 1 ? "is" : "are"} reviewing your ${
      version != null ? `version ${version}` : "paper"}. Nothing to do yet.`;
  }
  if (held.has("rdco")) return "RDCO is making the final decision. Nothing to do yet.";
  if (held.has("adviser")) return "Your Adviser is reviewing this. Nothing to do yet.";
  if (holders.length > 0) {
    return `${joinNames(holders.map((h) => h.label))} ${holders.length === 1 ? "has" : "have"} this. Nothing to do yet.`;
  }

  return "Nothing is waiting on this paper.";
}
