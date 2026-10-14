import { useAskIrisHandoff } from "@/lib/askHandoff";
import { RepositorySearchIcon } from "./DiscoverIcons";

interface DiscoverSearchComposerProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * The search composer. Typing filters the catalogue live; "Ask IRIS about
 * this" is a separate, explicit action that hands the exact text to Ask IRIS
 * as an editable draft. Neither runs the other (IR-559).
 */
export function DiscoverSearchComposer({
  value,
  onChange,
}: DiscoverSearchComposerProps) {
  const askIris = useAskIrisHandoff();

  const question = value.trim();

  return (
    <div className="bg-white border border-stone-200 rounded-2xl shadow-card px-4 pt-3.5 pb-3 focus-within:border-brand/40 transition-colors">
      <div className="flex items-start gap-2.5">
        <RepositorySearchIcon className="w-[18px] h-[18px] mt-0.5 shrink-0 text-stone-400" />
        <textarea
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            // Enter only keeps the box from growing a line; it never asks.
            if (e.key === "Enter" && !e.shiftKey) e.preventDefault();
          }}
          aria-label="Search records"
          placeholder="Who's working on edge AI at CIT-U? Search research, authors, topics…"
          className="flex-1 min-w-0 resize-none bg-transparent text-[14px] text-stone-800 placeholder-stone-400 outline-none leading-6 max-h-32"
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="p-1 text-stone-300 hover:text-stone-500"
          >
            <i className="fas fa-times-circle text-[14px]" aria-hidden />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 mt-2.5">
        <span className="text-[12px] font-mono text-stone-400">Filtering the catalogue as you type</span>
        <button
          type="button"
          onClick={() => askIris(value)}
          disabled={!question}
          title="Opens Ask IRIS with this text as a draft. Nothing is sent until you press Send."
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-brand-200 bg-brand-50 text-brand text-[13px] font-semibold transition-colors hover:bg-brand-100 disabled:opacity-40"
        >
          <i className="fas fa-brain text-[12px]" aria-hidden />
          Ask IRIS about this
        </button>
      </div>
    </div>
  );
}
