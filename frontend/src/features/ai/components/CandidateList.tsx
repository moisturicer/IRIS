import { Link } from "react-router-dom";
import type { AnswerListing, CandidateRow, CandidateState } from "@/types/ai";
import { cn } from "@/lib/utils";
import { CheckIcon, CloseIcon, OutlineIcon, QuestionIcon, SpinnerIcon, WarningIcon } from "./AskIrisIcons";

/** What each state says, in words: colour and icons never carry it alone (IR-546). */
export const STATE_LABEL: Record<CandidateState, string> = {
  pending: "Relevance pending",
  included: "Matches",
  excluded: "Does not match",
  uncertain: "Uncertain",
  unassessed: "Could not be assessed",
};

const STATE_ICON: Record<CandidateState, { Icon: OutlineIcon; tone: string }> = {
  pending: { Icon: SpinnerIcon, tone: "animate-spin motion-reduce:animate-none text-stone-400" },
  included: { Icon: CheckIcon, tone: "text-brand" },
  excluded: { Icon: CloseIcon, tone: "text-stone-400" },
  uncertain: { Icon: QuestionIcon, tone: "text-stone-500" },
  unassessed: { Icon: WarningIcon, tone: "text-stone-500" },
};

export function candidateHref(row: CandidateRow): string {
  const page = row.source?.field === "passage" ? row.source.page : null;
  return `/records/${row.record_id}${page ? `?page=${page}` : ""}`;
}

function Item({ row }: { row: CandidateRow }) {
  const label = STATE_LABEL[row.state];
  const { Icon, tone } = STATE_ICON[row.state];
  return (
    <li className="flex items-baseline gap-2 text-control">
      <Icon inline className={cn("self-center", tone)} />
      <span className="min-w-0">
        <Link to={candidateHref(row)} className="text-brand hover:underline">
          {row.restricted ? "A paper IRIS may not read" : row.title}
        </Link>
        <span className="text-small text-stone-500"> · {label}</span>
        {row.quote && (
          <q className="block text-small italic text-stone-500">{row.quote}</q>
        )}
      </span>
    </li>
  );
}

/**
 * The candidates while they are screened (IR-546): each paper appears at once
 * as "Relevance pending" and moves to its state by record id, so a repeat or a
 * reconnect never adds a card. Names and states only -- no model text. How
 * many are checked is said by the stream's one live line, not here (IR-570).
 */
export function LiveCandidates({ candidates, compact = false }: { candidates: CandidateRow[]; compact?: boolean }) {
  if (candidates.length === 0) return null;
  return (
    <section aria-label="Candidate papers" className={compact ? "mt-1 mb-2" : "mt-1 mb-3"}>
      <p className="text-small font-medium text-stone-500">Candidate papers</p>
      <ul aria-label="Candidates" className="mt-1.5 space-y-1">
        {candidates.map((row) => (
          <Item key={row.record_id} row={row} />
        ))}
      </ul>
    </section>
  );
}

/** A finished listing: the matches first, every other candidate behind a disclosure. */
export function CandidateList({ listing }: { listing: AnswerListing }) {
  const rows = listing.candidates ?? [];
  const matches = rows.filter((row) => row.state === "included");
  const others = rows.filter((row) => row.state !== "included");
  return (
    <div className="mt-3">
      <p className="text-control text-stone-600">{listing.wording}</p>
      {matches.length > 0 && (
        <ul aria-label="Matching papers" className="mt-2 space-y-1">
          {matches.map((row) => (
            <Item key={row.record_id} row={row} />
          ))}
        </ul>
      )}
      {others.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-small font-medium text-stone-500 hover:text-stone-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 rounded-control">
            {`Other candidates (${others.length})`}
          </summary>
          <ul aria-label="Other candidates" className="mt-1.5 space-y-1">
            {others.map((row) => (
              <Item key={row.record_id} row={row} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
