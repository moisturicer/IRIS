import { useEffect, useState } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { RepositorySearchIcon } from "./DiscoverIcons";

interface DiscoverSearchComposerProps {
  value: string;
  onChange: (value: string) => void;
}

const EXAMPLES = [
  "What research explores flood resilience in Cebu?",
  "How can AI support learning at CIT-U?",
  "What studies explore renewable energy for local communities?",
  "How can technology make transport more accessible?",
];

/** A compact catalogue search with rotating examples while it is empty. */
export function DiscoverSearchComposer({ value, onChange }: DiscoverSearchComposerProps) {
  const [example, setExample] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let interval: ReturnType<typeof setInterval> | undefined;
    let transition: ReturnType<typeof setTimeout> | undefined;
    const stop = () => {
      clearInterval(interval);
      clearTimeout(transition);
    };
    const start = () => {
      stop();
      setVisible(true);
      if (value || preference?.matches) return;
      interval = setInterval(() => {
        setVisible(false);
        transition = setTimeout(() => {
          setExample((current) => (current + 1) % EXAMPLES.length);
          setVisible(true);
        }, 180);
      }, 3600);
    };
    start();
    preference?.addEventListener("change", start);
    return () => {
      stop();
      preference?.removeEventListener("change", start);
    };
  }, [value]);

  return (
    <div className={cn("flex min-h-14 items-center gap-3 rounded-2xl border border-stone-300 bg-surface px-4 py-2 focus-within:border-brand", COLOUR_TRANSITION)}>
        <RepositorySearchIcon className="h-5 w-5 shrink-0 text-brand" />
        <div className="relative min-w-0 flex-1">
          {!value && <span aria-hidden="true" className={cn(
            "pointer-events-none absolute inset-x-0 top-2.5 truncate text-body text-stone-600 transition-[opacity,transform] duration-150 ease-out motion-reduce:transition-none motion-reduce:transform-none",
            visible ? "translate-y-0 opacity-100" : "-translate-y-1 opacity-0",
          )}>{EXAMPLES[example]}</span>}
          <textarea rows={1} value={value} onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) e.preventDefault(); }}
            aria-label="Search records" aria-describedby="discover-search-help"
            className={cn("block min-h-11 max-h-32 w-full resize-none rounded-lg bg-transparent py-2.5 text-body text-stone-900 caret-brand", FOCUS_RING)} />
        </div>
        {value && <button type="button" onClick={() => onChange("")} aria-label="Clear search"
          className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 hover:text-brand [@media(pointer:fine)]:h-9 [@media(pointer:fine)]:w-9", COLOUR_TRANSITION, FOCUS_RING)}>
          <i className="fas fa-times-circle" aria-hidden />
        </button>}
        <p id="discover-search-help" className="sr-only">Search research, authors and topics as you type.</p>
    </div>
  );
}
