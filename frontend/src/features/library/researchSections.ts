/**
 * My research, grouped by who has each record now (IR-410; spec §4.9 as
 * amended 2026-10-11).
 *
 * Every rule reads a server field: `workflow_state` for what waits on the
 * owner, `holders` for who is reviewing, and `pipeline_status` for drafts and
 * finished records. Nothing here works out a stage; it only files what the
 * server already said. A record lands in exactly one section, the first whose
 * rule it meets; the rules cover every `PipelineStatus`, so none is dropped.
 * A section with nothing in it is left out.
 */
import type { MyResearchItem, Party } from "@/types/records";

export type ResearchSectionId =
  | "waiting" | "adviser" | "offices" | "rdco" | "review"
  | "drafts" | "finished" | "deleting" | "archived";

export interface ResearchSection {
  id:     ResearchSectionId;
  title:  string;
  /** One line under the title saying what the section means. */
  note?:  string;
  items:  MyResearchItem[];
}

const OFFICES: ReadonlySet<Party> = new Set<Party>(["itso", "ierc", "ktto"]);

const holds = (item: MyResearchItem, test: (party: Party) => boolean) =>
  item.holders.some((holder) => test(holder.party));

/** Rules in display order; the first that matches files the record. */
const RULES: ReadonlyArray<Omit<ResearchSection, "items"> & { match: (item: MyResearchItem) => boolean }> = [
  {
    id: "waiting",
    title: "Waiting on you",
    note: "A reviewer needs something from you before review can go on.",
    match: (item) => item.workflow_state === "awaiting_resubmission" || item.workflow_state === "awaiting_document",
  },
  { id: "drafts", title: "Drafts", note: "Not yet submitted.", match: (item) => item.pipeline_status === "draft" },
  {
    id: "rdco",
    title: "With RDCO for a decision",
    match: (item) => item.pipeline_status === "in_review" && holds(item, (party) => party === "rdco"),
  },
  {
    id: "offices",
    title: "With the offices",
    note: "Reviewed in parallel. An office that has cleared stays cleared if another asks for revisions.",
    match: (item) => item.pipeline_status === "in_review" && holds(item, (party) => OFFICES.has(party)),
  },
  {
    id: "adviser",
    title: "With your Adviser",
    match: (item) => item.pipeline_status === "in_review" && holds(item, (party) => party === "adviser"),
  },
  { id: "review", title: "In review", match: (item) => item.pipeline_status === "in_review" },
  {
    id: "finished",
    title: "Finished",
    note: "Accepted, published or kept unlisted.",
    match: (item) => ["published", "approved", "completed"].includes(item.pipeline_status),
  },
  {
    id: "deleting",
    title: "Deletion requested",
    match: (item) => item.pipeline_status === "pending_delete",
  },
  {
    id: "archived",
    title: "Archived",
    note: "Rejected records, kept for your reference.",
    match: (item) => item.pipeline_status === "rejected",
  },
];

/** The order sections are shown in: what needs the owner, then the review path, then the rest. */
const DISPLAY_ORDER: readonly ResearchSectionId[] = [
  "waiting", "adviser", "offices", "rdco", "review", "drafts", "finished", "deleting", "archived",
];

export function groupResearch(items: readonly MyResearchItem[]): ResearchSection[] {
  const filed = new Map<ResearchSectionId, MyResearchItem[]>();
  for (const item of items) {
    const rule = RULES.find((r) => r.match(item));
    if (!rule) continue;
    filed.set(rule.id, [...(filed.get(rule.id) ?? []), item]);
  }
  return DISPLAY_ORDER.flatMap((id) => {
    const found = filed.get(id);
    if (!found?.length) return [];
    const rule = RULES.find((r) => r.id === id)!;
    return [{ id: rule.id, title: rule.title, note: rule.note, items: found }];
  });
}
