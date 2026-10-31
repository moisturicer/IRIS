import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, downloadBlob, formatDate, joinLabels } from "@/lib/utils";
import type { PaperPerson, RecordDetail, RecordTracker, TrackerPartyRow, TrackerPartyState, TrackerSeat } from "@/types/records";

import { dueText } from "./ReviewStatus";

/** Parties never asked are not part of this review, as on the status strip. */
const UNASKED: ReadonlySet<TrackerPartyState> = new Set(["not_requested", "not_required"]);

/** A glyph beside each state's words, never instead of them. */
const STATE_ICON: Partial<Record<TrackerPartyState, string>> = {
  active: "fa-circle-dot",
  completed: "fa-circle-check",
  withdrawn: "fa-circle-minus",
  awaiting: "fa-clock",
};

/** A person's glyph: their verdict once finished, else how far their seat has got. */
const VERDICT_ICON: Partial<Record<string, string>> = {
  approved: "fa-circle-check",
  negative_finding: "fa-flag",
  declined: "fa-rotate-left",
  rejected: "fa-ban",
};
const SEAT_ICON: Record<TrackerSeat["state"], string> = {
  assigned: "fa-clock",
  in_review: "fa-circle-dot",
  done: "fa-circle-check",
  withdrawn: "fa-circle-minus",
};

/** Where a Readiness link lands: a party's reviewers, or Documents. */
export const detailsTarget = (ids: string, to: string) => `${ids}-details-${to}`;

/**
 * The review workspace's details sidebar (ADR-032 §10 Amendment, IR-681):
 * Reviewers by party, then Researchers, Adviser, Classification, Flagged by
 * the authors, Keywords, Version, Due dates, Documents and Participants.
 *
 * Built from record detail's permission-filtered paper_details and the tracker.
 * Who is reviewing, due dates and participants are review content: the
 * tracker sends seats and reviews as null to a viewer who may not read the
 * review (IR-479), and then those sections are withheld, not shown empty.
 *
 * Reviewers lists every party the tracker sends (IR-685): one not involved
 * reads as the tracker says, an unclaimed Pool as the office itself. The host
 * passes `requestReview` (the gear on the heading, with the routing flags'
 * targets) and `addColleague` only when the viewer may take them; the two
 * stay separate controls.
 */
