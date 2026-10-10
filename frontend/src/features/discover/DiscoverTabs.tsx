import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

export interface DiscoverTab {
  id:      string;
  label:   string;
  content: ReactNode;
}

interface DiscoverTabsProps {
  tabs:     DiscoverTab[];
  active:   string;
  onSelect: (id: string) => void;
}

/**
 * Discover's content tabs (spec §4.3): Research, and Proposals once the
 * Discoverable backend exists (IR-421 adds that tab here, with its own
 * `ResearchCard` content).
 *
 * Tabs are for a real split of content only, so with a single tab no tab bar
 * is drawn at all: an empty or lone tab would be furniture, and a Proposals
 * tab must never be shown before there are Proposals to show.
 */
export function DiscoverTabs({ tabs, active, onSelect }: DiscoverTabsProps) {
  const baseId = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = tabs.find((t) => t.id === active) ?? tabs[0];

  if (tabs.length < 2) return <>{current?.content}</>;

  // Arrow keys move between tabs; Tab moves into the panel (WAI-ARIA tabs).
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (index + step + tabs.length) % tabs.length;
    onSelect(tabs[next].id);
    tabRefs.current[next]?.focus();
  };

  return (
    <>
      <div role="tablist" aria-label="Discover content" className="mt-6 flex gap-6 border-b border-stone-200">
        {tabs.map((tab, index) => {
          const selected = tab.id === current.id;
          return (
            <button
              key={tab.id}
              ref={(el) => { tabRefs.current[index] = el; }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onSelect(tab.id)}
              onKeyDown={(e) => onKeyDown(e, index)}
              className={cn(
                "-mb-px pb-3 border-b-2 text-body font-medium",
                COLOUR_TRANSITION,
                FOCUS_RING,
                selected ? "border-brand text-stone-900" : "border-transparent text-stone-600 hover:text-stone-900",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${baseId}-panel-${current.id}`} aria-labelledby={`${baseId}-tab-${current.id}`}>
        {current.content}
      </div>
    </>
  );
}
