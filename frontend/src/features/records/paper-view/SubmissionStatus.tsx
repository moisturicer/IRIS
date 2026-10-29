/**
 * The owner's own view of their submission, at the top of Overview (IR-625):
 * where the record is, what waits on them, and each version's history.
 *
 * Every word comes from `submitter_status`, which the server sends to an
 * owner only and which carries no reviewer's name or words. Why a party
 * asked is shown where it is answered: the revision banner and the
 * document-request panel below, which these links jump to.
 */
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import { WAITING_TARGET } from "../waitingOnYou";
import { focusFragmentTarget } from "./useFragmentFocus";

type Status = NonNullable<RecordDetail["submitter_status"]>;

export function SubmissionStatus({ status }: { status: Status }) {
  const waiting = status.waiting_on_you;
  return (
    <section
      aria-labelledby="submission-status-heading"
      className="rounded-2xl border border-stone-200 bg-surface p-4 space-y-4"
    >
      <div>
        <h2 id="submission-status-heading" className="text-sm font-bold text-stone-900">
          Your submission
        </h2>
        <p className="mt-1 text-body font-semibold text-stone-800">{status.line}</p>
      </div>

      {waiting.length > 0 && (
        <section
          aria-labelledby="waiting-on-you-heading"
          className="rounded-xl border border-brand-200 bg-brand-50 p-3"
        >
          <h3 id="waiting-on-you-heading" className="text-sm font-bold text-brand-dark">
            Waiting on you
          </h3>
          <ul className="mt-2 space-y-1.5">
            {waiting.map((item) => (
              <li key={`${item.kind}-${item.party}`} className="text-sm text-stone-800">
                {item.label} ·{" "}
                <a
                  href={`#${WAITING_TARGET[item.kind]}`}
                  // Focus in place rather than navigate: a hash change is a
                  // new history entry, which Paper View reads as an arrival.
                  onClick={(event) => {
                    if (focusFragmentTarget(WAITING_TARGET[item.kind])) event.preventDefault();
                  }}
                  className={cn("rounded-sm font-semibold text-brand underline underline-offset-2", FOCUS_RING)}
                >
                  {item.action_label}{" "}
                  <span className="sr-only">({item.label})</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      {status.history.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-stone-900">History</h3>
          <ol aria-label="Version history" className="mt-2 space-y-2">
            {status.history.map((version) => (
              <li key={version.number} className="text-sm text-stone-700">
                <span className="font-semibold text-stone-900">
                  v{version.number} · {version.cause_label}
                </span>
                {" "}· submitted {formatDate(version.submitted_at)}
                <span className="block text-stone-600">
                  {version.decisions.length > 0
                    ? version.decisions.map((d) => `${d.label}: ${d.verdict_label}`).join(" · ")
                    : "No decision yet"}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
