import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, downloadBlob, formatDate, joinLabels } from "@/lib/utils";
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

/** Where a Readiness link lands: a party's reviewers, Documents, or the facts themselves. */
export const detailsTarget = (ids: string, to: string) => `${ids}-details-${to}`;

/**
 * The review workspace's Details tab (ADR-032 §10 Amendment, IR-681; the
 * third column that repeated it is gone, IR-1094): Readiness's facts, then
 * Reviewers (one row per person, due dates on their line), Researchers,
 * Adviser, Classification (keywords as pills), Flagged by the authors,
 * Version, Documents, Participants and Copy link (IR-1193).
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
export function ReviewDetails({ record, tracker, ids, readiness, onReadinessAction, requestReview, addColleague, onAllDocuments, onCompare }: {
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
  addColleague?: ReactNode;
  /** Open the Documents drawer, which replaced the Files section (IR-879). */
  onAllDocuments?: () => void;
  /** Open the Changes tab, offered once there are two versions to compare. */
  onCompare?: () => void;
}) {
  const requestNoteId = useId();
  const readable = tracker.reviews !== null;
  const details = record.paper_details;
  const researchers = details?.researchers ?? [];
  // Review content (IR-681): shown on each party's line, never to a viewer who may not read the review.
  const dues = readable ? details?.due_dates : null;
  const flags = details?.author_flags ?? [];
  const versions = record.versions ?? [];
  const latest = versions[versions.length - 1];
  const openRequests = (tracker.document_requests ?? []).filter((r) => r.state === "open");
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
                due={dueFor(row.party)} revision={revisionFor(row.party)} />
            ))}
          </ul>
        )}
        {addColleague}
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
      <Section title="Version">
        {latest ? (
          <div className="space-y-1 text-small text-stone-700">
            <p><strong className="font-semibold text-stone-900">v{latest.number}</strong> · {latest.cause_label} · {formatDate(latest.created_at)}</p>
            <p className="text-stone-600">First sent {formatDate(versions[0].created_at)}</p>
            {onCompare && versions.length >= 2 && (
              <button type="button" onClick={onCompare}
                className={cn("review-control -mx-2 inline-flex items-center gap-2 font-semibold text-stone-900 hover:text-brand", FOCUS_RING)}>
                <i className="fas fa-clock-rotate-left text-stone-600" aria-hidden />
                Compare {versions.length} versions
              </button>
            )}
          </div>
        ) : <p className="text-small text-stone-600">{record.versions === null ? "Not disclosed" : "No version recorded"}</p>}
      </Section>
      <Section id={detailsTarget(ids, "documents")} title="Documents">
        <ul className="space-y-1.5 text-small text-stone-700">
          <li className="flex items-start gap-2"><i className="fas fa-file-lines mt-1 text-stone-500" aria-hidden />
            {(latest?.manuscript_url ?? record.abstract_file)
              ? <DocumentDownload name={`Manuscript${latest ? ` · v${latest.number}` : ""}`} filename="manuscript.pdf" strong
                fetch={() => latest?.manuscript_url
                  ? recordsApi.versionManuscriptBlob(record.id, latest.number)
                  : recordsApi.manuscriptBlob(record.id)} />
              : "No manuscript recorded"}
          </li>
          {/* The latest version's documents, and what arrived since (IR-872). */}
          {[...(latest?.documents ?? []), ...(latest?.documents_added ?? [])].map((d) => (
            <li key={`upload-${d.upload_id}`} className="flex items-start gap-2">
              <i className="fas fa-file-lines mt-1 text-stone-500" aria-hidden />
              <DocumentDownload name={`${d.slot} · v${d.version}`} filename={`${d.slot} v${d.version}.pdf`}
                fetch={() => documentsApi.downloadUpload(d.upload_id)} />
            </li>
          ))}
          {record.files.map((f) => (
            <li key={f.id} className="flex items-start gap-2">
              <i className="fas fa-file-lines mt-1 text-stone-500" aria-hidden />
              {f.url ? <DocumentDownload name={f.filename} filename={f.filename} fetch={() => documentsApi.downloadFile(f.id)} /> : f.filename}
            </li>
          ))}
          {openRequests.map((r) => (
            <li key={`request-${r.id}`} className="flex items-start gap-2">
              <i className="fas fa-file-circle-question mt-1 text-stone-500" aria-hidden />
              Requested by {r.label} · {r.state_label}
            </li>
          ))}
        </ul>
        {latest?.documents_reconstructed && (latest.documents?.length ?? 0) > 0 && (
          <p className="text-small text-stone-600">
            <i className="fas fa-circle-info mr-1.5" aria-hidden />
            v{latest.number} was submitted before IRIS kept each version&rsquo;s documents, so this list is a best guess.
          </p>
        )}
        {onAllDocuments && (
          <button type="button" onClick={onAllDocuments}
            className={cn("review-control -mx-2 text-small font-semibold text-stone-900 hover:text-brand", FOCUS_RING)}>
            All documents
          </button>
        )}
      </Section>
      {participants != null && (
        <Section title={`${participants.length} ${participants.length === 1 ? "participant" : "participants"}`}>
          {participants.length ? <ul className="flex flex-wrap gap-1.5">
            {participants.map((p) => <li key={p.id}><Person person={p} compact /></li>)}
          </ul> : <p className="text-small text-stone-600">None listed</p>}
        </Section>
      )}
      <CopyReviewLink recordId={record.id} />
    </div>
  );
}

/** The review's own address, for a colleague, as Share copies the paper's (IR-356). */
function CopyReviewLink({ recordId }: { recordId: number }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    let outcome: "copied" | "failed" = "copied";
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/records/${recordId}?section=review`);
    } catch {
      // No clipboard (plain http, or permission refused): say so, claim nothing.
      outcome = "failed";
    }
    setState(outcome);
    window.setTimeout(() => setState("idle"), 2500);
  };
  return (
    <div className="border-t border-stone-200 pt-4">
      <button type="button" onClick={copy}
        className={cn("review-control -mx-2 inline-flex items-center gap-2 text-small font-semibold text-stone-900 hover:text-brand", FOCUS_RING)}>
        <i className={cn("fas text-stone-600", state === "copied" ? "fa-check" : "fa-link")} aria-hidden />
        Copy link to this review
      </button>
      <p role="status" className="text-2xs text-stone-600">
        {state === "copied" ? "Link copied" : state === "failed" ? "Could not copy. The address bar has the link." : ""}
      </p>
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

/** Protected files need the API client's bearer header before a blob download. */
function DocumentDownload({ name, filename, fetch, strong }: {
  name: string; filename: string; fetch: () => Promise<{ data: Blob }>; strong?: boolean;
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
      className={cn("text-left hover:text-brand hover:underline disabled:opacity-60", strong && "font-semibold text-stone-900", FOCUS_RING)}>
      {name}{busy && <span className="sr-only"> · Downloading</span>}
    </button>
    {error && <span role="alert" className="block text-small text-brand">Could not download {name}. Please try again.</span>}
  </>;
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
function PartyReviewers({ row, ids, readable, people, due, revision }: {
  row: TrackerPartyRow; ids: string; readable: boolean; people: PaperPerson[];
  due?: PaperDueDate; revision?: TrackerResubmission;
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
        <span aria-hidden className="review-avatar review-avatar-brand">{initials}</span>
        {!compact && name}
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
