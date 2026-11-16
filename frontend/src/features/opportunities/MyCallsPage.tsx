import { useId, useState } from "react";

import { opportunitiesApi } from "@/api/opportunities";
import { PageHeader } from "@/components/layout/PageHeader";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button, ButtonLink } from "@/components/ui/Button";
import { FOCUS_RING } from "@/components/ui/interaction";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { TONES } from "@/components/ui/statusTones";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import type { CallStatus, Opportunity } from "@/types/opportunities";

import { CallDetails } from "./CallDetails";
import { useCallList, useDeleteCall, useReportCallFailure } from "./callActions";
import { OpportunityFormDialog } from "./OpportunityFormDialog";
import { formatDueDate } from "./opportunityUtils";

/** A status's tone, by what it means: waiting is in hand, rejected needs the poster. */
const STATUS_TONE: Record<CallStatus, string> = {
  pending:   TONES.active,
  confirmed: TONES.settled,
  rejected:  TONES.attention,
};

/**
 * My Calls (IR-765): every Call the viewer posted, in every status, so an
 * Adviser sees where each stands. A rejected one shows RDCO's reason; the
 * poster can edit it, which sends it to RDCO again, or delete it. A request
 * whose paper deadline passes before RDCO decides is deleted, not expired
 * (ADR-050 amendment of 2026-11-15), and its poster gets a notice.
 *
 * Edit and Delete come from each Call's `can_edit` and `can_delete`.
 * Outcomes are toasts; nothing grows inside the list.
 */
const readMine = () => opportunitiesApi.mine();

export function MyCallsPage() {
  const addToast = useUIStore((s) => s.addToast);
  const { items, setItems, loading, failed, load } = useCallList(readMine);
  const report = useReportCallFailure(load);
  const deletion = useDeleteCall((gone) => setItems((current) => current.filter((o) => o.id !== gone.id)), report);
  const [editing, setEditing] = useState<Opportunity | null>(null);

  const handleSaved = (saved: Opportunity) => {
    setItems((current) => current.map((o) => (o.id === saved.id ? saved : o)));
    setEditing(null);
    addToast(saved.status === "pending"
      ? { type: "info", message: `${saved.title} sent to RDCO. It appears on the board once RDCO confirms it.` }
      : { type: "success", message: "Changes saved." });
  };

  return (
    <div>
      <PageHeader
        title="My Calls"
        description="The calls for papers you posted, and where each stands with RDCO."
        actions={<ButtonLink to="/opportunities" variant="outline" size="sm">Calls & Conferences</ButtonLink>}
      />

      {loading ? (
        <LoadingRegion label="Loading your calls…">
          <div className="bg-white rounded-card border border-stone-200 p-card space-y-2.5">
            <SkeletonBlock className="h-3 w-28" />
            <SkeletonBlock tone="strong" className="h-5 w-3/4" />
          </div>
        </LoadingRegion>
      ) : failed ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-triangle-exclamation"
          title="Could not load your calls"
          message="The list did not load."
          action={<Button variant="outline" onClick={load}>Try again</Button>}
        />
      ) : items.length === 0 ? (
        <EmptyState
          framed
          icon="fa-bullhorn"
          title="You haven't posted a call"
          message="Post one from Calls & Conferences. An Adviser's call appears there once RDCO confirms it."
          action={<ButtonLink to="/opportunities" variant="outline">Go to Calls & Conferences</ButtonLink>}
        />
      ) : (
        <ol className="bg-white rounded-card border border-stone-200 divide-y divide-stone-200">
          {items.map((o) => (
            <li key={o.id}>
              <MyCallRow call={o} onEdit={() => setEditing(o)} onDelete={() => deletion.ask(o)} />
            </li>
          ))}
        </ol>
      )}

      {editing && (
        <OpportunityFormDialog
          opportunity={editing}
          canFeature={editing.can_feature}
          onClose={() => setEditing(null)}
          onSaved={(saved) => handleSaved(saved)}
        />
      )}

      <ConfirmDialog
        open={deletion.deleting !== null}
        title="Delete this call?"
        message={deletion.deleting ? `"${deletion.deleting.title}" will be deleted. This cannot be undone.` : ""}
        confirmLabel="Delete call"
        danger
        confirming={deletion.busy}
        onConfirm={deletion.confirm}
        onCancel={deletion.cancel}
      />
    </div>
  );
}

function MyCallRow({ call: o, onEdit, onDelete }: { call: Opportunity; onEdit: () => void; onDelete: () => void }) {
  const titleId = useId();
  // The accessible name starts with the words on the button (WCAG 2.5.3).
  const editLabel = o.status === "rejected" ? "Edit and send again" : "Edit";
  return (
    <article aria-labelledby={titleId} className="p-card-compact md:p-card space-y-3">
      <p className="flex flex-wrap items-center gap-2">
        <span className={cn("inline-flex items-center px-2.5 py-1 rounded-full text-label font-semibold", STATUS_TONE[o.status])}>
          {o.status_label}
        </span>
        <span className="text-small text-stone-600">Paper deadline {formatDueDate(o.due_date)}</span>
      </p>

      <div className="min-w-0">
        <CallDetails call={o} titleId={titleId} />
      </div>

      {o.status === "rejected" && o.review_reason && (
        <p className="text-small max-w-prose break-words">
          <span className="font-semibold text-stone-900">RDCO's reason: </span>
          <span className="text-stone-700">{o.review_reason}</span>
        </p>
      )}

      {(o.can_edit || o.can_delete) && (
        <div className="flex flex-wrap items-center gap-1">
          {o.can_edit && (
            <Button type="button" variant="ghost" size="sm" onClick={onEdit} aria-label={`${editLabel} ${o.title}`} className={cn("min-h-11 lg:min-h-0", FOCUS_RING)}>
              <i className="fas fa-pen" aria-hidden="true" />
              {editLabel}
            </Button>
          )}
          {o.can_delete && (
            <Button type="button" variant="ghost" size="sm" onClick={onDelete} aria-label={`Delete ${o.title}`} className={cn("min-h-11 lg:min-h-0", FOCUS_RING)}>
              <i className="fas fa-trash-can" aria-hidden="true" />
              Delete
            </Button>
          )}
        </div>
      )}
    </article>
  );
}
