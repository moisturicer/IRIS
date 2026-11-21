/**
 * What each record type asks for (ADR-063 decisions 3, 4 and 6), read once
 * from Guidelines' own list (`GET /documents/guidelines/`) so every screen
 * that shows a requirement row labels it and offers its Template the same way.
 *
 * A paper's own slots say what it has; this says what RDCO asks for. A slot
 * the guide doesn't list (one RDCO removed, or one a reviewer added for one
 * paper) gets no label and no Template, because it is no longer, or never
 * was, one of RDCO's requirements.
 */
import {
  guidelinesApi, type GuidelineRecordType, type GuidelineRequirement, type SharedTemplate,
} from "@/api/guidelines";
import { useApiRead } from "@/hooks/useApiRead";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

import { TemplateDownload } from "./TemplateDownload";

/** A shape guard (CODING_STANDARDS F1): anything else is treated as a failed read. */
export function isGuidelines(data: unknown): data is GuidelineRecordType[] {
  return Array.isArray(data) && data.every(
    (rt) => rt && typeof rt.id === "number" && typeof rt.name === "string"
      && rt.manuscript && Array.isArray(rt.requirements),
  );
}

/** The same guard for the Advisers' Templates list. */
export function isSharedList(data: unknown): data is SharedTemplate[] {
  return Array.isArray(data) && data.every(
    (t) => t && typeof t.id === "number" && typeof t.title === "string" && t.shared_by
      && typeof t.shared_by.name === "string",
  );
}

export interface RequirementGuide {
  /** The record type, by id (Publish knows it) or by name (a record's detail carries only that). */
  recordType: (which: { id?: number | null; name?: string | null }) => GuidelineRecordType | null;
  /** One of RDCO's listed requirements, by its slot id; null for any other slot. */
  requirement: (slotId: number | null | undefined) => GuidelineRequirement | null;
}

export type RequirementGuideRead =
  | { status: "loading"; guide: null; retry: () => void }
  | { status: "failed"; guide: null; retry: () => void }
  | { status: "ready"; guide: RequirementGuide; retry: () => void };

export function guideFrom(types: GuidelineRecordType[]): RequirementGuide {
  const bySlot = new Map(types.flatMap((rt) => rt.requirements.map((req) => [req.id, req] as const)));
  return {
    recordType: ({ id, name }) =>
      types.find((rt) => (id != null ? rt.id === id : name != null && rt.name === name)) ?? null,
    requirement: (slotId) => (slotId == null ? null : bySlot.get(slotId) ?? null),
  };
}

export function useRequirementGuide(): RequirementGuideRead {
  const read = useApiRead((signal) => guidelinesApi.list({ signal }).then((r) => r.data), []);
  if (read.status === "loading") return { status: "loading", guide: null, retry: read.retry };
  if (read.status !== "ready" || !isGuidelines(read.data)) return { status: "failed", guide: null, retry: read.retry };
  return { status: "ready", guide: guideFrom(read.data), retry: read.retry };
}

/** The record type's Manuscript Template, when RDCO has set one. */
export function ManuscriptTemplate({ recordType }: { recordType: GuidelineRecordType | null }) {
  const fileName = recordType?.manuscript.template_name;
  if (!recordType || !fileName) return null;
  return (
    <TemplateDownload
      fileName={fileName}
      label={`Download the Manuscript Template, ${fileName}`}
      download={() => guidelinesApi.downloadManuscriptTemplate(recordType.id)}
    />
  );
}

/** A requirement's Template, when it has one. */
export function RequirementTemplate({ requirement }: { requirement: GuidelineRequirement | null }) {
  if (!requirement?.template_name) return null;
  return (
    <TemplateDownload
      fileName={requirement.template_name}
      label={`Download the ${requirement.name} Template, ${requirement.template_name}`}
      download={() => guidelinesApi.downloadRequirementTemplate(requirement.id)}
    />
  );
}

/**
 * Said where the labels and Templates would be when the guide didn't load
 * (F1: show what still works, say what didn't). The documents stay usable.
 */
export function GuideUnavailable({ read, what = "The Required and Optional labels and the Templates" }: {
  read: RequirementGuideRead;
  /** What is missing, as the screen shows it. */
  what?: string;
}) {
  if (read.status !== "failed") return null;
  return (
    <p className="text-small text-stone-600">
      {what} didn't load.{" "}
      <button type="button" onClick={read.retry} className={cn("rounded-control font-semibold text-brand underline", FOCUS_RING)}>
        Try again
      </button>
    </p>
  );
}
