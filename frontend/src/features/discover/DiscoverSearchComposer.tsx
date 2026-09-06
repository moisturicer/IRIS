import { useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { RepositorySearchIcon } from "./DiscoverIcons";
import { cn } from "@/lib/utils";

type SearchMode = "keyword" | "smart";

interface DiscoverSearchComposerProps {
  value: string;
  onChange: (value: string) => void;
  /** Opens the filter panel — the composer's "+" is a second entry point to it. */
  onAddFilter: () => void;
}

/**
 * The search composer. "Smart AI Search" hands the query to Ask IRIS, which is
 * a real grounded-retrieval endpoint — not a decorative label.
 */
export function DiscoverSearchComposer({
  value,
  onChange,
  onAddFilter,
}: DiscoverSearchComposerProps) {
  const navigate = useNavigate();
  const [mode, setMode] = useState<SearchMode>("keyword");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function onPointerDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const submit = () => {
    const query = value.trim();
    if (!query) return;
    // Keyword search already filters live as you type; only Smart search navigates.
    if (mode === "smart") navigate(`/ai?q=${encodeURIComponent(query)}`);
  };

  return (
    <div className="bg-white border border-stone-200 rounded-2xl shadow-card px-4 pt-3.5 pb-3 focus-within:border-brand/40 transition-colors">
      <div className="flex items-start gap-2.5">
        <RepositorySearchIcon className="w-[18px] h-[18px] mt-0.5 shrink-0 text-stone-400" />
        <textarea
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          aria-label="Search records"
          placeholder="Who's working on edge AI at CIT-U? Search research, authors, topics…"
          className="flex-1 min-w-0 resize-none bg-transparent text-[13px] text-stone-800 placeholder-stone-400 outline-none leading-6 max-h-32"
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="p-1 text-stone-300 hover:text-stone-500"
          >
            <i className="fas fa-times-circle text-[13px]" aria-hidden />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 mt-2.5">
        <button
          type="button"
          onClick={onAddFilter}
          aria-label="Add a filter"
          title="Add a filter"
          className="w-7 h-7 shrink-0 rounded-full border border-stone-200 text-stone-500 flex items-center justify-center hover:border-brand-200 hover:text-brand transition-colors"
        >
          <i className="fas fa-plus text-[11px]" aria-hidden />
        </button>

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-[12px] font-semibold transition-colors",
              mode === "smart"
                ? "bg-brand-50 border-brand-200 text-brand"
                : "bg-white border-stone-200 text-stone-600 hover:border-stone-300",
            )}
          >
            <span>{mode === "smart" ? "Smart AI Search" : "Keyword Search"}</span>
            <i className={cn("fas fa-chevron-down text-[8px] opacity-60 transition-transform", menuOpen && "rotate-180")} aria-hidden />
          </button>

          {menuOpen && (
            <div className="absolute left-0 bottom-full mb-2 w-64 bg-white rounded-xl shadow-card-md border border-stone-200 py-1.5 z-40">
              <ModeOption
                active={mode === "keyword"}
                title="Keyword Search"
                detail="Filters this page as you type."
                onClick={() => { setMode("keyword"); setMenuOpen(false); }}
              />
              <ModeOption
                active={mode === "smart"}
                title="Smart AI Search"
                detail="Sends the question to Ask IRIS for a grounded answer."
                onClick={() => { setMode("smart"); setMenuOpen(false); }}
              />
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2.5">
          <span className="hidden sm:inline text-[11px] font-mono text-stone-400">
            {mode === "smart" ? "Enter to ask" : "Filtering as you type"}
          </span>
          <button
            type="button"
            onClick={submit}
            disabled={!value.trim() || mode !== "smart"}
            aria-label="Ask IRIS"
            title={mode === "smart" ? "Ask IRIS" : "Switch to Smart AI Search to ask"}
            className="w-8 h-8 shrink-0 rounded-full bg-brand text-white flex items-center justify-center transition-colors hover:bg-brand-light disabled:opacity-30"
          >
            <i className="fas fa-arrow-up text-[12px]" aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}

function ModeOption({
  active,
  title,
  detail,
  onClick,
}: {
  active: boolean;
  title: string;
  detail: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-3 py-2 hover:bg-stone-50 transition-colors"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-semibold text-stone-800">{title}</span>
        {active && <i className="fas fa-check text-brand text-[11px]" aria-hidden />}
      </span>
      <span className="block text-[11px] text-stone-500 mt-0.5">{detail}</span>
    </button>
  );
}
