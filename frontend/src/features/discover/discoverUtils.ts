import type { RecordListItem } from "@/types/records";

export type SpotlightBadge = {
  label: string;
  className: string;
};

export function formatAuthors(record: RecordListItem): string {
  return record.authors.map((a) => a.name).join(", ") || "—";
}

export function truncateText(text: string, max = 160): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max).trimEnd()}…`;
}

export function getSpotlightBadges(record: RecordListItem): SpotlightBadge[] {
  const badges: SpotlightBadge[] = [];

  if (record.community_extension) {
    badges.push({ label: "Award Winning", className: "bg-amber-100 text-amber-800" });
  }
  if (record.is_ip) {
    badges.push({
      label: record.for_commercialization ? "Patent Pending" : "Intellectual Property",
      className: "bg-blue-100 text-blue-800",
    });
  }
  if (record.access_count >= 5) {
    badges.push({ label: "Faculty Spotlight", className: "bg-emerald-100 text-emerald-800" });
  }

  if (badges.length === 0 && record.record_type_name) {
    badges.push({ label: record.record_type_name, className: "bg-gray-100 text-gray-700" });
  }

  return badges.slice(0, 2);
}

export function classificationToHashtag(name: string): string {
  return `# ${name}`;
}
