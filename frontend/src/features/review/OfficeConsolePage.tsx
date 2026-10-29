import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { reviewsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { ResearchCard } from "@/components/shared/ResearchCard";
import { Badge, Button, Skeleton } from "@/components/ui";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { OfficeConsole, OfficeConsoleRow } from "@/types/reviews";

import { AssignReviewerDialog } from "./AssignReviewerDialog";
import { ExtendDueDateDialog } from "./ExtendDueDateDialog";
import { ReassignDialog } from "./ReassignDialog";

type Load = "loading" | "ready" | "failed" | "refused";

type Acting =
  | { act: "assign"; row: OfficeConsoleRow }
  | { act: "reassign"; row: OfficeConsoleRow }
  | { act: "extend"; row: OfficeConsoleRow };

const BACK_LINK = cn(
  "inline-flex min-h-9 items-center rounded-lg border border-stone-200 px-3 text-small font-semibold text-stone-700 hover:border-stone-400",
  COLOUR_TRANSITION,
  FOCUS_RING,
);

/**
 * The coordinator console (IR-623): one office's open reviews -- who holds
 * each, when it arrived and when it is due -- and each member's load, so a
 * coordinator can see who is stretched and move work.
 *
 * It decides nothing. Its three acts are the existing ones: *Assign* an
 * unclaimed record, *Reassign* a held one (with a reason), and *Extend* a
 * due date (with a reason), and the server re-checks each. What the server
 * sends decides what is offered: `can_extend` per row, Assign only on a
 * pool row, and the page itself only to a coordinator of the office. Due
 * dates and overdue are the server's; nothing here works out a date.
 */
export default function OfficeConsolePage() {
  const [data, setData] = useState<OfficeConsole | null>(null);
  const [state, setState] = useState<Load>("loading");
  const [acting, setActing] = useState<Acting | null>(null);
  const [announcement, setAnnouncement] = useState("");

  /** Reload; whether it worked, so an act announces only what is shown. */
  const load = useCallback(async (): Promise<boolean> => {
    try {
      const { data: next } = await reviewsApi.office(null);
      setData(next);
      setState("ready");
      return true;
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      setState(status === 403 ? "refused" : "failed");
      return false;
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const retry = () => {
    setState("loading");
    void load();
  };

  const done = async (message: string) => {
    setActing(null);
    setAnnouncement("");
    if (await load()) setAnnouncement(message);
  };

  const label = data?.office_label;
  const rows = data?.rows ?? [];

  return (
    <div>
      <PageHeader
        title={label ? `${label} console` : "Office console"}
        description="Your office's open reviews, who holds each, and when it is due."
        actions={state === "ready" && rows.length > 0 ? <Link to="/review" className={BACK_LINK}>My Reviews</Link> : undefined}
      />

      {/* Polite, and always rendered, so a change to it is what gets announced. */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {state === "loading" ? (
        <Skeleton rows={3} label="Loading the console…" />
      ) : state === "refused" ? (
        <EmptyState
          icon="fa-lock"
          title="This console is for coordinators"
          message="Only a coordinator of an office can see its open reviews and move them."
          action={<Link to="/review" className={BACK_LINK}>Back to My Reviews</Link>}
        />
      ) : state === "failed" ? (
        <EmptyState
          icon="fa-triangle-exclamation"
          tone="error"
          title="Could not load the console"
          message="Check your connection, then try again."
          action={<Button type="button" variant="secondary" onClick={retry}>Try again</Button>}
        />
      ) : (
        <div className="space-y-8">
          <section aria-labelledby="console-workload">
            <h2 id="console-workload" className="mb-3 text-body font-semibold text-stone-900">Workload</h2>
            <div className="overflow-x-auto rounded-xl border border-stone-200">
              <table aria-labelledby="console-workload" className="w-full text-small">
                <thead className="bg-stone-50 text-left text-stone-600">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-semibold">Reviewer</th>
                    <th scope="col" className="px-4 py-2 font-semibold text-right">Open</th>
                    <th scope="col" className="px-4 py-2 font-semibold text-right">Overdue</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.load ?? []).map((m) => (
                    <tr key={m.reviewer} className="border-t border-stone-100">
                      <td className="px-4 py-2 text-stone-900">{m.name}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{m.open}</td>
                      <td className={cn("px-4 py-2 text-right tabular-nums", m.overdue > 0 && "font-semibold text-brand")}>
                        {m.overdue}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="console-open">
            <h2 id="console-open" className="mb-3 text-body font-semibold text-stone-900">Open reviews</h2>
            {rows.length === 0 ? (
              <EmptyState
                icon="fa-inbox"
                title={`Nothing open at ${label}`}
                message="Records routed to your office appear here until each review is finished."
                action={<Link to="/review" className={BACK_LINK}>Back to My Reviews</Link>}
              />
            ) : (
              <ul aria-labelledby="console-open" className="space-y-3">
                {rows.map((r) => (
                  <li key={r.key}>
                    <ConsoleRow row={r} onAct={(act) => setActing({ act, row: r })} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {acting?.act === "assign" && (
        <AssignReviewerDialog
          assignmentId={acting.row.assignment}
          recordTitle={acting.row.title}
          viewerId={null}
          onClose={() => setActing(null)}
          onAssigned={(name) => done(`Assigned to ${name}.`)}
        />
      )}
      {acting?.act === "reassign" && acting.row.seat != null && (
        <ReassignDialog
          seatId={acting.row.seat}
          assignmentId={acting.row.assignment}
          recordTitle={acting.row.title}
          holderName={acting.row.reviewer_name}
          onClose={() => setActing(null)}
          onReassigned={(name) => done(`Reassigned to ${name}.`)}
        />
      )}
      {acting?.act === "extend" && acting.row.due_at && (
        <ExtendDueDateDialog
          assignmentId={acting.row.assignment}
          recordTitle={acting.row.title}
          dueAt={acting.row.due_at}
          onClose={() => setActing(null)}
          onExtended={() => done("Due date extended.")}
        />
      )}
    </div>
  );
}

function dueLine(row: OfficeConsoleRow) {
  if (!row.due_at) return "No due date";
  if (row.is_overdue) return `Overdue · was due ${formatDate(row.due_at)}`;
  return `Due ${formatDate(row.due_at)}`;
}

function ConsoleRow({ row, onAct }: { row: OfficeConsoleRow; onAct: (act: Acting["act"]) => void }) {
  const holder = row.kind === "pool" ? "Unclaimed" : `${row.reviewer_name ?? "A reviewer"} · ${row.seat_state_label}`;

  const status = (
    <>
      <span className="font-semibold text-stone-800">{holder}</span>
      <span className={cn(row.is_overdue && "font-semibold text-brand")}>{dueLine(row)}</span>
      {row.clock_paused && <Badge variant="warning">Clock paused</Badge>}
    </>
  );

  const actions = (
    <>
      {row.can_extend && (
        <Button type="button" variant="secondary" size="sm" onClick={() => onAct("extend")}
          aria-label={`Extend due date: ${row.title}`}>
          Extend due date
        </Button>
      )}
      {row.kind === "pool" ? (
        <Button type="button" size="sm" onClick={() => onAct("assign")} aria-label={`Assign reviewer: ${row.title}`}>
          Assign reviewer
        </Button>
      ) : (
        <Button type="button" size="sm" onClick={() => onAct("reassign")} aria-label={`Reassign: ${row.title}`}>
          Reassign
        </Button>
      )}
    </>
  );

  return (
    <ResearchCard
      href={`/records/${row.record}?section=review`}
      title={row.title}
      meta={<span>Received {formatDate(row.opened_at)}</span>}
      status={status}
      actions={actions}
    />
  );
}
