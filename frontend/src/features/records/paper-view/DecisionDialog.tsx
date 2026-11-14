import { useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/lib/errorDetail";
import { formatDate, joinLabels } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
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

/** RDCO's warnings: the executive Decision, and an embargo (ADR-047, ADR-052 §14). */
const WARNING_CALLOUT = "rounded-lg border border-stone-300 bg-surface p-3 text-small text-brand";

/**
 * Why RDCO isn't offered *Publish* (ADR-052 §14 as amended, IR-882): an
 * embargoed paper is never published, so it is released first.
 */
function embargoWarning(until: string | null): string {
  const dated = until ? ` until ${formatDate(until)}` : "";
  return (
    `This paper is under embargo${dated}, so it can't be published. To publish it, release the ` +
    "embargo first. Kept unlisted, its text stays away from outside AI companies."
  );
}

/**
 * The title and the consequence, stated before anyone commits to it
 * (ui-ux/16 §4). Only RDCO publishes a Thesis or Project (ADR-047 §5).
 */
function wording(outcome: DecisionOutcome, kind: string) {
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
  if (outcome === "publish") {
    return {
      title: `Publish this ${kind}?`,
      body:
        "This publishes it to Discover, where any signed-in user can read it and Ask IRIS can cite it.",
    };
  }
  if (outcome === "keep_unlisted") {
    return {
      title: "Accept and keep unlisted?",
      body:
        `This accepts the ${kind} without publishing it. It stays out of Discover and Ask IRIS, and its ` +
        "owners and reviewers can still open it. RDCO can publish it to Discover later, once its " +
        "embargo is released.",
    };
  }
  return {
    title: "Reject and archive?",
    body: `This archives the ${kind}. The owner cannot submit a new version; they would have to start a new submission.`,
  };
}

/** Each piece of open work deciding would end, as one line. */
export function closingLines(closes: DecisionCloses | null): string[] {
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
  for (const r of closes.revision_requests ?? []) lines.push(`Revision request #${r.id} from ${r.label}: ${r.reason}`);
  return lines;
}

/**
 *Accept & publish*, *Keep unlisted* or *Reject* by RDCO's reviewer, at any
 * time (ADR-047 §5); *Reject* by a Thesis or Project's Adviser, who accepts
 * by sending it to RDCO instead. On a Proposal, *Accept* or *Reject*, by its
 * Adviser alone (ADR-032 §2, IR-271).
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
  const userId = useAuthStore(s => s.user?.id);
  const [text, setText] = useState(() => readDecisionDraft(userId, record.id, outcome));
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const reject = outcome === "reject";
  const kind =
    record.record_type_name === "Project"
      ? "project"
      : record.record_type_name === "Proposal"
        ? "proposal"
        : "thesis";
  // An embargoed paper is never published, so `decide/` offers no publish for it
  // (ADR-052 §14 as amended). Keeping it unlisted says why, and what to do. A
  // Publish dialog an embargo overtook gets a 400, not the 409 below: `decide()`
  // refuses the outcome before it checks the token, so the reply carries the
  // embargo reason and no fresh `decision`, and the server refuses every retry.
  const embargo = flags.embargo && flags.embargo.state !== "released" ? flags.embargo : null;
  const warnEmbargo = embargo !== null && (outcome === "keep_unlisted" || outcome === "publish");
  const ready = (!reject || text.trim() !== "") && !(outcome === "publish" && embargo !== null);
  const { title, body } = wording(outcome, kind);
  const stillReviewing = (flags.closes?.assignments ?? []).map((a) => a.label);
  const withdrawsRevisions = (flags.closes?.revision_requests ?? []).length > 0;
  const closing = closingLines(flags.closes);

  const change = (value: string) => {
    setText(value);
    writeDecisionDraft(userId, record.id, outcome, value);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await recordsApi.decide(record.id, { outcome, comment: text.trim(), token: flags.token ?? "" });
      clearDecisionDrafts(userId, record.id);
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

        {flags.party === "rdco" && (stillReviewing.length > 0 || withdrawsRevisions) && (
          <p className={WARNING_CALLOUT}>
            <i className="fas fa-triangle-exclamation mr-1.5" aria-hidden />
            This is RDCO's executive Decision. RDCO doesn't have to wait.
            {stillReviewing.length > 0 &&
              ` ${joinLabels(stillReviewing)}'s open review${stillReviewing.length > 1 ? "s close" : " closes"}, marked "closed by RDCO's Decision"; their comments and findings stay in the history.`}
            {withdrawsRevisions && " Open revision requests are withdrawn."}
          </p>
        )}
        {warnEmbargo && (
          <section aria-label="Under embargo" className={WARNING_CALLOUT}>
            <i className="fas fa-lock mr-1.5" aria-hidden />
            {embargoWarning(embargo.until)}
          </section>
        )}
        {!!flags.closes?.findings?.length && <section aria-label="Recorded findings">
          <h3 className="text-small font-semibold">Recorded findings</h3>
          {flags.closes.findings.map((f, i) => <p key={i} className="text-small text-stone-700">{f.label}: {f.comment}</p>)}
        </section>}
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
