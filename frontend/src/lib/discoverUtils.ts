import type { RecordListItem } from "@/types/records";

export const DISCOVER_QUICK_CHIPS = [
  "Computer Science",
  "Patents",
  "Recent 2026",
  "Bio-Engineering",
] as const;

export const DEFAULT_TRENDING_TOPICS = [
  "Retrieval-Augmented Generation",
  "ChromaDB",
  "Godot Game Engine",
  "Demand Forecasting",
  "Vision-Language-Action",
];

export function chipToSearchTerm(chip: string): string {
  if (chip === "Recent 2026") return "2026";
  if (chip === "Patents") return "patent";
  if (chip === "Computer Science") return "computer";
  return chip;
}

export function formatAuthorList(authors: { name: string }[]): string {
  return authors.map((a) => a.name).join(", ") || "Unknown authors";
}

export function recordCollegeLabel(record: RecordListItem): string {
  return record.classification_name ?? record.record_type_name ?? "CIT-U Research";
}

export function recordPubLabel(record: RecordListItem): string {
  const year = record.year_accomplished ?? new Date(record.created_at).getFullYear();
  return `Published: ${year}`;
}

export type SpotlightBadge = { label: string; tone: "award" | "patent" | "faculty" };

export function spotlightBadges(record: RecordListItem, index: number): SpotlightBadge[] {
  const badges: SpotlightBadge[] = [];
  if (index === 0 || record.access_count >= 10) {
    badges.push({ label: "Award Winning", tone: "award" });
  }
  if (record.is_ip || record.for_commercialization) {
    badges.push({ label: "Patent Pending", tone: "patent" });
  }
  if (index === 1 && badges.length < 2) {
    badges.push({ label: "Faculty Spotlight", tone: "faculty" });
  }
  if (badges.length === 0) {
    badges.push({ label: "Featured Research", tone: "faculty" });
  }
  return badges.slice(0, 2);
}

export function listBadges(record: RecordListItem): string[] {
  const tags: string[] = [];
  if (record.is_ip) tags.push("IP");
  if (record.for_commercialization) tags.push("Commercialization");
  if (record.community_extension) tags.push("Extension");
  if (record.record_type_name) tags.push(record.record_type_name);
  return tags.slice(0, 3);
}

/** Build trending topics from loaded records + defaults. */
export function buildTrendingTopics(records: RecordListItem[]): string[] {
  const fromData = records
    .map((r) => r.classification_name)
    .filter((n): n is string => Boolean(n));
  const unique = [...new Set([...fromData, ...DEFAULT_TRENDING_TOPICS])];
  return unique.slice(0, 6);
}

export function pickSpotlightAndRecent(records: RecordListItem[]) {
  const sorted = [...records].sort((a, b) => b.access_count - a.access_count);
  const spotlight = sorted.slice(0, 2);
  const spotlightIds = new Set(spotlight.map((r) => r.id));
  const recent = records
    .filter((r) => !spotlightIds.has(r.id))
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);
  return { spotlight, recent };
}
