import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

/** Questions to start from, as a hairline list rather than a grid of cards. */
export function StarterQuestions({
  questions,
  onChoose,
  className,
}: {
  questions: readonly string[];
  onChoose: (question: string) => void;
  className?: string;
}) {
  return (
    <div role="group" aria-label="Suggested questions" className={cn("divide-y divide-stone-200 text-left", className)}>
      {questions.map((question, index) => (
        <button
          key={question}
          type="button"
          onClick={() => onChoose(question)}
          style={{ animationDelay: `${Math.min(index, 4) * 50}ms` }}
          className={cn(
            "group flex min-h-11 w-full items-center justify-between gap-3 py-2.5 text-left text-small text-stone-700 hover:text-brand",
            "motion-safe:animate-fade-in-up motion-safe:[animation-fill-mode:backwards]",
            COLOUR_TRANSITION,
            FOCUS_RING,
          )}
        >
          <span>{question}</span>
          <i
            aria-hidden
            className="fas fa-arrow-right shrink-0 text-xs text-stone-400 transition-[color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:translate-x-0.5 group-hover:text-brand motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
          />
        </button>
      ))}
    </div>
  );
}
