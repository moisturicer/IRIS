/**
 * Review threads, as the Threads tab reads them (ADR-032 §7, 2026-11-04;
 * IR-875). Pure: every fact here is the server's -- a comment's party,
 * severity, state, answer and `can_*` flags, and record detail's capability
 * and blocked flags. Nothing compares a role.
 */
import type { Capability } from "@/features/records/capabilities";
import type { DecisionOutcome, Party, RecordDetail, ReviewComment, ReviewVerdict, ThreadSeverity } from "@/types/records";

/** A top-level comment and its replies, with the pin it shows on the paper. */
export interface Thread {
  root:    ReviewComment;
  replies: ReviewComment[];
  /** "1", "2"... for a sent thread; "D1", "D2"... for one of the viewer's drafts. */
  pin:     string;
}

/**
 * The viewer's comments as threads: sent ones numbered in the order they were
 * sent, the viewer's own drafts apart. The server lists oldest first and never
 * sends another person's draft, so a draft here is always the viewer's.
 */
export function groupThreads(comments: readonly ReviewComment[]): { sent: Thread[]; drafts: Thread[] } {
  const replies = new Map<number, ReviewComment[]>();
  for (const c of comments) {
    if (c.reply_to === null) continue;
    replies.set(c.reply_to, [...(replies.get(c.reply_to) ?? []), c]);
  }
  const sent: Thread[] = [];
  const drafts: Thread[] = [];
  for (const c of comments) {
    if (c.reply_to !== null) continue;
    const list = c.is_draft ? drafts : sent;
    list.push({ root: c, replies: replies.get(c.id) ?? [], pin: `${c.is_draft ? "D" : ""}${list.length + 1}` });
  }
  return { sent, drafts };
}

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** A severity in words, wherever it is shown. */
export const SEVERITY_WORDS: Record<ThreadSeverity, string> = { must_fix: "Must fix", suggestion: "Suggestion" };

/** Open and sent: what still asks something of someone. */
export const isOpen = (t: Thread) => t.root.state === "open";

/** The Threads tab's count (ADR-032 §7): "2 must fix · 5 suggestions", a side left out at 0, "" when none is open. */
export function countLabel(sent: readonly Thread[]): string {
  const open = sent.filter(isOpen);
  const mustFix = open.filter((t) => t.root.severity === "must_fix").length;
  const suggestions = open.filter((t) => t.root.severity === "suggestion").length;
  return [
    mustFix ? `${mustFix} must fix` : "",
    suggestions ? plural(suggestions, "suggestion", "suggestions") : "",
  ].filter(Boolean).join(" · ");
}

/**
 * Where a thread stands, in words: Resolved, Closed by Decision, or -- for an
 * open reviewer's thread -- the owner's answer or "No answer". An open thread
 * of the authors' own has no answer to wait for, so null.
 */
export function threadStatus(root: ReviewComment): string | null {
  if (root.state === "resolved") return "Resolved";
  if (root.state === "closed") return "Closed by Decision";
  if (root.answer) return root.answer.kind === "addressed" ? "Addressed" : "Declined";
  return root.party ? "No answer" : null;
}

export type ThreadFilter = "open" | "yours" | "resolved" | "all";

/**
 * Who "Yours" means: what the viewer wrote, and their party's threads -- the
 * party record detail says they review as (`revision.party`), since a thread
 * belongs to its party, not its writer (ADR-032 §7).
 */
export interface ThreadViewer {
  userId: number | null;
  party:  Party | null;
}

export function filterThreads(sent: readonly Thread[], filter: ThreadFilter, viewer: ThreadViewer): Thread[] {
  switch (filter) {
    case "open":
      return sent.filter(isOpen);
    case "resolved":
      return sent.filter((t) => t.root.state === "resolved" || t.root.state === "closed");
    case "yours":
      return sent.filter((t) =>
        (viewer.userId !== null && t.root.author === viewer.userId) ||
        (viewer.party !== null && t.root.party === viewer.party));
    default:
      return [...sent];
  }
}

/** What the Finish dialog reads of record detail: the server's flags, nothing else. */
export type VerdictFlags = Pick<RecordDetail, "revision" | "routing" | "office_review" | "decision">;

