import { useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import type { Capability } from "@/features/records/capabilities";
import { errorDetail } from "@/lib/errorDetail";
import { cn } from "@/lib/utils";
import type { DecisionFlags, RecordDetail, ReviewComment, ReviewVerdict } from "@/types/records";

import { closingLines } from "../DecisionDialog";
import { plural, verdictOptions, type Thread } from "./threadModel";
import { SELECTED } from "@/components/ui/highlightRoles";

export interface FinishReviewDialogProps {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  /** The viewer's draft threads: sent with the verdict, in one act. */
  drafts: ReviewComment[];
  /** The sent threads, so a Decision names each one it closes by its pin and quote. */
  sent?: Thread[];
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
  request_revision: "Request revision",
  send_to_rdco: "Choose offices…",
  cleared: "Clear",
  finding: "Record finding",
  accept: "Accept",
  publish: "Accept & publish",
  keep_unlisted: "Keep unlisted",
  reject: "Reject",
};

const DONE_WORDS: Record<Exclude<ReviewVerdict, "send_to_rdco">, string> = {
  comment_only: "Review sent. The authors and the other reviewers have been told.",
  request_revision: "Revision requested. The owner has been notified.",
  cleared: "Cleared.",
  finding: "Finding recorded.",
  accept: "Accepted.",
  publish: "Accepted and published.",
  keep_unlisted: "Accepted and kept unlisted.",
  reject: "Rejected.",
};


/**
 * *Finish review* (ADR-032 §7, 2026-11-04; IR-875): the summary, then a
 * verdict, sent with the viewer's drafts in one act. The verdicts are
 * `verdictOptions`' -- *Comment only* and what the capabilities grant -- and
 * one that is held says why. A Decision lists what it closes, the open
 * threads among them, and needs the summary as its reason while a *Must fix*
 * is open; its token is the server's, and a 409 brings the fresh one back so
 * the next press decides into the record as it now is.
 */
export function FinishReviewDialog({ record, can, drafts, sent = [], onClose, onDone, onSendToRdco }: FinishReviewDialogProps) {
  const ids = useId();
  const [decision, setDecision] = useState<DecisionFlags>(record.decision);
  const options = verdictOptions(can, { ...record, decision }, drafts);
  const [verdict, setVerdict] = useState<ReviewVerdict>("comment_only");
  const [summary, setSummary] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const chosen = options.find((o) => o.verdict === verdict) ?? options[0];
  const mustFix = drafts.filter((d) => d.severity === "must_fix").length;

  const missingReason = chosen.reasonRequired && summary.trim() === "";
  const empty = chosen.verdict === "comment_only" && summary.trim() === "" && drafts.length === 0;
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
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>Keep reviewing</Button>
          <Button type="submit" form={formId} variant={chosen.verdict === "reject" ? "danger" : "primary"}
            disabled={!ready} loading={sending}>
            {SUBMIT_WORDS[chosen.verdict]}
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <p className="text-[14px] text-stone-700">
          {drafts.length
            ? `${plural(drafts.length, "draft comment", "draft comments")}${mustFix ? `, ${mustFix} Must fix,` : ""} will be sent with it.`
            : "No draft comments. You can still send a summary."}
        </p>

        <div>
          <label htmlFor={summaryId} className={LABEL}>
            Summary{chosen.reasonRequired ? " (required: it is this act's reason)" : ""}
          </label>
          <textarea id={summaryId} rows={4} value={summary} onChange={(e) => setSummary(e.target.value)}
            aria-required={chosen.reasonRequired}
            placeholder="What the authors and the other reviewers read first"
            className={fieldClasses(false)} />
        </div>

        <fieldset className="space-y-1.5">
          <legend className="text-[14px] font-medium text-stone-700 mb-1">Verdict</legend>
          {options.map((o) => {
            const descId = `${ids}-${o.verdict}-desc`;
            const nameId = `${ids}-${o.verdict}-name`;
            return (
              <label key={o.verdict} className={cn(
                "flex items-start gap-2.5 rounded-lg border px-3 py-2",
                verdict === o.verdict ? SELECTED : "border-stone-200",
                o.unavailable && "opacity-70",
              )}>
                <input type="radio" name={`${ids}-verdict`} value={o.verdict} checked={verdict === o.verdict}
                  disabled={o.unavailable !== null} onChange={() => setVerdict(o.verdict)}
                  aria-labelledby={nameId} aria-describedby={descId} className="mt-1 accent-brand" />
                <span>
                  <span id={nameId} className="block text-small font-semibold text-stone-900">{o.label}</span>
                  <span id={descId} className="block text-2xs text-stone-600">
                    {o.unavailable ? `Unavailable: ${o.unavailable}` : o.description}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>

        {(closing.length > 0 || closingThreads.length > 0) && (
          <section aria-label="What this Decision closes" className="rounded-lg bg-stone-100 px-3 py-2 text-[13px] text-stone-800 space-y-1">
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
  const where = known?.root.anchor ? `: “${known.root.anchor.quote}”` : t.anchored ? ", on a passage" : ", on the record";
  return `${known ? `Thread ${known.pin}, ` : ""}${t.label}${where}`;
}
