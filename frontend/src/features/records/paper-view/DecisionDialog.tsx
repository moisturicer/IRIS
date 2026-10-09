import { useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/features/document-requests/errorDetail";
import type { DecisionCloses, DecisionFlags, DecisionOutcome, RecordDetail } from "@/types/records";

import { clearDecisionDrafts, readDecisionDraft, writeDecisionDraft } from "./decisionDraft";

interface DecisionDialogProps {
  record: RecordDetail;
  outcome: DecisionOutcome;
  onClose: () => void;
  /** Decided: the sentence the bar announces. */
  onDone: (outcome: string) => void;
}

/** What each outcome's confirm button says, and what the bar announces after. */
const CONFIRM: Record<DecisionOutcome, { label: string; done: string }> = {
  accept: { label: "Accept", done: "Accepted. The proposal leaves review." },
  publish: { label: "Publish", done: "Published. It is now in Discover." },
  keep_unlisted: { label: "Keep unlisted", done: "Accepted and kept unlisted." },
  reject: { label: "Reject and archive", done: "Rejected. The record is archived." },
};

/**
 * The title and the consequence, stated before anyone commits to it
 * (ui-ux/16 §4; spec §7.3 item 1 for the Adviser's publish).
 */
function wording(outcome: DecisionOutcome, adviser: boolean, kind: string) {
  if (outcome === "accept") {
    // IR-271: promises nothing about continuing it as a Thesis or Project,
    // which IRIS does not offer yet (IR-417).
    return {
      title: "Accept this proposal?",
      body:
        "This accepts the proposal. It leaves review and is not published to Discover; " +
        "its owners keep it as an accepted proposal.",
    };
  }
  if (outcome === "reject" && kind === "proposal") {
    return {
      title: "Reject and archive?",
      body: "This archives the proposal. The student will need to submit a new one.",
    };
  }
  if (outcome === "publish" && adviser) {
    return {
      title: "Publish without specialist review?",
      body: `This publishes the ${kind} to Discover. No office will review it.`,
    };
  }
  if (outcome === "publish") {
    return {
      title: `Publish this ${kind}?`,
      body: "This publishes it to Discover, where any signed-in user can read it and Ask IRIS can cite it.",
    };
  }
  if (outcome === "keep_unlisted") {
    return {
      title: "Accept and keep unlisted?",
      body:
        `This accepts the ${kind} without publishing it. It stays out of Discover and Ask IRIS, and its ` +
        "owners and reviewers can still open it. Publishing it later is not yet possible in IRIS.",
    };
  }
  return {
    title: "Reject and archive?",
    body: `This archives the ${kind}. The owner cannot submit a new version; they would have to start a new submission.`,
  };
}

/** Each piece of open work deciding would end, as one line. */
function closingLines(closes: DecisionCloses | null): string[] {
  if (!closes) return [];
  const lines = closes.assignments.map((a) =>
    a.holders.length > 0
      ? `${a.label}'s review in progress (${a.holders.join(", ")})`
      : `${a.label}'s review, not yet claimed`,
  );
  if (closes.document_requests > 0) {
    lines.push(
      closes.document_requests === 1
        ? "1 open document request"
        : `${closes.document_requests} open document requests`,
    );
  }
  return lines;
}

/**
 * *Accept & publish*, *Keep unlisted* or *Reject* (ADR-032 §3, IR-270): the
 * Adviser on a record no office was asked to review, or RDCO's reviewer on
 * the specialist path. On a Proposal, *Accept* or *Reject*, by its Adviser
 * alone (ADR-032 §2, IR-271).
 *
 * It says what follows and what it closes -- every other review still open,
 * and every open document request -- before anyone commits. A rejection
 * needs its reason, which the owner reads as written; both accepts take an
 * optional comment.
 *
 * **Never decides into a changed record** (IR-143's carried criteria). The
 * dialog sends the server's `decision.token`. If the record moved while the
 * dialog was open, the server refuses with a 409 and the fresh `decision`;
 * the dialog then shows what deciding would close now, keeps the typed text,
 * and decides only when the decider presses again, with the new token.
 * The text is also kept in the tab's session as it is typed, so closing the
 * dialog to read the paper loses nothing.
 */
export function DecisionDialog({ record, outcome, onClose, onDone }: DecisionDialogProps) {
  const ids = useId();
  const [flags, setFlags] = useState<DecisionFlags>(record.decision);
  const [text, setText] = useState(() => readDecisionDraft(record.id, outcome));
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const reject = outcome === "reject";
  const ready = !reject || text.trim() !== "";
  const kind =
    record.record_type_name === "Project"
      ? "project"
      : record.record_type_name === "Proposal"
        ? "proposal"
        : "thesis";
  const { title, body } = wording(outcome, flags.party === "adviser", kind);
  const closing = closingLines(flags.closes);

  const change = (value: string) => {
    setText(value);
    writeDecisionDraft(record.id, outcome, value);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await recordsApi.decide(record.id, { outcome, comment: text.trim(), token: flags.token ?? "" });
      clearDecisionDrafts(record.id);
      onDone(CONFIRM[outcome].done);
    } catch (err) {
      const fresh = (err as { response?: { status?: number; data?: { decision?: DecisionFlags } } })
        ?.response;
      if (fresh?.status === 409 && fresh.data?.decision) setFlags(fresh.data.decision);
      const kept = reject ? "Your reason is kept." : "Your comment is kept.";
      setError(`${errorDetail(err, "The decision could not be recorded. Please try again.")} ${kept}`);
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const textId = `${ids}-text`;
  const helpId = `${textId}-help`;
  const hintsId = `${ids}-hints`;
  const closesId = `${ids}-closes`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title={title}
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button
            type="submit"
            form={formId}
            variant={reject ? "danger" : "primary"}
            disabled={!ready}
            loading={sending}
          >
            {CONFIRM[outcome].label}
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-[14px] text-stone-700 leading-relaxed">{body}</p>

        {flags.author_hints.length > 0 && (
          <div>
            <p id={hintsId} className="text-[13px] font-semibold text-stone-900">
              The author flagged
            </p>
            <ul aria-labelledby={hintsId} className="mt-1 list-disc pl-5 text-[13px] text-stone-700">
              {flags.author_hints.map((hint) => (
                <li key={hint}>{hint}</li>
              ))}
            </ul>
          </div>
        )}

        {closing.length > 0 && (
          <div>
            <p id={closesId} className="text-[13px] font-semibold text-stone-900">
              This also closes
            </p>
            <ul aria-labelledby={closesId} className="mt-1 list-disc pl-5 text-[13px] text-stone-700">
              {closing.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <label htmlFor={textId} className={LABEL}>
            {reject ? "Why is it rejected?" : "Comment (optional)"}
          </label>
          <textarea
            id={textId}
            required={reject}
            rows={4}
            value={text}
            onChange={(e) => change(e.target.value)}
            aria-describedby={helpId}
            className={fieldClasses(false)}
          />
          <p id={helpId} className="mt-1 text-[13px] text-stone-600">
            {reject
              ? "The owner reads this as written."
              : "If you add one, the owner and the reviewers see it with the record."}
          </p>
        </div>

        {error && (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
