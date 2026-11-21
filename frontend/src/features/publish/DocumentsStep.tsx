/**
 * Publish, step 3: the record type's documents (ADR-063 decision 6, IR-973).
 *
 * The same compact rows as the review page's Documents tab (`DocumentRow`):
 * the Manuscript first, then each of RDCO's requirements with its
 * Required/Optional label, its Template and a small Upload. Nothing here
 * blocks Continue or Submit: an empty Required slot is accepted (decision 3),
 * and an office that needs a document asks for it later (ADR-022).
 *
 * The labels and Templates come from Guidelines' list; what the draft already
 * holds comes from its own slots, which the dialog reads (Review lists them
 * too). For a Proposal, the chosen Adviser's own Templates are pointed out
 * (decision 8): Advisers share them for Proposals.
 */
import { useId } from "react";

import { guidelinesApi, type SharedTemplate } from "@/api/guidelines";
import { documentsApi } from "@/api/documents";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { PlainTextWithLinks } from "@/components/shared/PlainTextWithLinks";
import { useApiRead, type ApiRead } from "@/hooks/useApiRead";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { cn } from "@/lib/utils";
import { DocumentRow, byline } from "@/features/records/paper-view/DocumentRow";
import { useRowUploads } from "@/features/records/paper-view/rowUploads";
import {
  GuideUnavailable, ManuscriptTemplate, RequirementTemplate, isSharedList, useRequirementGuide,
} from "@/features/guidelines/requirementGuide";
import { TemplateDownload } from "@/features/guidelines/TemplateDownload";
import type { SlotWithUploads } from "@/types/documents";

import { GuidelinesLink } from "./ManuscriptStep";

/** A shape guard for the draft's slots (CODING_STANDARDS F1). */
export function isSlotList(data: unknown): data is SlotWithUploads[] {
  return Array.isArray(data) && data.every(
    (slot) => slot && typeof slot.id === "number" && typeof slot.name === "string" && Array.isArray(slot.uploads),
  );
}

interface DocumentsStepProps {
  recordId: number;
  typeId: number | null;
  typeName: string;
  /** The manuscript's file name, when this visit uploaded it (a resumed draft's isn't kept). */
  manuscriptName: string | null;
  /** The draft's slots, read by the dialog. */
  slots: ApiRead<SlotWithUploads[] | null>;
  /** The chosen Adviser, whose Templates a Proposal points out. */
  adviser: { id: number; name: string } | null;
  isProposal: boolean;
}

export function DocumentsStep({ recordId, typeId, typeName, manuscriptName, slots, adviser, isProposal }: DocumentsStepProps) {
  const guideRead = useRequirementGuide();
  const guide = guideRead.guide;
  const { pdfUpload } = useRowUploads(async () => slots.refresh());
  const list = slots.status === "ready" && isSlotList(slots.data) ? slots.data : null;

  return (
    <div className="flex flex-col gap-section">
      <div className="space-y-2">
        <p className="text-body text-stone-700">
          Only the manuscript is needed to submit. Add any other document now, or later when an office asks for it.
          Uploads are PDF only, so save a Word or Excel file as a PDF first.
        </p>
        <GuidelinesLink typeName={typeName || null} />
      </div>

      {isProposal && adviser && <AdviserTemplates adviser={adviser} />}

      <GuideUnavailable read={guideRead} />

      {slots.status === "loading" && <Skeleton rows={3} label="Loading your documents…" />}
      {slots.status !== "loading" && !list && (
        <div role="alert" className={cn(LOAD_ERROR, "flex-wrap")}>
          <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
          <span className="flex-1">Your documents didn't load. You can still continue and submit.</span>
          <Button type="button" variant="outline" size="sm" onClick={slots.retry}>Try again</Button>
        </div>
      )}
      {list && (
        <ul aria-label="Documents" className="divide-y divide-stone-200 rounded-card border border-stone-200 bg-white">
          <DocumentRow
            name="Manuscript"
            required={guide ? true : undefined}
            template={<ManuscriptTemplate recordType={guide?.recordType({ id: typeId }) ?? null} />}
            latest={manuscriptName ?? "Uploaded"}
          />
          {list.map((slot) => {
            // A requirement RDCO removed shows only for the file it holds, and takes no upload (decision 5).
            if (slot.hidden && slot.uploads.length === 0) return null;
            const requirement = guide?.requirement(slot.id) ?? null;
            const [latest] = slot.uploads;
            return (
              <DocumentRow
                key={slot.id}
                name={slot.name}
                required={requirement?.is_required}
                template={<RequirementTemplate requirement={requirement} />}
                latest={latest ? byline(latest.version, latest.uploaded_by_name, latest.created_at) : null}
                actions={!slot.hidden && pdfUpload(`slot:${slot.id}`, `Upload ${slot.name}`,
                  (file, onProgress) => documentsApi.upload(recordId, slot.id, file, { onProgress }))}
              />
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** The chosen Adviser's own Templates, for a Proposal; nothing when they share none. */
function AdviserTemplates({ adviser }: { adviser: { id: number; name: string } }) {
  const headingId = useId();
  const read = useApiRead((signal) => guidelinesApi.advisersTemplates({ signal }).then((r) => r.data), []);
  if (read.status === "loading") {
    return <p role="status" className="text-small text-stone-600">Loading your Adviser's Templates…</p>;
  }
  const shared = read.status === "ready" && isSharedList(read.data) ? read.data : null;
  if (!shared) {
    return (
      <p className="text-small text-stone-600">
        Your Adviser's Templates didn't load.{" "}
        <Button type="button" variant="ghost" size="sm" onClick={read.retry}>Try again</Button>
      </p>
    );
  }
  const theirs = shared.filter((t: SharedTemplate) => t.shared_by.id === adviser.id);
  if (theirs.length === 0) return null;
  return (
    <section aria-labelledby={headingId} className="rounded-card border border-stone-200 bg-surface p-card-compact">
      <h3 id={headingId} className="text-body font-semibold text-stone-900">
        Templates from your Adviser, {adviser.name}
      </h3>
      <p className="mt-1 text-small text-stone-600">Shared for Proposals. Follow them where they apply.</p>
      <ul className="mt-3 space-y-3">
        {theirs.map((t) => (
          <li key={t.id} className="space-y-1">
            <p className="break-words text-small font-semibold text-stone-900">{t.title}</p>
            {t.description && <PlainTextWithLinks text={t.description} className="text-small text-stone-700" />}
            <TemplateDownload
              fileName={t.file_name}
              label={`Download ${t.title} by ${adviser.name}, ${t.file_name}`}
              download={() => guidelinesApi.downloadAdviserTemplate(t.id)}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
