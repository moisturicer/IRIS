import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate, joinLabels } from "@/lib/utils";
import type { PaperDueDate, PaperPerson, Readiness, ReadinessItem, RecordDetail, RecordTracker, TrackerPartyRow, TrackerPartyState, TrackerResubmission, TrackerSeat } from "@/types/records";

import { ReadinessFacts } from "./ReadinessPanel";
import { dueText } from "./ReviewStatus";
import { readinessFacts } from "./yourPart";

/** Parties never asked are not part of this review, as on the status strip. */
const UNASKED: ReadonlySet<TrackerPartyState> = new Set(["not_requested", "not_required"]);

/** A glyph beside each state's words, never instead of them. */
const STATE_ICON: Partial<Record<TrackerPartyState, string>> = {
  active: "fa-eye",
  completed: "fa-circle-check",
  withdrawn: "fa-circle-minus",
  awaiting: "fa-clock",
};

/** A person's glyph: their verdict once finished, else how far their seat has got. */
const VERDICT_ICON: Partial<Record<string, string>> = {
  approved: "fa-shield-halved",
  negative_finding: "fa-flag",
  declined: "fa-rotate-left",
  rejected: "fa-ban",
};
const SEAT_ICON: Record<TrackerSeat["state"], string> = {
  assigned: "fa-clock",
  in_review: "fa-eye",
  done: "fa-circle-check",
  withdrawn: "fa-circle-minus",
};

/** "October 7, 2026", as Version history reads (IR-1202). */
const HISTORY_DATE_FORMAT = "MMMM d, yyyy";

/** Where a Readiness link lands: a party's reviewers, or the facts themselves. */
export const detailsTarget = (ids: string, to: string) => `${ids}-details-${to}`;

/**
 * The review workspace's Details tab (ADR-032 §10 Amendment, IR-681; the
 * third column that repeated it is gone, IR-1094): Readiness's facts, then
 * Reviewers (one row per person, due dates on their line), Researchers,
 * Adviser, Classification (keywords as pills), Flagged by the authors and
 * Version history (IR-1202: who and what only; Participants, Copy link and
 * the document list left).
 *
 * Built from record detail's permission-filtered paper_details and the tracker.
 * Who is reviewing and due dates are review content: the
 * tracker sends seats and reviews as null to a viewer who may not read the
 * review (IR-479), and then those sections are withheld, not shown empty.
 *
 * Reviewers lists every party the tracker sends (IR-685): one not involved
 * reads as the tracker says, an unclaimed Pool as the office itself. The host
 * passes `requestReview` (the gear on the heading, with the routing flags'
 * targets) and `addColleague` only when the viewer may take them; the two
 * stay separate controls. *Add a colleague* sits under the viewer's own
 * office, the party it adds to (IR-1340).
 */
