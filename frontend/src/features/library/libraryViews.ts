import type { ReadingStatus } from "@/api/library";
import { READING_STATUSES } from "@/store/library.store";

import type { ResearchFilter } from "./researchSections";

/**
 * Which list My Library's main column shows (IR-1311). Every view is named
 * once, in the rail: the owner's own research by filter (IR-410), the
 * account's saves, a Reading status and the reader's own folders (IR-566,
 * IR-572), reading history (IR-756), saved calls (IR-766) and download
 * requests (IR-743).
 */
export type LibraryView =
  | { kind: "research"; filter: ResearchFilter }
  | { kind: "saved" }
  | { kind: "status"; status: ReadingStatus }
  | { kind: "folder"; id: number }
  | { kind: "history" }
  | { kind: "calls" }
  | { kind: "downloads" };

/** The views that list saved papers, which share one list and toolbar. */
export type ReadingView = Extract<LibraryView, { kind: "saved" | "status" | "folder" | "history" }>;

export const isReadingView = (view: LibraryView): view is ReadingView =>
  view.kind === "saved" || view.kind === "status" || view.kind === "folder" || view.kind === "history";

const RESEARCH_SECTIONS: Record<string, ResearchFilter> = {
  research: "all", waiting: "waiting", review: "review", drafts: "drafts", finished: "finished",
};
const STATUS_SECTIONS = new Set<string>(READING_STATUSES.map((s) => s.value));

/** The view a reader lands on with no `section`: an author's research, anyone else's saves. */
export const defaultView = (mayAuthor: boolean): LibraryView =>
  mayAuthor ? { kind: "research", filter: "all" } : { kind: "saved" };

/**
 * Read the view from the address. `?section=` keeps every value the tabs
 * used (`research`, `saved`, `calls`, `downloads`; `overview` lands on the
 * default), so old links and `/workspace` still open the same list.
 */
export function viewFromParams(params: URLSearchParams, mayAuthor: boolean): LibraryView {
  const section = params.get("section") ?? "";
  if (section in RESEARCH_SECTIONS) {
    return mayAuthor ? { kind: "research", filter: RESEARCH_SECTIONS[section] } : { kind: "saved" };
  }
  if (STATUS_SECTIONS.has(section)) return { kind: "status", status: section as ReadingStatus };
  if (section === "folder") {
    const id = Number(params.get("folder"));
    return Number.isInteger(id) && id > 0 ? { kind: "folder", id } : { kind: "saved" };
  }
  if (section === "saved" || section === "history" || section === "calls" || section === "downloads") {
    return { kind: section };
  }
  return defaultView(mayAuthor);
}

/** Write the view into the address, keeping every other parameter (Publish's among them). */
export function paramsForView(current: URLSearchParams, view: LibraryView, mayAuthor: boolean): URLSearchParams {
  const next = new URLSearchParams(current);
  next.delete("section");
  next.delete("folder");
  if (isSameView(view, defaultView(mayAuthor))) return next;
  if (view.kind === "research") next.set("section", view.filter === "all" ? "research" : view.filter);
  else if (view.kind === "status") next.set("section", view.status);
  else if (view.kind === "folder") {
    next.set("section", "folder");
    next.set("folder", String(view.id));
  } else next.set("section", view.kind);
  return next;
}

export function viewKey(view: LibraryView): string {
  if (view.kind === "research") return `research:${view.filter}`;
  if (view.kind === "status") return `status:${view.status}`;
  if (view.kind === "folder") return `folder:${view.id}`;
  return view.kind;
}

export const isSameView = (a: LibraryView, b: LibraryView) => viewKey(a) === viewKey(b);

/** Back from a key, for the phone's picker. */
export function viewFromKey(key: string): LibraryView | null {
  const [kind, value] = key.split(":");
  if (kind === "research" && value) return { kind: "research", filter: value as ResearchFilter };
  if (kind === "status" && value) return { kind: "status", status: value as ReadingStatus };
  if (kind === "folder" && value) return { kind: "folder", id: Number(value) };
  if (kind === "saved" || kind === "history" || kind === "calls" || kind === "downloads") return { kind };
  return null;
}