export function ReviewDetails({ record, tracker, ids, requestReview, addColleague }: {
  record: RecordDetail;
  tracker: RecordTracker;
  ids: string;
  requestReview?: { targets: string[]; onOpen: () => void };
  addColleague?: ReactNode;
}) {
  const requestNoteId = useId();
  const readable = tracker.reviews !== null;
  const details = record.paper_details;
  const researchers = details?.researchers ?? [];
  const dues = readable ? details?.due_dates : null;
  const flags = details?.author_flags ?? [];
  const versions = record.versions ?? [];
  const latest = versions[versions.length - 1];
  const openRequests = (tracker.document_requests ?? []).filter((r) => r.state === "open");
  const participants = readable ? details?.participants : null;

  return (
    <div className="space-y-5">
      <Section id={detailsTarget(ids, "reviewers")} title="Reviewers" action={requestReview && (
        <button type="button" aria-label="Request review" title="Request review" aria-describedby={requestNoteId}
          onClick={requestReview.onOpen} className={cn("review-control text-stone-600 hover:text-brand", FOCUS_RING)}>
          <i className="fas fa-gear" aria-hidden />
        </button>
      )}>
        {requestReview && <p id={requestNoteId} className="text-2xs text-stone-600">Can be sent to {joinLabels(requestReview.targets)}</p>}
        {tracker.parties.length === 0 ? <p className="text-small text-stone-600">No party has been asked yet.</p> : (
          <ul className="space-y-3">
            {tracker.parties.map((row) => <PartyReviewers key={row.party} row={row} ids={ids} readable={readable} people={participants ?? []} />)}
          </ul>
        )}
        {addColleague}
      </Section>
      <Section title="Researchers">
        {researchers.length ? <ul className="space-y-1">{researchers.map((p) => <li key={p.id}><Person person={p} /></li>)}</ul>
          : <p className="text-small text-stone-600">None listed</p>}
      </Section>
      <Section title="Adviser">
        {details?.adviser ? <Person person={details.adviser} /> : <p className="text-small text-stone-600">None named</p>}
      </Section>
      <Section title="Classification">
        <dl className="review-kv">
          {[["Type", record.record_type_name], ["Area", record.classification_name], ["PSCED", record.psced]]
            .filter(([, v]) => v).map(([k, v]) => <Fact key={k} k={k!} v={v!} />)}
          <Fact k="College" v={affiliationText(details?.colleges)} />
          <Fact k="Program" v={affiliationText(details?.programs)} />
        </dl>
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
      <Section title="Keywords">
        {(record.keywords?.length ?? 0) > 0 ? (
          <ul className="flex flex-wrap gap-1.5">{record.keywords!.map((k) => <li key={k} className="review-tag">{k}</li>)}</ul>
        ) : <p className="text-small text-stone-600">None listed</p>}
      </Section>
      <Section title="Version">
        {latest ? (
          <dl className="review-kv">
            <Fact k="Current" v={`v${latest.number} · ${formatDate(latest.created_at)}`} />
            <Fact k="First submitted" v={formatDate(versions[0].created_at)} />
            <Fact k="History" v={`${versions.length} ${versions.length === 1 ? "version" : "versions"}`} />
          </dl>
        ) : <p className="text-small text-stone-600">{record.versions === null ? "Not disclosed" : "No version recorded"}</p>}
      </Section>
      {dues != null && (
        <Section title="Due dates">
          {dues.length ? (
            <dl className="review-kv">
              {dues.map((due) => <Fact key={due.party} k={due.label} v={dueText(due) ?? "No due date recorded"} strong={due.is_overdue} />)}
            </dl>
          ) : <p className="text-small text-stone-600">None running</p>}
        </Section>
      )}
      <Section id={detailsTarget(ids, "documents")} title="Documents">
        <ul className="space-y-1.5 text-small">
          <li><i className="fas fa-file-lines mr-2 text-stone-500" aria-hidden />
            {(latest?.manuscript_url ?? record.abstract_file)
              ? <DocumentDownload name={`Manuscript${latest ? ` · v${latest.number}` : ""}`} filename="manuscript.pdf"
                fetch={() => latest?.manuscript_url
                  ? recordsApi.versionManuscriptBlob(record.id, latest.number)
                  : recordsApi.manuscriptBlob(record.id)} />
              : "No manuscript recorded"}
          </li>
          {record.files.map((f) => (
            <li key={f.id}>
              <i className="fas fa-paperclip mr-2 text-stone-500" aria-hidden />
              {f.url ? <DocumentDownload name={f.filename} filename={f.filename} fetch={() => documentsApi.downloadFile(f.id)} /> : f.filename}
            </li>
          ))}
          {openRequests.map((r) => (
            <li key={`request-${r.id}`} className="text-stone-700">
              <i className="fas fa-file-circle-question mr-2 text-stone-500" aria-hidden />
              Requested by {r.label} · {r.state_label}
            </li>
          ))}
        </ul>
      </Section>
      {participants != null && (
        <Section title={`${participants.length} ${participants.length === 1 ? "participant" : "participants"}`}>
          {participants.length ? <ul className="flex flex-wrap gap-1.5">
            {participants.map((p) => <li key={p.id}><Person person={p} compact /></li>)}
          </ul> : <p className="text-small text-stone-600">None listed</p>}
        </Section>
      )}
    </div>
  );
}

function Section({ id, title, action, children }: { id?: string; title: string; action?: ReactNode; children: ReactNode }) {
  const headingId = useId();
  const heading = <h3 id={headingId} className="font-display text-base font-semibold text-stone-900">{title}</h3>;
  return (
    <section id={id} tabIndex={id ? -1 : undefined} aria-labelledby={headingId} className={cn("space-y-2 border-t border-stone-200 pt-4 first:border-0 first:pt-0", FOCUS_RING)}>
      {action ? <div className="flex items-center justify-between gap-2">{heading}{action}</div> : heading}
      {children}
    </section>
  );
}