export function ReviewDetails({ record, tracker, ids, readiness, onReadinessAction, requestReview, addColleague }: {
  record: RecordDetail;
  tracker: RecordTracker;
  ids: string;
  /**
   * What the footer's one line leaves out (IR-1094): the server's facts, less
   * the ones that restate a party's status, which Reviewers says once.
   */
  readiness?: Readiness | null;
  onReadinessAction?: (action: NonNullable<ReadinessItem["action"]>) => void;
  requestReview?: { targets: string[]; onOpen: () => void };
  /** The control, and the party whose row it sits under: the viewer's own office. */
  addColleague?: { party: string; control: (officeLabel: string) => ReactNode };
}) {
  const requestNoteId = useId();
  const readable = tracker.reviews !== null;
  const details = record.paper_details;
  const researchers = details?.researchers ?? [];
  // Review content (IR-681): shown on each party's line, never to a viewer who may not read the review.
  const dues = readable ? details?.due_dates : null;
  const flags = details?.author_flags ?? [];
  const participants = readable ? details?.participants : null;
  const facts = readinessFacts(readiness);

  const pills = [record.record_type_name, record.classification_name, record.psced, ...(record.keywords ?? [])]
    .filter((v): v is string => Boolean(v));
  // Where the paper comes from, program then college, as one line under the pills.
  const affiliation = [["Program", affiliationText(details?.programs)], ["College", affiliationText(details?.colleges)]] as const;
  const dueFor = (party: string) => dues?.find((d) => d.party === party);
  const revisionFor = (party: string) => (tracker.resubmissions ?? []).find((r) => r.party === party && r.state === "open");

  return (
    <div className="space-y-5">
      {facts.length > 0 && onReadinessAction && (
        <Section id={detailsTarget(ids, "readiness")} title="Readiness">
          <ReadinessFacts items={facts} onAction={onReadinessAction} />
        </Section>
      )}
      <Section id={detailsTarget(ids, "reviewers")} title="Reviewers" action={requestReview && (
        <button type="button" aria-label="Request review" title="Request review" aria-describedby={requestNoteId}
          onClick={requestReview.onOpen} className={cn("review-control text-stone-600 hover:text-brand", FOCUS_RING)}>
          <i className="fas fa-sliders" aria-hidden />
        </button>
      )}>
        {requestReview && <p id={requestNoteId} className="text-2xs text-stone-600">Can be sent to {joinLabels(requestReview.targets)}</p>}
        {tracker.parties.length === 0 ? <p className="text-small text-stone-600">No party has been asked yet.</p> : (
          <ul className="space-y-3">
            {tracker.parties.map((row) => (
              <PartyReviewers key={row.party} row={row} ids={ids} readable={readable} people={participants ?? []}
                due={dueFor(row.party)} revision={revisionFor(row.party)}
                extra={addColleague?.party === row.party ? addColleague.control(row.label) : null} />
            ))}
          </ul>
        )}
      </Section>
      <Section title="Researchers">
        {researchers.length ? <ul className="space-y-2">{researchers.map((p) => <li key={p.id}><Person person={p} /></li>)}</ul>
          : <p className="text-small text-stone-600">None listed</p>}
      </Section>
      <Section title="Adviser">
        {details?.adviser ? <Person person={details.adviser} /> : <p className="text-small text-stone-600">None named</p>}
      </Section>
      <Section title="Classification">
        {pills.length > 0 && (
          <ul aria-label="Type, area and keywords" className="flex flex-wrap gap-1.5">
            {pills.map((v) => <li key={v} className="review-tag font-semibold text-stone-900">{v}</li>)}
          </ul>
        )}
        <p className="text-small text-stone-600">
          {affiliation.map(([k, v], i) => (
            <span key={k}>{i > 0 && <span aria-hidden> · </span>}<span className="sr-only">{k}: </span><span>{v}</span></span>
          ))}
        </p>
      </Section>
      <Section title="Flagged by the authors">
        {flags.length ? (
          <ul className="flex flex-wrap gap-1.5">
            {flags.map((f) => (
              <li key={f.office} title={f.hint} className="review-tag"><i className="fas fa-check text-2xs mr-1" aria-hidden />{f.label}</li>
            ))}
          </ul>
        ) : <p className="text-small text-stone-600">Nothing flagged</p>}
      </Section>
      <Section title="Version history">
        <VersionHistory versions={record.versions}
          partyLabel={(party) => tracker.parties.find((p) => p.party === party)?.label ?? party.toUpperCase()} />
      </Section>
    </div>
  );
}

function Section({ id, title, action, children }: { id?: string; title: string; action?: ReactNode; children: ReactNode }) {
  const headingId = useId();
  // A pull request sidebar's small sans label (IR-1131), not a title: the rule above does the dividing.
  const heading = <h3 id={headingId} className="text-small font-semibold text-stone-600">{title}</h3>;
  return (
    <section id={id} tabIndex={id ? -1 : undefined} aria-labelledby={headingId} className={cn("space-y-2 border-t border-stone-200 pt-4 first:border-0 first:pt-0", FOCUS_RING)}>
      {action ? <div className="flex items-center justify-between gap-2">{heading}{action}</div> : heading}
      {children}
    </section>
  );
}

/**
 * Each manuscript Version, oldest first, as plain text (IR-1202): what was
 * submitted and when. Downloads and the files themselves are the Documents
 * tab's (IR-1203); comparing two Versions is the Changes tab's.
 */
