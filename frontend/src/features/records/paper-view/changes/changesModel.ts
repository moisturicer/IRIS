/**
 * What the Changes tab says about a comparison (ADR-058 §3, IR-873), apart
 * from how it draws it: labels, counts, the page outline, and which threads
 * sit under which section. Pure, so each wording is tested on its own.
 */
import type {
  ChangeCounts, ChangeKind, PlacedThread, SectionComparison, VersionChange, VersionComparisonPayload,
} from "@/types/records";

/** Every change is labelled in words; colour only repeats it. */
export const KIND_LABEL: Record<ChangeKind, string> = {
  changed: "Changed",
  added:   "Added",
  removed: "Removed",
  moved:   "Moved",
};

const KIND_ORDER: ChangeKind[] = ["changed", "added", "removed", "moved"];

/** "3 changed · 1 added", or "No changes" when every count is 0. */
export function countsLabel(counts: ChangeCounts): string {
  const parts = KIND_ORDER.filter((k) => counts[k] > 0).map((k) => `${counts[k]} ${k}`);
  return parts.length ? parts.join(" · ") : "No changes";
}

/** The heading a section is shown under: its later heading, else its earlier one. */
export function sectionTitle(section: SectionComparison): string {
  const heading = section.to ?? section.from;
  return heading?.heading || "Untitled section";
}

/** Short words for what happened to the section itself, beside its changes. */
export function sectionMarks(section: SectionComparison, from: number, to: number): string[] {
  const marks: string[] = [];
  if (section.status === "added") marks.push(`New in v${to}`);
  if (section.status === "removed") marks.push(`Not in v${to}`);
  if (section.renamed && section.from) marks.push(`Renamed from "${section.from.heading}"`);
  if (section.moved) marks.push("Moved");
  if (section.status === "unchanged" && !section.moved && !section.renamed) marks.push(`Same as v${from}`);
  return marks;
}

/** Does the section hold anything to look at? */
export const sectionHasChanges = (s: SectionComparison) =>
  s.status !== "unchanged" || s.renamed || s.moved || s.changes.length > 0;

/** The page a change is shown at: where it is now, else where it was. */
export const changePage = (c: VersionChange) => (c.to ?? c.from)?.page ?? null;

/** By page: each page's changes in order, for the outline and the list. */
export function pageGroups(changes: readonly VersionChange[]): { page: number | null; changes: VersionChange[] }[] {
  const groups: { page: number | null; changes: VersionChange[] }[] = [];
  for (const change of changes) {
    const page = changePage(change);
    const last = groups[groups.length - 1];
    if (last && last.page === page) last.changes.push(change);
    else groups.push({ page, changes: [change] });
  }
  return groups;
}

export function countChanges(changes: readonly VersionChange[]): ChangeCounts {
  const counts: ChangeCounts = { changed: 0, added: 0, removed: 0, moved: 0 };
  for (const c of changes) counts[c.kind] += 1;
  return counts;
}

/** Threads by section index; by page they are all listed together under `null`. */
export function threadsBySection(threads: readonly PlacedThread[]): Map<number | null, PlacedThread[]> {
  const out = new Map<number | null, PlacedThread[]>();
  for (const t of threads) {
    const list = out.get(t.section) ?? [];
    list.push(t);
    out.set(t.section, list);
  }
  return out;
}

/**
 * The comparison only when its shape is what the tab draws (CODING_STANDARDS
 * F1): a wrong shape is shown as a failed request, never thrown.
 */
export function readComparison(data: unknown): VersionComparisonPayload | null {
  if (!data || typeof data !== "object") return null;
  const body = data as Partial<VersionComparisonPayload>;
  if (typeof body.state !== "string" || typeof body.from !== "number" || typeof body.to !== "number") return null;
  if (!Array.isArray(body.documents)) return null;
  if (body.state === "ready") {
    const listed = body.mode === "pages" ? body.changes : body.sections;
    if (!Array.isArray(listed) || !body.counts || !Array.isArray(body.notices)) return null;
  }
  return body as VersionComparisonPayload;
}