function Fact({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return <><dt>{k}</dt><dd className={cn(strong && "font-semibold text-brand")}>{v}</dd></>;
}

/** Protected files need the API client's bearer header before a blob download. */
function DocumentDownload({ name, filename, fetch }: {
  name: string; filename: string; fetch: () => Promise<{ data: Blob }>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const download = async () => {
    setBusy(true);
    setError(false);
    try {
      const { data } = await fetch();
      downloadBlob(data, filename);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  return <>
    <button type="button" disabled={busy} aria-busy={busy} onClick={download}
      className={cn("review-control text-left text-brand hover:underline disabled:opacity-60", FOCUS_RING)}>
      {name}{busy && <span className="sr-only"> · Downloading</span>}
    </button>
    {error && <span role="alert" className="block text-small text-brand">Could not download {name}. Please try again.</span>}
  </>;
}

function affiliationText(values: string[] | null | undefined): string {
  return values == null ? "Not disclosed" : values.length ? values.join("; ") : "Not recorded";
}

function PartyReviewers({ row, ids, readable, people }: { row: TrackerPartyRow; ids: string; readable: boolean; people: PaperPerson[] }) {
  // The tracker sends only the withdrawn seats a Decision cut short, labelled so.
  const seats = row.seats ?? [];
  const outcome = row.outcome && row.outcome !== "pending" ? row.outcome_label : null;
  const unasked = UNASKED.has(row.state);
  return (
    <li id={detailsTarget(ids, row.party)} tabIndex={-1} className={cn("rounded", FOCUS_RING)}>
      <p className={cn("flex items-center gap-2 text-small font-semibold", unasked ? "text-stone-600" : "text-stone-900")}>
        <span>{row.label}</span>
        <span className="text-2xs font-normal text-stone-600">
          <i className={cn("fas mr-1", STATE_ICON[row.state] ?? "fa-circle")} aria-hidden />
          {[row.state_label, outcome, row.changes_requested ? "Changes requested" : null].filter(Boolean).join(" · ")}
        </span>
      </p>
      {row.in_pool ? (
        // The office, not a person: nobody holds a seat to show.
        <p className="mt-1 text-small text-stone-600"><i className="fas fa-users mr-2" aria-hidden />Nobody has claimed this yet</p>
      ) : readable && seats.length > 0 && (
        <ul aria-label={`Reviewing for ${row.label}`} className="mt-1 space-y-1">
          {seats.map((seat, i) => (
            <li key={i} className="flex items-center justify-between gap-2">
              <Person name={seat.reviewer_name ?? "A reviewer"} role={`${row.label} reviewer`}
                person={people.find((p) => p.id === seat.reviewer)} />
              <span className="text-2xs text-stone-600">
                <i className={cn("fas mr-1", (seat.verdict && VERDICT_ICON[seat.verdict]) ?? SEAT_ICON[seat.state])} aria-hidden />
                {seat.verdict_label ?? seat.state_label}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * The server decides which card fields are readable. Never reconstruct an
 * affiliation from classification or another person's card.
 */
function Person({ person, name = person?.name ?? "A reviewer", role = person?.role ?? null, compact }: {
  person?: PaperPerson; name?: string; role?: string | null; compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const cardId = useId();
  const [position, setPosition] = useState({ left: 16, top: 16 });
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");

  // The sidebar scrolls and participants wrap. Keep the card out of its
  // clipping ancestor and inside the viewport, including the last avatar.
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
        aria-label={compact ? name : undefined} title={compact ? name : undefined}
        onClick={() => setOpen((o) => !o)}
        className={cn("review-control inline-flex items-center gap-2 text-small text-stone-900 hover:underline", FOCUS_RING)}
      >
        <span aria-hidden className="review-avatar">{initials}</span>
        {!compact && name}
      </button>
      {open && createPortal(
        <div ref={card} id={cardId} role="dialog" aria-label={name} tabIndex={-1}
          style={position}
          className={cn("fixed z-50 w-56 max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-lg border border-stone-300 bg-overlay p-3 shadow-sm", FOCUS_RING)}>
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
