import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { STARTER_KINDS } from "./askStarters";

/**
 * Questions to start from (IR-1306): an index of what Ask IRIS answers well.
 * Each is a row with its kind above the question, two to a row once the
 * box has room, divided by hairlines rather than boxed as cards. Hovering
 * washes it in the binding maroon and draws the arrow in from the margin.
 */
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
    <div className={cn("[container-type:inline-size] [container-name:starters]", className)}>
      <div role="group" aria-label="Suggested questions"
        className="grid grid-cols-1 gap-x-3 border-t border-stone-200 text-left starters-wide:grid-cols-2">
        {questions.map((question, index) => {
          const label = STARTER_KINDS[question];
          return <button
            key={question}
            type="button"
            onClick={() => onChoose(question)}
            style={{ animationDelay: `${Math.min(index, 4) * 60}ms` }}
            className={cn(
              "group relative -mx-1 flex min-h-11 items-start gap-3 rounded-control border-b border-stone-200 px-3 py-3 text-left",
              "hover:border-transparent hover:bg-brand/[0.06]",
              "motion-safe:animate-fade-in-up motion-safe:[animation-fill-mode:backwards]",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            {label && <span aria-hidden className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-control bg-stone-100 text-brand
              transition-colors duration-150 group-hover:bg-brand group-hover:text-white">
              <i className={cn("fas text-label", label.icon)} />
            </span>}
            <span className="min-w-0 flex-1">
              {label && <span aria-hidden className="block text-label font-medium text-stone-500">{label.kind}</span>}
              <span className="block text-body text-stone-800 group-hover:text-brand-dark">{question}</span>
            </span>
            <i aria-hidden className="fas fa-arrow-right mt-1.5 shrink-0 text-xs text-transparent transition-[color,transform] duration-200
              ease-[cubic-bezier(0.22,1,0.36,1)] -translate-x-1 group-hover:translate-x-0 group-hover:text-brand
              group-focus-visible:translate-x-0 group-focus-visible:text-brand motion-reduce:transition-none" />
          </button>;
        })}
      </div>
    </div>
  );
}
