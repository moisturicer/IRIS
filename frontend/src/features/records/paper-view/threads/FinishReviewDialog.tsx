import { useEffect, useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { fieldClasses } from "@/components/ui/fieldClasses";
import type { Capability } from "@/features/records/capabilities";
import { errorDetail } from "@/lib/errorDetail";
import { cn } from "@/lib/utils";
import type { DecisionFlags, DocumentRequest, RecordDetail, ReviewComment, ReviewVerdict } from "@/types/records";

import { closingLines } from "../DecisionDialog";
import { plural, verdictOptions, type Thread } from "./threadModel";

export interface FinishReviewDialogProps {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  /** The viewer's draft threads: sent with the verdict, in one act. */
  drafts: ReviewComment[];
  /** The sent threads, so a Decision names each one it closes by its pin and quote. */
  sent?: Thread[];
  /** The verdict a footer button opened it on (IR-1139); *Comment only* otherwise. */
  initialVerdict?: ReviewVerdict;
  onClose: () => void;
  /** Finished: the sentence to announce. */
  onDone: (outcome: string) => void;
  /**
   * *Accept & send to RDCO* chooses its offices in the routing dialog, which
   * finishes the review with them; this hands it the summary.
   */
  onSendToRdco: (summary: string) => void;
}

const SUBMIT_WORDS: Record<ReviewVerdict, string> = {
  comment_only: "Send review",
  request_revision: "Request changes",
  send_to_rdco: "Choose offices…",
  cleared: "Clear",
  finding: "Record finding",
  accept: "Accept",
  publish: "Accept & publish",
  keep_unlisted: "Keep unlisted",
  reject: "Reject",
};

/** The verdicts that send the reviewer's drafted document requests (ADR-022 Amendment 9, IR-1325). */
const SENDS_DOCUMENT_REQUESTS: readonly ReviewVerdict[] = ["request_revision", "comment_only"];

const DONE_WORDS: Record<Exclude<ReviewVerdict, "send_to_rdco">, string> = {
  comment_only: "Review sent. The authors and the other reviewers have been told.",
  request_revision: "Changes requested. The authors have been notified.",
  cleared: "Cleared.",
  finding: "Finding recorded.",
  accept: "Accepted.",
  publish: "Accepted and published.",
  keep_unlisted: "Accepted and kept unlisted.",
  reject: "Rejected.",
};


/**
 * *Finish review* (ADR-032 §7, 2026-11-04; IR-875): the summary, then a
 * verdict, sent with the viewer's drafts in one act -- their draft comments
 * and the document requests they drafted in the Documents tab (ADR-022
 * Amendment 9, IR-1325). Only *Request changes* and *Comment only* send
 * document requests; every other verdict waits until they are removed. The verdicts are
 * `verdictOptions`' -- *Comment only* and what the capabilities grant -- and
 * one that is held says why. A Decision lists what it closes, the open
 * threads among them, and needs the summary as its reason while a *Must fix*
 * is open; its token is the server's, and a 409 brings the fresh one back so
 * the next press decides into the record as it now is.
 */
export function FinishReviewDialog({ record, can, drafts, sent = [], initialVerdict, onClose, onDone, onSendToRdco }: FinishReviewDialogProps) {
  const ids = useId();
  const [decision, setDecision] = useState<DecisionFlags>(record.decision);
  // The document requests this reviewer drafted, which go with the review (Amendment 9).
  const [asked, setAsked] = useState<DocumentRequest[]>([]);
  useEffect(() => {
    if (record.can_request_document.length === 0) return;
    let cancelled = false;
    recordsApi.documentRequests(record.id)
      .then(({ data }) => { if (!cancelled) setAsked(data.filter((r) => r.state === "draft")); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [record.id, record.can_request_document.length]);
  const askedNames = asked.flatMap((r) => r.items.map((i) => i.label));
  const waiting = asked.length > 0
    ? `You have ${plural(askedNames.length, "document request", "document requests")} waiting. Remove ${askedNames.length === 1 ? "it" : "them"} in the Documents tab first, or choose Request changes or Comment only.`
    : null;
  const options = verdictOptions(can, { ...record, decision }, drafts).map((o) =>
    waiting && o.unavailable === null && !SENDS_DOCUMENT_REQUESTS.includes(o.verdict) ? { ...o, unavailable: waiting } : o);
  // A footer button opens it on its own verdict, when that one is on offer and not held (IR-1139).
  const [verdict, setVerdict] = useState<ReviewVerdict>(() =>
    options.find((o) => o.verdict === initialVerdict && o.unavailable === null)?.verdict ?? "comment_only");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const chosen = options.find((o) => o.verdict === verdict) ?? options[0];
  // A verdict the drafted requests hold back falls back to Comment only, which sends them.
  useEffect(() => {
    if (chosen.unavailable !== null && chosen.verdict !== "comment_only") setVerdict("comment_only");
  }, [chosen.unavailable, chosen.verdict]);
  const mustFix = drafts.filter((d) => d.severity === "must_fix").length;

  const missingReason = chosen.reasonRequired && summary.trim() === "";
  const empty = chosen.verdict === "comment_only" && summary.trim() === "" && drafts.length === 0 && asked.length === 0;
  const ready = chosen.unavailable === null && !missingReason && !empty;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    if (chosen.verdict === "send_to_rdco") {
      onSendToRdco(summary.trim());
      return;
    }
    setError(null);
    setSending(true);
    try {
      await recordsApi.finishReview(record.id, {
        verdict: chosen.verdict,
        summary: summary.trim(),
        ...(chosen.decision ? { token: decision.token ?? "" } : {}),
      });
      onDone(DONE_WORDS[chosen.verdict as Exclude<ReviewVerdict, "send_to_rdco">]);
    } catch (err) {
      const response = (err as { response?: { status?: number; data?: { decision?: DecisionFlags } } })?.response;
      if (response?.status === 409 && response.data?.decision) setDecision(response.data.decision);
      setError(`${errorDetail(err, "Your review could not be sent. Please try again.")} Your summary and drafts are kept.`);
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const summaryId = `${ids}-summary`;
  const closing = chosen.decision ? closingLines(decision.closes) : [];
  const closingThreads = chosen.decision ? decision.closes?.threads ?? [] : [];
  const closingMustFix = closingThreads.filter((t) => t.severity === "must_fix");

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Finish your review"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={sending}>Keep reviewing</Button>
          <Button type="submit" form={formId} variant={chosen.verdict === "reject" ? "danger" : "primary"}
            disabled={!ready} loading={sending}>
            {SUBMIT_WORDS[chosen.verdict]}
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        {/* The decision first, then the summary, as the prototype's dialog
            reads (IR-1139): each option is "Label · what it does" on one line. */}
        <fieldset className="space-y-1">
          <legend className="mb-1.5 text-small font-semibold text-stone-900">Your decision</legend>
          {options.map((o) => {
            const descId = `${ids}-${o.verdict}-desc`;
            const nameId = `${ids}-${o.verdict}-name`;
            return (
              <label key={o.verdict} className={cn(
                "flex items-start gap-2.5 rounded-control px-1 py-1",
                o.unavailable ? "cursor-not-allowed text-stone-500" : "cursor-pointer",
              )}>
                <input type="radio" name={`${ids}-verdict`} value={o.verdict} checked={verdict === o.verdict}
                  disabled={o.unavailable !== null} onChange={() => setVerdict(o.verdict)}
                  aria-labelledby={nameId} aria-describedby={descId} className="mt-[3px] size-4 shrink-0 accent-brand" />
                <span className="text-small leading-snug text-stone-700">
                  <span id={nameId} className="font-semibold text-stone-900">{o.label}</span>
                  <span aria-hidden> · </span>
                  <span id={descId}>{o.unavailable ? `Unavailable: ${o.unavailable}` : o.description}</span>
                </span>
              </label>
            );
          })}
        </fieldset>


        <div>
          <label htmlFor={summaryId} className="mb-1.5 block text-small font-semibold text-stone-900">
            Summary{" "}
            <span className="font-normal text-stone-600">
              {chosen.reasonRequired ? "(required: it is this act's reason)" : "(what the authors and other reviewers read first)"}
            </span>
          </label>
          <textarea id={summaryId} rows={4} value={summary} onChange={(e) => setSummary(e.target.value)}
            aria-required={chosen.reasonRequired}
            className={fieldClasses(false)} />
          <p className="mt-1.5 text-2xs text-stone-600">
            {drafts.length
              ? `${plural(drafts.length, "draft comment", "draft comments")}${mustFix ? `, ${mustFix} Must fix,` : ""} will be sent with it.`
              : "No draft comments. You can still send a summary."}
          </p>
          {askedNames.length > 0 && (
            <p className="mt-1 text-2xs text-stone-600">
              {plural(askedNames.length, "document request", "document requests")} will be sent with it: {askedNames.join(", ")}.
            </p>
          )}
        </div>

        {(closing.length > 0 || closingThreads.length > 0) && (
          <section aria-label="What this Decision closes" className="rounded-control bg-stone-100 px-3 py-2 text-small text-stone-800 space-y-1">
            <p className="font-semibold">This Decision also closes</p>
            <ul className="list-disc pl-5">
              {closing.map((line) => <li key={line}>{line}</li>)}
              {closingThreads.length > 0 && (
                <li>
                  {plural(closingThreads.length, "open thread", "open threads")}
                  {closingMustFix.length ? `, ${closingMustFix.length} Must fix:` : ""}
                  {closingMustFix.length > 0 && (
                    <ul className="list-[circle] pl-5">
                      {closingMustFix.map((t) => <li key={t.id}>{closingName(t, sent)}</li>)}
                    </ul>
                  )}
                </li>
              )}
            </ul>
            {decision.reason_required && (
              <p>Your summary is the reason each open Must fix thread closes with.</p>
            )}
          </section>
        )}

        {error && <p role="alert" className="text-small text-brand">{error}</p>}
      </form>
    </Modal>
  );
}

/** A closing thread as the reviewer knows it: its pin, party and quote, where the Threads tab has it. */
function closingName(
  t: NonNullable<NonNullable<DecisionFlags["closes"]>["threads"]>[number],
  sent: Thread[],
): string {
  const known = sent.find((s) => s.root.id === t.id);
  // Its passage's quote, else its document (IR-1204), else where it sits.
  const document = known?.root.document?.label ?? t.document;
  const where = known?.root.anchor ? `: “${known.root.anchor.quote}”`
    : document ? `, on ${document}`
    : t.anchored ? ", on a passage" : ", on the record";
  return `${known ? `Thread ${known.pin}, ` : ""}${t.label}${where}`;
}
