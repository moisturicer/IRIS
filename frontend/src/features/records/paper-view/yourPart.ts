import type { Readiness, ReadinessItem, ReadinessVerdict, ReviewerSeat } from "@/types/records";

/** A glyph beside the server's verdict, never instead of it. */
export const VERDICT_ICON: Record<ReadinessVerdict, string> = {
  ready: "fa-circle-check",
  blocked: "fa-circle-xmark",
  waiting_on_you: "fa-circle-exclamation",
  none: "fa-circle-info",
};

/**
 * Facts that only restate a party's status. Details' Reviewers says it once
 * (IR-1094, audit US-17), so neither the footer's line nor the facts listed
 * under Details repeat it.
 */
const PARTY_STATUS_KINDS: ReadonlySet<string> = new Set(["party_reviewing", "pool_unclaimed"]);

/** What Readiness says beyond a party's own status, blockers first as the server sorts them. */
export function readinessFacts(readiness: Readiness | null | undefined): ReadinessItem[] {
  return (readiness?.items ?? []).filter((i) => !PARTY_STATUS_KINDS.has(i.kind));
}

export interface YourPart {
  /** One heading: the server's headline, or a finished review's verdict. */
  heading: string;
  /** One line under it, or null: the most severe fact, with any drafts held. */
  line: string | null;
  icon: string;
}

/**
 * The "Your part" footer's words (IR-1094; spec §4.8). Every string is the
 * server's -- its headline, a fact's label, the seat's own verdict or state --
 * apart from the count of drafts the viewer holds. The browser words no
 * verdict, no blocker and no status sentence (ADR-032 §10 Amendment, IR-681).
 *
 * A finished review shows its verdict, not "This record is not in review."
 * beside a warning (audit WF-07).
 */
export function yourPartSummary({ readiness, seat, draftCount }: {
  readiness: Readiness | null | undefined;
  seat: ReviewerSeat | undefined;
  draftCount: number;
}): YourPart {
  const drafts = draftCount > 0 ? `${draftCount} draft comment${draftCount === 1 ? "" : "s"}, not sent` : null;
  const seatWords = seat?.verdict_label ?? seat?.state_label ?? "No verdict recorded";

  if (seat?.state === "done") {
    return { heading: `Your review: ${seatWords}`, line: null, icon: "fa-circle-check" };
  }
  if (!readiness) {
    return { heading: `Your review: ${seatWords}`, line: drafts, icon: "fa-circle-info" };
  }
  const facts = readinessFacts(readiness);
  const blocker = facts.find((f) => f.severity === "blocker");
  return {
    heading: readiness.headline,
    // The most severe fact, and the drafts the viewer holds beside it; else
    // whichever there is. The facts' own sort puts a blocker first.
    line: blocker ? [blocker.label, drafts].filter(Boolean).join(" · ") : drafts ?? facts[0]?.label ?? null,
    icon: VERDICT_ICON[readiness.verdict],
  };
}
