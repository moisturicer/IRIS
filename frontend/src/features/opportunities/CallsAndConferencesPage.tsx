import { useEffect, useMemo, useState } from "react";
import { opportunitiesApi } from "@/api/opportunities";
import {
  getSavedOpportunityIds,
  toggleSavedOpportunity,
} from "@/lib/opportunityLibrary";
import type { Opportunity, OpportunityType } from "@/types/opportunities";
import { cn } from "@/lib/utils";
import {
  TYPE_TABS,
  TYPE_BADGE_CLASS,
  countdownChip,
  formatCeiling,
  formatDueDate,
  matchesQuery,
} from "./opportunityUtils";

/**
 * Calls & Conferences — a deadline board (IR-121).
 *
 * The one question this page answers is "what can I still apply to, and by
 * when". Everything is ordered around that: featured first, then soonest
 * deadline (server-side), with urgency encoded in the countdown chip's colour.
 *
 * Two deliberate departures from the mockup, both recorded in IR-121:
 *
 *  - the header counter read "0 Saved Reminders". Reminders are .ics downloads
 *    that live in the user's own calendar, so IRIS has nothing to count. It
 *    shows saved bookmarks instead, which IRIS does know about.
 *  - closed items are not hidden the moment they pass. They grey out in place
 *    so somebody mid-application can still find the page they were reading,
 *    and only drop off after a month (enforced server-side).
 */
