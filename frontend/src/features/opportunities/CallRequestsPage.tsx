/**
 * RDCO's Call Requests (ADR-050 decision 8, ADR-051; IR-765): every Adviser's
 * Call waiting for RDCO, oldest first, with all its fields.
 *
 * RDCO confirms one (it goes on the board), rejects one with a reason the
 * Adviser receives, or sets Featured. Every control comes from the Call's own
 * `can_*` flags, so the page compares no role names. A decision names the
 * version RDCO read (`updated_at`): a Call changed, decided or lapsed since
 * answers 409, and the page shows the server's words and reloads rather than
 * pretending it worked. Outcomes are toasts; nothing grows inside the list.
 *
 * Backend: GET /opportunities/requests/, POST /opportunities/<id>/confirm/,
 * POST /opportunities/<id>/reject/, PATCH /opportunities/<id>/ {is_featured}.
 */
import { useId, useState } from "react";

import { opportunitiesApi } from "@/api/opportunities";
import { PageHeader } from "@/components/layout/PageHeader";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/Button";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { RdcoNoteDialog } from "@/features/admin/RdcoNoteDialog";
import { cn, formatDate } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import type { Opportunity } from "@/types/opportunities";

import { FeaturedToggle, posterOf, useCallList, useFeaturedToggle, useReportCallFailure } from "./callActions";
import { CallDetails } from "./CallDetails";
import { formatDueDate } from "./opportunityUtils";

const readRequests = () => opportunitiesApi.requests();

export default function CallRequestsPage() {
  const addToast = useUIStore((s) => s.addToast);
  const { items, setItems, loading, failed, load } = useCallList(readRequests);
  const report = useReportCallFailure(load);

  const [confirming, setConfirming] = useState<Opportunity | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [rejecting,  setRejecting]  = useState<Opportunity | null>(null);

  const drop = (id: number) => setItems((current) => current.filter((o) => o.id !== id));
  // The server's copy carries the new `updated_at` a decision must name.
  const featured = useFeaturedToggle(
    (next) => setItems((current) => current.map((o) => (o.id === next.id ? next : o))),
    report,
  );

  const confirmCall = async (target: Opportunity) => {
    setConfirmBusy(true);
    try {
      await opportunitiesApi.confirm(target.id, target.updated_at);
      drop(target.id);
      addToast({ type: "success", message: `${target.title} confirmed. It's on Calls & Conferences.` });
    } catch (err) {
      report(err, `Could not confirm ${target.title}.`, () => void confirmCall(target));
    } finally {
      setConfirmBusy(false);
      setConfirming(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Call requests"
        description="Advisers' calls for papers waiting for RDCO, oldest first. A request leaves this list when its paper deadline passes."
      />

      {loading ? (
        <LoadingRegion label="Loading call requests…">
          <div className="bg-white rounded-card border border-stone-200 divide-y divide-stone-200">
            {[0, 1].map((i) => (
              <div key={i} className="p-card space-y-2.5">
                <SkeletonBlock className="h-3 w-28" />
                <SkeletonBlock tone="strong" className="h-5 w-3/4" />
                <SkeletonBlock className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        </LoadingRegion>
      ) : failed ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-triangle-exclamation"
          title="Could not load call requests"
          message="The list did not load. Nothing has been decided."
          action={<Button variant="outline" onClick={load}>Try again</Button>}
        />
      ) : items.length === 0 ? (
        <EmptyState
          framed
          icon="fa-bullhorn"
          title="No calls waiting"
          message="When an Adviser posts a call for papers, it waits here for RDCO."
        />
      ) : (
        <ol className="bg-white rounded-card border border-stone-200 divide-y divide-stone-200">
          {items.map((o) => (
            <li key={o.id}>
              <RequestRow
                call={o}
                featuring={featured.featuringId === o.id}
                onConfirm={() => setConfirming(o)}
                onReject={() => setRejecting(o)}
                onToggleFeatured={() => void featured.toggle(o)}
              />
            </li>
          ))}
        </ol>
      )}

      {/* Names the Adviser and the Call, so a slip on the wrong row is seen. */}
      <ConfirmDialog
        open={confirming !== null}
        title={confirming ? `Confirm ${confirming.title}?` : ""}
        message={confirming
          ? `It goes on Calls & Conferences for everyone, with its link. ${posterOf(confirming)} is told in-app.`
          : ""}
        confirmLabel="Confirm call"
        focusCancel
        confirming={confirmBusy}
        onConfirm={() => { if (confirming && !confirmBusy) void confirmCall(confirming); }}
        onCancel={() => setConfirming(null)}
      />

      {rejecting && (
        <RdcoNoteDialog
          kind="reason"
          title="Reject this call"
          submitLabel="Reject call"
          audience="Adviser"
          requester={posterOf(rejecting)}
          recordTitle={rejecting.title}
          intro="It stays with the Adviser, who may change it and send it again, or delete it."
          send={(reason) => opportunitiesApi.reject(rejecting.id, rejecting.updated_at, reason)}
          onClose={() => setRejecting(null)}
          onDone={() => {
            drop(rejecting.id);
            addToast({ type: "success", message: `${rejecting.title} rejected. Its Adviser is told why.` });
            setRejecting(null);
          }}
          onFailure={(err) => (report(err, `Could not reject ${rejecting.title}.`).stale ? "close" : "keep")}
        />
      )}
    </div>
  );
}

interface RequestRowProps {
  call: Opportunity;
  featuring: boolean;
  onConfirm: () => void;
  onReject: () => void;
  onToggleFeatured: () => void;
}

/** One request, every field shown, About in full. */
function RequestRow({ call: o, featuring, onConfirm, onReject, onToggleFeatured }: RequestRowProps) {
  const titleId = useId();
  return (
    <article aria-labelledby={titleId} className="p-card-compact md:p-card space-y-3">
      <div className="min-w-0">
        <CallDetails call={o} titleId={titleId} clampAbout={false} />
      </div>

      <dl className="grid gap-x-section gap-y-1 text-small sm:grid-cols-[auto_1fr]">
        <dt className="text-stone-600">Paper deadline</dt>
        <dd className="text-stone-900">{formatDueDate(o.due_date)}</dd>
        <dt className="text-stone-600">Link</dt>
        <dd className="min-w-0 break-all">
          {o.external_url ? (
            <a
              href={o.external_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn("text-brand underline underline-offset-2", FOCUS_RING, COLOUR_TRANSITION)}
            >
              {o.external_url}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          ) : (
            <span className="text-stone-600">None given</span>
          )}
        </dd>
        <dt className="text-stone-600">Posted by</dt>
        <dd className="text-stone-900">
          {o.posted_by_name || "An account that no longer exists"}, {formatDate(o.created_at)}
        </dd>
      </dl>

      <div className="flex flex-wrap items-center gap-2">
        {o.can_confirm && (
          <Button type="button" size="sm" variant="primary" onClick={onConfirm} aria-label={`Confirm ${o.title}`}>
            <i className="fas fa-check" aria-hidden="true" /> Confirm
          </Button>
        )}
        {o.can_reject && (
          <Button type="button" size="sm" variant="outline" onClick={onReject} aria-label={`Reject ${o.title}`}>
            Reject
          </Button>
        )}
        {o.can_feature && <FeaturedToggle call={o} busy={featuring} onToggle={onToggleFeatured} />}
      </div>
    </article>
  );
}
