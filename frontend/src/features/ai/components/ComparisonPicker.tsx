import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { recordsApi } from "@/api/records";
import { INSTITUTION } from "@/config/institution";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { CHAT_COMPOSER_ICON } from "./answerLayout";
import type { Classification, ComparisonRecord } from "@/types/records";

const ORIGINS = {
  institutional: `${INSTITUTION.shortName} research`,
  imported_reference: "Imported reference",
  synthetic: "Synthetic",
  unknown: "Origin not recorded",
};

interface Props {
  selected: ComparisonRecord[];
  onChange: (records: ComparisonRecord[]) => void;
  limit?: number;
  disabled?: boolean;
  scoped: boolean;
}

interface Results {
  key: string;
  papers: ComparisonRecord[];
  next: boolean;
  failed: boolean;
}

/** Selects catalogue IDs only; reading, coverage and comparison stay on IR-549. */
export function ComparisonPicker({ selected, onChange, limit, disabled, scoped }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [area, setArea] = useState("");
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const [results, setResults] = useState<Results | null>(null);
  const [areas, setAreas] = useState<Classification[]>([]);
  const [areasFailed, setAreasFailed] = useState(false);
  const key = JSON.stringify([query.trim(), area, page, retry]);
  const busy = results?.key !== key;
  const available = !disabled && !scoped && limit !== undefined;

  useEffect(() => {
    if (!open) return;
    let obsolete = false;
    // Catalogue requests are debounced and fenced: neither old matches nor
    // an old failure can replace the current query's result.
    const timer = window.setTimeout(() => {
      recordsApi.list({ search: query.trim(), classification: area || undefined, ordering: "title", page })
        .then(({ data }) => {
          if (!obsolete) setResults({ key, papers: data.results, next: Boolean(data.next), failed: false });
        })
        .catch(() => {
          if (!obsolete) setResults({ key, papers: [], next: false, failed: true });
        });
    }, 250);
    return () => { obsolete = true; window.clearTimeout(timer); };
  }, [open, key, query, area, page]);

  useEffect(() => {
    if (!open) return;
    let obsolete = false;
    setAreasFailed(false);
    void (async () => {
      try {
        const all: Classification[] = [];
        let next = true;
        for (let page = 1; next; page += 1) {
          const { data } = await recordsApi.classifications({ page });
          if (obsolete) return;
          all.push(...data.results);
          next = Boolean(data.next);
        }
        setAreas(all);
      } catch {
        if (!obsolete) setAreasFailed(true);
      }
    })();
    return () => { obsolete = true; };
  }, [open, retry]);

  const changeSelection = (paper: ComparisonRecord) => {
    if (!available) return;
    if (selected.some((r) => r.id === paper.id)) onChange(selected.filter((r) => r.id !== paper.id));
    else if (limit !== undefined && selected.length < limit) onChange([...selected, paper]);
  };
  const count = limit === undefined ? "Comparison limit unavailable. Reload to try again." :
    selected.length === 1 ? `1 of ${limit} papers selected. Choose at least 2 to compare.` :
      `${selected.length} of ${limit} papers selected.`;

  return (
    // `contents`: these sit directly in the composer's control row.
    <div className="contents">
      <div className="contents">
        <button type="button" disabled={!available} aria-label="Compare papers" title="Compare papers"
          aria-haspopup="dialog" onClick={() => { setResults(null); setOpen(true); }}
          className={cn(CHAT_COMPOSER_ICON, COLOUR_TRANSITION, FOCUS_RING,
            selected.length > 0 ? "border border-brand-200 bg-brand-50 text-brand" : "border border-stone-300 text-stone-700 hover:border-brand/40 hover:text-brand",
            "disabled:border-stone-200 disabled:bg-transparent disabled:text-stone-400 disabled:cursor-not-allowed")}>
          <i className="fas fa-columns text-sm" aria-hidden />
        </button>
        <p className="order-1 text-xs text-stone-600" aria-live="polite">
          {/* Nothing to report until a paper is chosen; the dialog states the limit. */}
          {scoped ? "This chat is about one paper. Start a new chat to compare papers." : selected.length > 0 || limit === undefined ? count : null}
        </p>
      </div>
      {selected.length > 0 && (
        <ul aria-label="Papers to compare" tabIndex={0} className="order-2 flex max-h-40 basis-full flex-wrap gap-2 overflow-y-auto rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand">
          {selected.map((paper) => (
            <li key={paper.id} className="inline-flex max-w-full items-center rounded-lg border border-stone-300 text-sm text-stone-800">
              <span className="min-w-0 break-words py-1.5 pl-3">{paper.title}</span>
              <button type="button" disabled={disabled} aria-label={`Remove ${paper.title} from comparison`}
                onClick={() => onChange(selected.filter((r) => r.id !== paper.id))}
                className="min-h-11 min-w-11 shrink-0 rounded-lg text-stone-600 hover:text-stone-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand">
                <i className="fas fa-xmark" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {createPortal(<Modal open={open && available} onClose={() => setOpen(false)} title="Compare papers" size="max-w-xl"
        footer={<div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-stone-600">{count}</p>
          <Button type="button" className="min-h-11" onClick={() => setOpen(false)}>Done</Button>
        </div>}>
        <p className="mb-4 text-sm text-stone-600">Choose papers from the catalogue, then ask what you want to compare. Only papers you can browse appear here.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label="Search papers" size="lg" hint="Search titles, abstracts and author names." value={query} onChange={(e) => { setQuery(e.target.value); setPage(1); }}
            onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} />
          <Select label="Area" size="lg" value={area} onChange={(e) => { setArea(e.target.value); setPage(1); }}>
            <option value="">All areas</option>
            {areas.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
        </div>
        {areasFailed && <div className="mt-2 text-sm text-stone-700" role="alert"><p>Could not load areas. You can still search papers.</p><Button type="button" variant="outline" className="mt-2 min-h-11" onClick={() => setRetry((r) => r + 1)}>Retry areas</Button></div>}
        <div className="mt-4" aria-busy={busy}>
          {busy ? <p role="status" className="py-6 text-sm text-stone-600">Searching catalogue…</p> :
            results?.failed ? <div role="alert" className="py-4 text-sm text-stone-700">
              <p>Could not load papers. Your selections are kept.</p>
              <Button type="button" variant="outline" className="mt-2 min-h-11" onClick={() => setRetry((r) => r + 1)}>Retry search</Button>
            </div> : !results?.papers.length ? <p role="status" className="py-6 text-sm text-stone-600">No catalogue papers match. Try another title or Area.</p> : (
              <ul aria-label="Catalogue papers" className="divide-y divide-stone-200">
                {results.papers.map((paper) => {
                  const checked = selected.some((r) => r.id === paper.id);
                  return <li key={paper.id}>
                    <label className="flex min-h-11 cursor-pointer items-start gap-3 py-3">
                      <input type="checkbox" checked={checked} aria-label={`Compare ${paper.title}`}
                        disabled={!checked && selected.length >= (limit ?? 0)} onChange={() => changeSelection(paper)}
                        className="mt-1 h-4 w-4 shrink-0 accent-brand" />
                      <span className="min-w-0">
                        <span className="block break-words text-sm font-medium text-stone-900">{paper.title}</span>
                        <span className="mt-1 block text-xs text-stone-600">{paper.classification_name ?? "Area not recorded"} · {ORIGINS[paper.origin ?? "unknown"]}</span>
                      </span>
                    </label>
                  </li>;
                })}
              </ul>
            )}
        </div>
        <div className="mt-3 flex items-center justify-between gap-3">
          <Button type="button" variant="ghost" className="min-h-11" size="sm" disabled={busy || page === 1} onClick={() => setPage((p) => p - 1)}>Previous papers</Button>
          <span className="text-xs text-stone-600">Page {page}</span>
          <Button type="button" variant="ghost" className="min-h-11" size="sm" disabled={busy || !results?.next} onClick={() => setPage((p) => p + 1)}>Next papers</Button>
        </div>
      </Modal>, document.body)}
    </div>
  );
}