export function CallsAndConferencesPage() {
  const [items,   setItems]   = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  const [activeType, setActiveType] = useState<OpportunityType | null>(null);
  const [query,      setQuery]      = useState("");
  const [savedIds,   setSavedIds]   = useState<number[]>(() => getSavedOpportunityIds());
  const [busyIcs,    setBusyIcs]    = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    opportunitiesApi
      .list()
      .then(({ data }) => {
        if (!cancelled) setItems(data.results);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load calls and conferences.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const visible = useMemo(
    () => items.filter(
      (o) => (activeType === null || o.opportunity_type === activeType) && matchesQuery(o, query),
    ),
    [items, activeType, query],
  );

  // "Active" means still open — a closed call is not something you can act on,
  // so counting it here would overstate what the board offers.
  const activeCount = useMemo(() => items.filter((o) => !o.is_closed).length, [items]);

  const handleToggleSave = (id: number) => {
    toggleSavedOpportunity(id);
    setSavedIds(getSavedOpportunityIds());
  };

  const handleDownloadIcs = async (o: Opportunity) => {
    setBusyIcs(o.id);
    try {
      const { data } = await opportunitiesApi.calendar(o.id);
      // Fetched with auth then handed to the browser as a blob — a plain link
      // to the endpoint would arrive unauthenticated and 401.
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${o.title.replace(/[^\w\s-]/g, "").slice(0, 60).trim() || "opportunity"}.ics`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not build the calendar file.");
    } finally {
      setBusyIcs(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-[1400px] mx-auto space-y-4">
      {/* ---- Orientation ------------------------------------------------- */}
      <header className="bg-white rounded-xl border border-stone-200 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-6 h-6 rounded-full bg-brand text-white flex items-center justify-center shrink-0">
                <i className="fas fa-bullhorn text-[10px]" aria-hidden />
              </span>
              <span className="text-[11px] font-bold uppercase tracking-wider text-brand">
                Institutional &amp; External Announcements
              </span>
            </div>
            <h1 className="text-2xl font-bold text-stone-900">Calls &amp; Conferences</h1>
            <p className="text-[13px] text-stone-600 mt-1 max-w-2xl">
              Internal research calls, upcoming conference deadlines, and competitive funding
              windows published by CIT-U offices and partner institutions.
            </p>
          </div>

          <div className="flex items-center gap-3 text-[12px] font-semibold rounded-lg border border-stone-200 px-3 py-2 shrink-0">
            <span className="flex items-center gap-1.5 text-stone-700">
              <i className="fas fa-calendar-check text-brand text-[11px]" aria-hidden />
              {activeCount} Active {activeCount === 1 ? "Call" : "Calls"}
            </span>
            <span className="w-px h-4 bg-stone-200" aria-hidden />
            {/* Saved, not "reminders": an .ics download lives in the user's own
                calendar and IRIS never sees it again. */}
            <span className="text-stone-500" title="Saved in this browser only">
              {savedIds.length} Saved
            </span>
          </div>
        </div>

        {/* ---- Filters --------------------------------------------------- */}
        <div className="flex items-center gap-3 mt-5 pt-4 border-t border-stone-100 flex-wrap">
          <div
            className="flex items-center gap-1.5 overflow-x-auto scrollbar-thin -mb-1 pb-1"
            role="tablist"
            aria-label="Filter by type"
          >
            {TYPE_TABS.map((tab) => {
              const active = activeType === tab.id;
              return (
                <button
                  key={tab.label}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveType(tab.id)}
                  className={cn(
                    "px-3.5 py-1.5 rounded-full text-[12px] font-semibold whitespace-nowrap transition-colors",
                    active
                      ? "bg-brand text-white"
                      : "text-stone-600 border border-stone-200 hover:bg-stone-50",
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          <div className="relative ml-auto min-w-[200px] flex-1 sm:flex-none sm:w-[280px]">
            <i
              className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 text-[11px]"
              aria-hidden
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search calls, keywords..."
              aria-label="Search calls and conferences"
              className="w-full pl-8 pr-3 py-2 rounded-lg border border-stone-200 text-[12px]
                placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/40"
            />
          </div>
        </div>
      </header>

      {/* ---- Board ------------------------------------------------------- */}
      {loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-stone-200 p-5 animate-pulse">
              <div className="h-5 w-32 bg-stone-100 rounded-full" />
              <div className="h-5 w-3/4 bg-stone-100 rounded mt-4" />
              <div className="h-3 w-1/2 bg-stone-100 rounded mt-3" />
              <div className="h-3 w-full bg-stone-100 rounded mt-4" />
              <div className="h-3 w-5/6 bg-stone-100 rounded mt-2" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="bg-white rounded-xl border border-red-200 p-8 text-center">
          <i className="fas fa-triangle-exclamation text-red-500 text-xl" aria-hidden />
          <p className="text-[13px] text-stone-700 mt-2">{error}</p>
        </div>
      ) : visible.length === 0 ? (
        <div className="bg-white rounded-xl border border-stone-200 p-10 text-center">
          <i className="fas fa-bullhorn text-stone-300 text-2xl" aria-hidden />
          <p className="text-[13px] font-semibold text-stone-700 mt-3">
            {items.length === 0
              ? "No calls have been posted yet."
              : "Nothing matches these filters."}
          </p>
          <p className="text-[12px] text-stone-500 mt-1">
            {items.length === 0
              ? "RDCO, KTTO and advisers publish calls here as they open."
              : "Try a different type, or clear the search."}
          </p>
          {items.length > 0 && (
            <button
              type="button"
              onClick={() => { setActiveType(null); setQuery(""); }}
              className="mt-4 px-3.5 py-1.5 rounded-lg text-[12px] font-semibold text-brand border border-brand-200 hover:bg-brand-50"
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {visible.map((o) => (
            <OpportunityCard
              key={o.id}
              opportunity={o}
              saved={savedIds.includes(o.id)}
              icsBusy={busyIcs === o.id}
              onToggleSave={() => handleToggleSave(o.id)}
              onDownloadIcs={() => void handleDownloadIcs(o)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface CardProps {
  opportunity:   Opportunity;
  saved:         boolean;
  icsBusy:       boolean;
  onToggleSave:  () => void;
  onDownloadIcs: () => void;
}

function OpportunityCard({ opportunity: o, saved, icsBusy, onToggleSave, onDownloadIcs }: CardProps) {
  const chip    = countdownChip(o);
  const ceiling = formatCeiling(o.funding_ceiling);

  return (
    <article
      className={cn(
        "bg-white rounded-xl border p-5 flex flex-col transition-colors",
        // A closed call stays legible but visibly spent — it is reference now,
        // not an option.
        o.is_closed ? "border-stone-200 opacity-70" : "border-stone-200 hover:border-stone-300",
      )}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className={cn(
            "px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider",
            o.is_closed ? "bg-stone-200 text-stone-600" : TYPE_BADGE_CLASS[o.opportunity_type],
          )}
        >
          {o.type_display}
        </span>

        {o.is_featured && !o.is_closed && (
          <span className="px-2 py-1 rounded-md text-[10px] font-bold bg-stone-900 text-white flex items-center gap-1">
            <i className="fas fa-star text-[9px]" aria-hidden />
            Featured
          </span>
        )}

        {o.source === "external" && (
          <span
            className="px-2 py-1 rounded-md text-[10px] font-semibold border border-stone-200 text-stone-500"
            title="Published by an external body and reposted here"
          >
            External
          </span>
        )}

        <span
          className={cn(
            "ml-auto px-2.5 py-1 rounded-full text-[11px] font-semibold flex items-center gap-1.5 shrink-0",
            chip.className,
          )}
        >
          <i className="far fa-clock text-[10px]" aria-hidden />
          {chip.label}
        </span>
      </div>

      <h2 className="text-[15px] font-bold text-stone-900 mt-3 leading-snug">{o.title}</h2>

      <dl className="mt-2.5 space-y-1.5">
        <MetaRow icon="fa-building-columns" label="Posting office">
          <span className="text-brand font-medium">{o.posting_office}</span>
        </MetaRow>
        {o.audience && (
          <MetaRow icon="fa-users" label="Audience">{o.audience}</MetaRow>
        )}
        {ceiling && (
          <MetaRow icon="fa-money-bill-wave" label="Funding ceiling">
            <span className="font-semibold text-stone-800">{ceiling}</span>
          </MetaRow>
        )}
      </dl>

      {o.description && (
        <p className="text-[12px] text-stone-600 leading-relaxed mt-3 line-clamp-3">
          {o.description}
        </p>
      )}

      {o.tags.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 mt-3">
          {o.tags.map((tag) => (
            <li
              key={tag}
              className="px-2 py-0.5 rounded-md bg-stone-50 border border-stone-200 text-[10px] text-stone-500"
            >
              #{tag}
            </li>
          ))}
        </ul>
      )}

      <footer className="flex items-center gap-2 mt-4 pt-3.5 border-t border-stone-100">
        <span className="text-[11px] text-stone-500 flex items-center gap-1.5">
          <i className="far fa-calendar text-[10px]" aria-hidden />
          Due: {formatDueDate(o.due_date)}
        </span>

        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={onToggleSave}
            aria-pressed={saved}
            aria-label={saved ? `Remove ${o.title} from saved` : `Save ${o.title}`}
            title={saved ? "Saved in this browser" : "Save in this browser"}
            className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
              saved ? "text-brand bg-brand-50" : "text-stone-400 hover:text-stone-700 hover:bg-stone-50",
            )}
          >
            <i className={cn(saved ? "fas" : "far", "fa-bookmark text-[12px]")} aria-hidden />
          </button>

          <button
            type="button"
            onClick={onDownloadIcs}
            disabled={icsBusy}
            aria-label={`Add ${o.title} deadline to your calendar`}
            title="Add the deadline to your own calendar (.ics)"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-stone-400
              hover:text-stone-700 hover:bg-stone-50 transition-colors disabled:opacity-50"
          >
            <i
              className={cn(icsBusy ? "fas fa-spinner fa-spin" : "far fa-calendar-plus", "text-[12px]")}
              aria-hidden
            />
          </button>

          {o.external_url ? (
            <a
              href={o.external_url}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "px-3.5 py-1.5 rounded-lg text-[12px] font-semibold transition-colors ml-1",
                o.is_closed
                  ? "bg-stone-100 text-stone-500 hover:bg-stone-200"
                  : "bg-brand text-white hover:bg-brand-light",
              )}
            >
              {o.is_closed ? "View" : "View & Apply"}
              <i className="fas fa-arrow-up-right-from-square text-[9px] ml-1.5" aria-hidden />
            </a>
          ) : (
            // No link means the poster gave none — say so rather than render a
            // button that goes nowhere.
            <span className="px-3 py-1.5 text-[11px] text-stone-400 ml-1">
              Contact {o.posting_office.split("(")[0].trim()}
            </span>
          )}
        </div>
      </footer>
    </article>
  );
}

function MetaRow({
  icon, label, children,
}: { icon: string; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-[12px] text-stone-600">
      <i className={cn("fas", icon, "text-stone-400 text-[11px] mt-0.5 w-3.5 shrink-0")} aria-hidden />
      <dt className="sr-only">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}