function VersionHistory({ versions, partyLabel }: {
  versions: RecordDetail["versions"];
  partyLabel: (party: string) => string;
}) {
  if (versions == null) return <p className="text-small text-stone-600">Not disclosed</p>;
  if (versions.length === 0) return <p className="text-small text-stone-600">No version recorded</p>;
  // A Version's `documents` names every slot's file as it was submitted, so an
  // unchanged upload recurs under each later Version. Each is listed once,
  // under the first Version that has it, so nothing reads as submitted twice.
  const seen = new Set<number>();
  const firstListed = versions.map((v) => [...(v.documents ?? []), ...(v.documents_added ?? [])].filter((d) => {
    if (seen.has(d.upload_id)) return false;
    seen.add(d.upload_id);
    return true;
  }));
  return (
    <ol aria-label="Manuscript versions, oldest first" className="space-y-3 text-small text-stone-700">
      {versions.map((v, i) => {
        const documents = firstListed[i];
        return (
          <li key={v.number} className="space-y-1">
            <p><span className="font-semibold text-stone-900">Manuscript v{v.number}</span> · submitted {formatDate(v.created_at, HISTORY_DATE_FORMAT)}</p>
            {documents.length > 0 && (
              <ul aria-label={`Documents with v${v.number}`} className="space-y-1 border-l border-stone-200 pl-3">
                {documents.map((d) => (
                  <li key={d.upload_id}>
                    {d.slot} v{d.version} · submitted {formatDate(d.uploaded_at, HISTORY_DATE_FORMAT)}
                    {/* Why it was replaced (IR-1201); absent where requests are not disclosed. */}
                    {(d.rejections ?? []).map((r, n) => (
                      <p key={n} className="text-stone-600">Replacement asked by {partyLabel(r.party)}: {r.reason}</p>
                    ))}
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function affiliationText(values: string[] | null | undefined): string {
  return values == null ? "Not disclosed" : values.length ? values.join("; ") : "Not recorded";
}

/**
 * One status per party (IR-1094, audit US-17), drawn one row per person
 * (IR-1193). A party with people says where it stands through them: each
 * person's row names the party and when, with their own state on the right. A
 * party with none (not asked, waiting, withheld, or an unclaimed Pool) says it
 * once on its own row. The row is never both.
 */
function PartyReviewers({ row, ids, readable, people, due, revision, extra }: {
  row: TrackerPartyRow; ids: string; readable: boolean; people: PaperPerson[];
  due?: PaperDueDate; revision?: TrackerResubmission;
  /** Drawn under the party's rows: *Add a colleague*, on the viewer's own office (IR-1340). */
  extra?: ReactNode;
}) {
  // The tracker sends only the withdrawn seats a Decision cut short, labelled so.
  const seats = row.seats ?? [];
  const outcome = row.outcome && row.outcome !== "pending" ? row.outcome_label : null;
  const unasked = UNASKED.has(row.state);
  const showSeats = !row.in_pool && readable && seats.length > 0;
  // A clearance kept through a resubmission (ADR-003), said as the mockup says it.
  const kept = row.carryover === "preserved";
  const when = row.at ? (row.state === "active" ? `Since ${formatDate(row.at)}` : formatDate(row.at)) : null;
  const dueLine = due ? dueText({ ...due, state: row.state }) : null;
  const subline = (label: string | null) => {
    const lead = [label, when].filter(Boolean).join(" · ");
    if (!lead && !dueLine && !revision) return null;
    return <>
      {(lead || dueLine) && (
        <p className="text-2xs text-stone-600">
          {lead}
          {dueLine && <span className={cn(due?.is_overdue && "font-semibold text-brand")}>{lead ? " · " : ""}{dueLine}</span>}
        </p>
      )}
      {revision && (
        <p className="text-2xs text-stone-600">
          Requested revision{revision.version != null ? ` on v${revision.version}` : ""}{revision.created_at ? `, ${formatDate(revision.created_at)}` : ""}
        </p>
      )}
    </>;
  };
  const status = (icon: string, label: string, title?: string | null) => (
    <span title={title ?? undefined} className="shrink-0 whitespace-nowrap pt-0.5 text-2xs font-semibold text-stone-700">
      <i className={cn("fas mr-1", icon)} aria-hidden />{label}
    </span>
  );
  const keptStatus = () => status("fa-shield-halved", "Kept", row.carryover_label);
  return (
    <li id={detailsTarget(ids, row.party)} tabIndex={-1} className={cn("rounded-control", FOCUS_RING)}>
      {showSeats ? (
        <ul aria-label={`Reviewing for ${row.label}`} className="space-y-3">
          {seats.map((seat, i) => (
            <li key={i} className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <Person name={seat.reviewer_name ?? "A reviewer"} role={`${row.label} reviewer`}
                  person={people.find((p) => p.id === seat.reviewer)} />
                <div className="pl-8">{subline(row.label)}</div>
              </div>
              {kept ? keptStatus()
                : status((seat.verdict && VERDICT_ICON[seat.verdict]) ?? SEAT_ICON[seat.state], seat.verdict_label ?? seat.state_label)}
            </li>
          ))}
        </ul>
      ) : (
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-start gap-2">
            <span aria-hidden className="review-avatar review-avatar-office">
              <i className={cn("fas text-2xs", row.in_pool ? "fa-users" : "fa-building-columns")} />
            </span>
            <div className="min-w-0">
              <p className={cn("text-small font-semibold", unasked ? "text-stone-600" : "text-stone-900")}>{row.label}</p>
              {/* The office, not a person: nobody holds a seat to show. */}
              {row.in_pool ? <p className="text-2xs text-stone-600">Nobody has claimed this yet</p> : subline(null)}
            </div>
          </div>
          {!row.in_pool && (kept ? keptStatus() : status(STATE_ICON[row.state] ?? "fa-circle",
            [row.state_label, outcome, row.changes_requested ? "Changes requested" : null].filter(Boolean).join(" · ")))}
        </div>
      )}
      {extra}
    </li>
  );
}

/**
 * The server decides which card fields are readable. Never reconstruct an
 * affiliation from classification or another person's card.
 */
function Person({ person, name = person?.name ?? "A reviewer", role = person?.role ?? null }: {
  person?: PaperPerson; name?: string; role?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const cardId = useId();
  const [position, setPosition] = useState({ left: 16, top: 16 });
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");

  // The sidebar scrolls. Keep the card out of its clipping ancestor and
  // inside the viewport.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = button.current?.getBoundingClientRect();
      const bounds = card.current?.getBoundingClientRect();
      if (!anchor || !bounds) return;
      const below = anchor.bottom + 4;
      setPosition({
        left: Math.max(16, Math.min(anchor.left, window.innerWidth - bounds.width - 16)),
        top: Math.max(16, Math.min(below, window.innerHeight - bounds.height - 16)),
      });
    };
    place();
    window.addEventListener("resize", place);
    document.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      document.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    card.current?.focus();
    const close = () => { setOpen(false); button.current?.focus(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); close(); } };
    // Restore focus after the outside click's normal focus movement.
    const onClick = (e: MouseEvent) => {
      if (!card.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onClick);
    };
  }, [open]);

  return (
    <span className="relative inline-flex">
      <button
        ref={button} type="button" aria-expanded={open} aria-controls={open ? cardId : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn("review-control inline-flex items-center gap-2 text-small text-stone-900 hover:underline", FOCUS_RING)}
      >
        <span aria-hidden className="review-avatar review-avatar-brand">{initials}</span>
        {name}
      </button>
      {open && createPortal(
        <div ref={card} id={cardId} role="dialog" aria-label={name} tabIndex={-1}
          style={position}
          className={cn("fixed z-50 w-56 max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-control border border-stone-300 bg-overlay p-3 shadow-sm", FOCUS_RING)}>
          <p className="font-display text-base font-semibold text-stone-900">{name}</p>
          {role && <p className="text-small text-stone-600">{role} on this record</p>}
          {person && <dl className="mt-2 space-y-1 break-words text-small text-stone-700">
            {(["office", "college", "department", "program"] as const).map((key) => person[key] && (
              <div key={key}><dt className="font-semibold capitalize">{key}</dt><dd>{person[key]}</dd></div>
            ))}
            {person.email && <div><dt className="font-semibold">Contact</dt><dd>
              <a href={`mailto:${person.email}`} className={cn("text-brand hover:underline", FOCUS_RING)}>{person.email}</a>
            </dd></div>}
          </dl>}
        </div>, document.body,
      )}
    </span>
  );
}
