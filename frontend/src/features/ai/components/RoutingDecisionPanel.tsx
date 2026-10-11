import type { ChatLane, RoutingDecision } from "@/types/ai";

const LABELS: Record<ChatLane, string> = {
  passage: "Passages", listing: "List papers", count: "Count papers",
  comparison: "Compare papers", research: "Research", landscape: "Research landscape",
};

const REASONS: Record<string, string> = {
  confident: "IRIS selected this approach to match the kind of answer your question asks for.",
  backup_failed: "IRIS could not reliably choose an answer approach, so it is using passages from readable papers.",
  question_injection: "Your question contains instructions that may redirect IRIS, so the answer is restricted to passages.",
  jev_disabled: "IRIS used its available question classifier to choose this approach.",
  jev_uncertain: "The first classification was uncertain; a second check selected this approach.",
  decisionunavailable: "The first classification was unavailable; a second check selected this approach.",
  decisionmalformed: "The first classification could not be used; a second check selected this approach.",
};

export function RoutingDecisionPanel({ decision, onOverride, disabled = false }: {
  decision: RoutingDecision;
  onOverride?: (lane: ChatLane) => void;
  disabled?: boolean;
}) {
  const alternatives = decision.allowed_overrides.filter((lane) => lane !== decision.lane);
  const scopeRestricted = !decision.injection_flagged && decision.allowed_overrides.length === 1 && decision.allowed_overrides[0] === "passage";
  return (
    <div className="mt-2 text-xs text-stone-600 space-y-1.5" aria-label="Answer routing">
      <p>Answer approach: <strong>{LABELS[decision.lane]}</strong>
        {decision.override_applied && " · Your choice"}
      </p>
      <details>
        <summary className="cursor-pointer hover:text-brand">Why this approach?</summary>
        <p className="mt-1">{REASONS[decision.reason] ?? "IRIS selected this approach based on your question and the answer approaches available."}</p>
        {decision.lane === "landscape" && <p>A research landscape or gap analysis is not available yet. Passages alone cannot establish complete coverage of a field.</p>}
        {scopeRestricted && <p>This answer stays within the current paper. Other answer approaches are unavailable in this scope.</p>}
        {decision.injection_flagged && <p>Only passage answers are available because the question could not be safely cleared for other approaches.</p>}
      </details>
      {onOverride && alternatives.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5" aria-label="Rerun answer">
          <span>Try instead:</span>
          {alternatives.map((lane) => (
            <button key={lane} type="button" disabled={disabled}
              onClick={() => onOverride(lane)}
              className="rounded-full border border-stone-200 px-2.5 py-1 hover:border-brand/40 hover:text-brand disabled:opacity-40"
              aria-label={`Rerun with ${LABELS[lane]}`}>
              {LABELS[lane]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
