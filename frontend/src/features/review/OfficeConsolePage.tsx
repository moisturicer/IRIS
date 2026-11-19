import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { reviewsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { ClearanceStrip, hasStrip } from "@/components/shared/ClearanceStrip";
import { Button, Skeleton } from "@/components/ui";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { TONES } from "@/components/ui/statusTones";
import { RowMenu, type RowMenuItem } from "@/features/accounts/RowMenu";
import { failureMessage, readFailureKind } from "@/lib/readFailure";
import { cn, formatDate } from "@/lib/utils";
import type { OfficeConsole, OfficeConsoleAction, OfficeConsoleRow, OfficeConsoleStatusKind } from "@/types/reviews";

import { AssignReviewerDialog } from "./AssignReviewerDialog";
import { ExtendDueDateDialog } from "./ExtendDueDateDialog";
import { ReassignDialog } from "./ReassignDialog";
import { WithdrawSeatDialog } from "./WithdrawSeatDialog";

type Load = "loading" | "ready" | "interrupted" | "failed" | "refused";

type Acting = { act: OfficeConsoleAction; row: OfficeConsoleRow };

const BACK_LINK = cn(
  "inline-flex min-h-9 items-center rounded-control border border-stone-200 px-3 text-small font-semibold text-stone-700 hover:border-stone-400",
  COLOUR_TRANSITION,
  FOCUS_RING,
);

/**
 * The coordinator console (IR-623, IR-1136): one office's open reviews in one
 * table -- paper, reviewer, due date, status -- and each member's load, so a
 * coordinator can see who is stretched and move work.
 *
 * It decides nothing. Its three acts are the existing ones: *Assign* an
 * unclaimed record, *Reassign* a held one (with a reason), and *Extend* a
 * due date (with a reason), and the server re-checks each. What the server
 * sends decides what is offered: each row's `actions`, and the page itself
 * only to a coordinator of the office (anyone else is refused, and told so).
 * Status wording, due dates and overdue are the server's; nothing here works
 * out a date. Below 640px each row stacks into labelled lines.
 */
export default function OfficeConsolePage() {
  const [data, setData] = useState<OfficeConsole | null>(null);
  const [state, setState] = useState<Load>("loading");
  const [failure, setFailure] = useState<unknown>(null);
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
      const kind = readFailureKind(err);
      setFailure(err);
      setState(kind === "unavailable" ? "refused" : kind);
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
  const members = data?.load ?? [];

  return (
    <div>
      <PageHeader
        title={label ? `${label} office console` : "Office console"}
        description={
          label
            ? `Assign ${label}'s reviews, and move due dates when a reviewer needs more time.`
            : "Assign your office's reviews, and move due dates when a reviewer needs more time."
        }
        actions={state === "ready" && rows.length > 0 ? <Link to="/review" className={BACK_LINK}>My Reviews</Link> : undefined}
      />

      {/* Polite, and always rendered, so a change to it is what gets announced. */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {state === "loading" ? (
        <Skeleton rows={3} label="Loading the console…" onRetry={retry} />
      ) : state === "refused" ? (
        <EmptyState
          icon="fa-lock"
          title="This console is for coordinators"
          message="Only a coordinator of an office can see its open reviews and move them."
          action={<Link to="/review" className={BACK_LINK}>Back to My Reviews</Link>}
        />
      ) : state === "interrupted" ? (
        <InterruptedState what="console" onRetry={retry} />
      ) : state === "failed" ? (
        <EmptyState
          icon="fa-triangle-exclamation"
          tone="error"
          title="Could not load the console"
          message={failureMessage(failure)}
          action={<Button type="button" variant="secondary" onClick={retry}>Try again</Button>}
        />
      ) : (
        <div className="space-y-6">
          {members.length > 0 && (
            <section aria-labelledby="console-workload">
              <h2 id="console-workload" className="mb-2 text-small font-semibold text-stone-700">Workload</h2>
              <ul aria-labelledby="console-workload" className="flex flex-wrap gap-2">
                {members.map((m) => (
                  <li
                    key={m.reviewer}
                    className={cn(
                      "rounded-full px-3 py-1 text-small text-stone-700 ring-1",
                      m.overdue > 0 ? "text-brand ring-brand" : "ring-stone-300",
                    )}
                  >
                    <span className="font-semibold text-stone-900">{m.name}</span>
                    {` · ${m.open_count} open`}
                    {m.overdue > 0 && ` · ${m.overdue} overdue`}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {rows.length === 0 ? (
            <EmptyState
              icon="fa-inbox"
              title={`Nothing open at ${label}`}
              message="Records routed to your office appear here until each review is finished."
              action={<Link to="/review" className={BACK_LINK}>Back to My Reviews</Link>}
            />
          ) : (
            <div className="rounded-card border border-stone-200 max-sm:border-0">
              <table className="w-full text-small max-sm:block">
                <caption className="sr-only">
                  {label} open reviews: who holds each, when it is due, and what you can do
                </caption>
                <thead className="bg-stone-50 text-left text-stone-600 max-sm:sr-only">
                  <tr>
                    <th scope="col" className="px-4 py-2 font-semibold">Paper</th>
                    <th scope="col" className="px-4 py-2 font-semibold">Reviewer</th>
                    <th scope="col" className="px-4 py-2 font-semibold">Due</th>
                    <th scope="col" className="px-4 py-2 font-semibold">Status</th>
                    <th scope="col" className="px-4 py-2 font-semibold"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="max-sm:block max-sm:space-y-3">
                  {rows.map((r) => (
                    <ConsoleRow key={r.key} row={r} onAct={(act) => setActing({ act, row: r })} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
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
          leaving={acting.row.unresolved
            ? { name: acting.row.reviewer_name ?? "This reviewer", unresolved: acting.row.unresolved }
            : null}
          onClose={() => setActing(null)}
          onReassigned={(name) => done(`Reassigned to ${name}.`)}
        />
      )}
      {acting?.act === "withdraw" && acting.row.seat != null && (
        <WithdrawSeatDialog
          seatId={acting.row.seat}
          recordTitle={acting.row.title}
          officeLabel={label ?? "your office"}
          holderName={acting.row.reviewer_name}
          unresolved={acting.row.unresolved}
          completesOffice={acting.row.withdraw_completes_office === true}
          onClose={() => setActing(null)}
          onWithdrawn={() => done(`${acting.row.reviewer_name ?? "The reviewer"} was withdrawn.`)}
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

/** Tone by meaning, never the only signal: each chip also carries its words and an icon. */
const STATUS_TONE: Record<OfficeConsoleStatusKind, { tone: string; icon: string }> = {
  kept:       { tone: TONES.settled,   icon: "fa-check" },
  overdue:    { tone: TONES.attention, icon: "fa-triangle-exclamation" },
  unassigned: { tone: TONES.quiet,     icon: "fa-user-plus" },
  due:        { tone: TONES.active,    icon: "fa-clock" },
  paused:     { tone: TONES.quiet,     icon: "fa-pause" },
  no_date:    { tone: TONES.quiet,     icon: "fa-minus" },
};

const CELL = "px-4 py-3 align-top max-sm:flex max-sm:gap-3 max-sm:px-0 max-sm:py-1";
const CELL_LABEL = "hidden shrink-0 basis-20 text-stone-500 max-sm:inline";

function ConsoleRow({ row, onAct }: { row: OfficeConsoleRow; onAct: (act: OfficeConsoleAction) => void }) {
  const { tone, icon } = STATUS_TONE[row.status.kind];
  const may = (act: OfficeConsoleAction) => row.actions.includes(act);

  // Assign is the row's own button; the rest sit in its "More actions" menu.
  const items: RowMenuItem[] = [
    ...(may("reassign") ? [{ key: "reassign", label: "Reassign…", onSelect: () => onAct("reassign") }] : []),
    // IR-1226: take the reviewer off without naming anyone; it says when that finishes the office.
    ...(may("withdraw")
      ? [{
          key: "withdraw",
          label: "Withdraw…",
          onSelect: () => onAct("withdraw"),
        }]
      : []),
    ...(may("extend") ? [{ key: "extend", label: "Extend due date…", onSelect: () => onAct("extend") }] : []),
  ];

  return (
    <tr className="border-t border-stone-100 max-sm:block max-sm:rounded-card max-sm:border max-sm:border-stone-200 max-sm:p-4">
      <td className={cn(CELL, "max-sm:block")}>
        <Link
          to={`/records/${row.record}?section=review`}
          className={cn("font-semibold text-stone-900 hover:text-brand", FOCUS_RING)}
        >
          {row.title}
        </Link>
        {row.authors_line && <p className="mt-0.5 text-stone-600">{row.authors_line}</p>}
        {hasStrip(row.clearance_strip) && (
          <div className="mt-2"><ClearanceStrip entries={row.clearance_strip} /></div>
        )}
      </td>
      <td className={CELL}>
        <span className={CELL_LABEL} aria-hidden>Reviewer</span>
        <span className={cn(row.kind === "pool" && "text-stone-500")}>
          {row.kind === "pool" ? "Nobody yet" : row.reviewer_name ?? "A reviewer"}
        </span>
      </td>
      <td className={CELL}>
        <span className={CELL_LABEL} aria-hidden>Due</span>
        <span>{row.due_at ? formatDate(row.due_at) : "—"}</span>
      </td>
      <td className={CELL}>
        <span className={CELL_LABEL} aria-hidden>Status</span>
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-label font-semibold", tone)}>
          <i className={cn("fas", icon)} aria-hidden />
          {row.status.text}
        </span>
      </td>
      <td className={cn(CELL, "text-right max-sm:justify-end")}>
        <div className="inline-flex items-center gap-1">
          {may("assign") && (
            <Button type="button" size="sm" onClick={() => onAct("assign")} aria-label={`Assign reviewer: ${row.title}`}>
              Assign
            </Button>
          )}
          <RowMenu label={`More actions: ${row.title}`} items={items} />
        </div>
      </td>
    </tr>
  );
}