export interface VerdictOption {
  verdict:        ReviewVerdict;
  label:          string;
  description:    string;
  /** Why it can't be taken now, in the server's words where it has them; null when it can. */
  unavailable:    string | null;
  /** The summary is this act's reason, and must be written. */
  reasonRequired: boolean;
  /** A Decision: it closes what `decision.closes` lists, and carries the token. */
  decision:       boolean;
}

/** `finish_review.py` refuses this before anything is written, in these words. */
const OWN_MUST_FIX =
  "You can't approve while sending a Must fix comment. Change it to Suggestion, or request a revision.";


/**
 * The Finish dialog's verdicts (ADR-032 §7): *Comment only*, then each act
 * the viewer's capabilities already grant, in one order for everyone,
 * approvals first and *Reject* last. Finishing grants nothing: a verdict not
 * granted is not offered, and one granted but held says why -- the server's
 * reason, or the refusal `finish-review/` itself would give.
 */
export function verdictOptions(
  can: ReadonlySet<Capability>,
  flags: VerdictFlags,
  drafts: readonly ReviewComment[],
): VerdictOption[] {
  if (!can.has("finish_review")) return [];
  const ownMustFix = drafts.some((d) => d.severity === "must_fix") ? OWN_MUST_FIX : null;
  const decision = flags.decision;
  const decisionHeld = (outcome: DecisionOutcome) =>
    decision.blocked ?? decision.blocked_outcomes?.[outcome] ?? null;
  const decisionNeedsReason = Boolean(decision.reason_required);
  const options: VerdictOption[] = [{
    verdict: "comment_only", label: "Comment only",
    description: "Send your drafts and a summary. Your review stays open.",
    unavailable: null, reasonRequired: false, decision: false,
  }];
  const add = (o: Omit<VerdictOption, "decision"> & { decision?: boolean }) =>
    options.push({ decision: false, ...o });

  if (can.has("accept_proposal")) add({
    verdict: "accept", label: "Accept", description: "Accepts the Proposal. The authors may continue it as a thesis.",
    unavailable: decisionHeld("accept") ?? ownMustFix, reasonRequired: decisionNeedsReason, decision: true,
  });
  if (can.has("accept_publish")) add({
    verdict: "publish", label: "Accept & publish", description: "Publishes the record to Discover.",
    unavailable: decisionHeld("publish"), reasonRequired: decisionNeedsReason, decision: true,
  });
  if (can.has("keep_unlisted")) add({
    verdict: "keep_unlisted", label: "Keep unlisted",
    description: "Accepted, but kept out of Discover and Ask IRIS.",
    unavailable: decisionHeld("keep_unlisted"), reasonRequired: decisionNeedsReason, decision: true,
  });
  if (can.has("send_to_rdco")) add({
    verdict: "send_to_rdco", label: "Accept & send to RDCO",
    description: "Accept, and ask RDCO to review. You choose the offices to suggest next.",
    unavailable: flags.revision.decision_blocked ?? flags.routing.send_to_rdco_blocked ?? ownMustFix,
    reasonRequired: true,
  });
  if (can.has("office_review")) {
    add({
      verdict: "cleared", label: `Clear for ${flags.office_review.label ?? "your office"}`,
      description: "Your office's question is settled for this version.",
      unavailable: flags.office_review.blocked ?? flags.office_review.clear_blocked ?? ownMustFix,
      reasonRequired: false,
    });
    add({
      verdict: "finding", label: "Record a finding", description: "A reasoned concern. It goes to RDCO, which decides.",
      unavailable: flags.office_review.blocked, reasonRequired: true,
    });
  }
  if (can.has("request_revision") || can.has("withdraw_revision")) add({
    verdict: "request_revision", label: "Request revision",
    description: "The authors revise and submit the next version.",
    unavailable: can.has("request_revision")
      ? flags.revision.blocked
      : "Your revision request is already open. Withdraw it to ask again.",
    reasonRequired: true,
  });
  if (can.has("reject")) add({
    verdict: "reject", label: "Reject", description: "Ends the review. The authors must submit a new record.",
    unavailable: decisionHeld("reject"), reasonRequired: true, decision: true,
  });
  return options;
}

