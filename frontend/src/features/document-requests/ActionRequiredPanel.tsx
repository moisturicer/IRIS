import { useCallback, useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { cn, formatDate } from "@/lib/utils";
import { errorDetail } from "@/lib/errorDetail";
import { ItemStatusChip } from "./itemStatus";
import type { GuidelineRequirement } from "@/api/guidelines";
import {
  GuideUnavailable, RequirementTemplate, useRequirementGuide,
} from "@/features/guidelines/requirementGuide";
import type { DocumentRequest, DocumentRequestItem } from "@/types/records";

interface ActionRequiredPanelProps {
  recordId: number;
  /** The panel's id, so a link can land on it (IR-625). */
  id?: string;
  /** Opens the review's Documents tab, where each item is uploaded (IR-1318). */
  onOpenDocuments: () => void;
}

/**
 * The owner's list of what reviewers have asked them to provide (IR-262,
 * ADR-022 §3, workflow_routing_architecture.md §9.3), on the Overview.
 *
 * One entry per **open** document request: who asked, why -- in their words,
 * rendered as text -- and each item in spec §4.10's one vocabulary
 * (`itemStatus`): Requested, Uploaded · awaiting review, Accepted,
 * Replacement needed, with the reviewer's reason for a refused upload. An
 * item for one of RDCO's requirements offers its Template (ADR-063 decision
 * 6, IR-973). Renders nothing while no request is open; a withdrawn request
 * is never shown, since the reviewer no longer needs it (IR-263).
 *
 * **Nothing is uploaded here** (IR-1318). The review's Documents tab is the
 * one place an owner uploads what is asked for, so *Upload in Documents*
 * opens it. A list that fails to load says so: an empty panel would read as
 * "nothing required", which is exactly the wrong thing to tell an owner.
 */
export function ActionRequiredPanel({ recordId, id, onOpenDocuments }: ActionRequiredPanelProps) {
  const headingId = useId();
  const [requests, setRequests] = useState<DocumentRequest[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const load = useCallback(
    () =>
      recordsApi
        .documentRequests(recordId)
        .then(({ data }) => {
          setRequests(data);
          setFailed(null);
        })
        .catch((error: unknown) => {
          setFailed(errorDetail(error, "Could not load the documents reviewers asked for. Reload the page to try again."));
        }),
    [recordId],
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (failed) {
    return (
      <p
        role="alert"
        className="rounded-card border border-stone-300 bg-surface p-4 text-sm text-brand-dark"
      >
        {failed}
      </p>
    );
  }

  const shown = (requests ?? []).filter((r) => r.state === "open");
  if (shown.length === 0) return null;

  return (
    <section
      id={id}
      tabIndex={id ? -1 : undefined}
      aria-labelledby={headingId}
      className="rounded-card border border-stone-300 bg-surface p-4 space-y-4 scroll-mt-20 focus:outline-none"
    >
      <h2 id={headingId} className="text-sm font-bold text-brand-dark flex items-center gap-2">
        <i className="fas fa-file-circle-exclamation text-xs" aria-hidden />
        Action required
      </h2>
      <RequestEntries requests={shown} />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <button type="button" onClick={onOpenDocuments} className={cn(PILL_PRIMARY, FOCUS_RING)}>
          <i className="fas fa-folder-open text-2xs" aria-hidden />
          Upload in Documents
        </button>
        <p className="text-xs text-stone-600">Nothing is sent until you submit in Documents.</p>
      </div>
    </section>
  );
}

/** The shown requests, with each requested slot's Template. */
function RequestEntries({ requests }: { requests: DocumentRequest[] }) {
  const guideRead = useRequirementGuide();
  return (
    <>
      <GuideUnavailable read={guideRead} what="The requested documents' Templates" />
      {requests.map((r) => (
        <RequestEntry key={r.id} request={r}
          requirement={(slot) => guideRead.guide?.requirement(slot) ?? null} />
      ))}
    </>
  );
}

function RequestEntry({
  request,
  requirement,
}: {
  request: DocumentRequest;
  requirement: (slot: number | null) => GuidelineRequirement | null;
}) {
  const listId = useId();
  return (
    <article className="bg-white border border-stone-300 rounded-card p-3.5">
      <h3 className="text-sm font-bold text-stone-900">
        {request.label} requested documents
      </h3>
      <p className="text-2xs text-stone-500 mt-0.5">
        {request.requested_by && `${request.requested_by} · `}
        {formatDate(request.created_at, "MMM d")}
      </p>
      {/* A text node, never innerHTML: the reviewer's words, exactly (ADR-022 §Security). */}
      <p className="text-justified text-sm text-stone-700 leading-relaxed mt-2 whitespace-pre-line break-words">
        {request.message}
      </p>
      <p id={listId} className="sr-only">
        Documents requested by {request.label}
      </p>
      <ul aria-labelledby={listId} className="mt-3 divide-y divide-stone-100">
        {request.items.map((item) => (
          <ItemRow key={item.id} item={item} asker={request.label} requirement={requirement(item.slot)} />
        ))}
      </ul>
    </article>
  );
}

function ItemRow({
  item,
  asker,
  requirement,
}: {
  item: DocumentRequestItem;
  /** Who asked, as the server words it. */
  asker: string;
  /** The RDCO requirement this item asks for, if it is one; it carries the Template. */
  requirement: GuidelineRequirement | null;
}) {
  return (
    <li className="py-2 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-sm font-semibold text-stone-800 min-w-0 break-words">
          {item.label}
        </span>
        <ItemStatusChip item={item} />
      </div>
      {requirement?.template_name && <div className="mt-1"><RequirementTemplate requirement={requirement} /></div>}
      {item.state === "missing" && item.rejection_reason && (
        <p className="text-xs text-brand mt-1 break-words">
          {asker} did not accept your last upload: “{item.rejection_reason}”
        </p>
      )}
    </li>
  );
}
