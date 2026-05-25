import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import type { RecordDetail } from "@/types/records";

interface SourceContextPanelProps {
  open:         boolean;
  citationIds:  number[];
  onClose:      () => void;
}

export function SourceContextPanel({ open, citationIds, onClose }: SourceContextPanelProps) {
  const [records, setRecords]   = useState<RecordDetail[]>([]);
  const [loading, setLoading]   = useState(false);

  useEffect(() => {
    if (!open || citationIds.length === 0) {
      setRecords([]);
      return;
    }

    let cancelled = false;
    setLoading(true);

    Promise.all(
      citationIds.map((id) =>
        recordsApi.detail(id).then(({ data }) => data).catch(() => null),
      ),
    )
      .then((items) => {
        if (!cancelled) {
          setRecords(items.filter((r): r is RecordDetail => r !== null));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [open, citationIds.join(",")]);

  if (!open) return null;

  return (
    <aside
      className="shrink-0 w-[min(100%,320px)] sm:w-[300px] flex flex-col border-l border-stone-200/80 bg-stone-50/50"
      aria-label="Referenced sources"
    >
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-stone-200/60 bg-white">
        <div>
          <h2 className="text-[12px] font-bold text-stone-800">Referenced sources</h2>
          <p className="text-[10px] text-stone-500 mt-0.5">Records used for the latest answer</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-2 rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-700"
          aria-label="Hide sources panel"
        >
          <i className="fas fa-xmark text-[13px]" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-3 space-y-3">
        {citationIds.length === 0 && (
          <p className="text-[12px] text-stone-500 text-center py-8 px-2">
            Ask a question to see which records IRIS used in its answer.
          </p>
        )}

        {loading && citationIds.length > 0 && (
          <div className="space-y-3 animate-pulse">
            {[1, 2].map((n) => (
              <div key={n} className="bg-white rounded-xl border border-stone-200 p-4 space-y-2">
                <div className="h-3 bg-stone-200 rounded w-3/4" />
                <div className="h-2 bg-stone-100 rounded w-full" />
                <div className="h-2 bg-stone-100 rounded w-5/6" />
              </div>
            ))}
          </div>
        )}

        {!loading && records.map((r, index) => (
          <article
            key={r.id}
            className="bg-white rounded-xl border border-stone-200/90 p-4 shadow-sm hover:border-[#6B0F12]/20 transition-colors"
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wide text-[#6B0F12]">
                Source {index + 1}
              </span>
              {r.classification_name && (
                <span className="text-[9px] text-stone-400 truncate max-w-[120px]">
                  {r.classification_name}
                </span>
              )}
            </div>
            <h3 className="text-[13px] font-semibold text-stone-900 leading-snug line-clamp-2">
              {r.title}
            </h3>
            {r.authors?.length > 0 && (
              <p className="text-[11px] text-stone-500 mt-1 line-clamp-1">
                {r.authors.map((a) => a.name).join(", ")}
              </p>
            )}
            {r.abstract && (
              <p className="text-[11px] text-stone-600 mt-2 line-clamp-3 leading-relaxed">
                {r.abstract}
              </p>
            )}
            <Link
              to={`/records/${r.id}`}
              className="mt-3 inline-flex items-center gap-1.5 text-[11px] font-semibold text-[#6B0F12] hover:underline"
            >
              View record
              <i className="fas fa-arrow-right text-[9px]" />
            </Link>
          </article>
        ))}

        {!loading && citationIds.length > 0 && records.length === 0 && (
          <p className="text-[12px] text-stone-500 text-center py-6">
            Could not load record details. Citations: {citationIds.join(", ")}
          </p>
        )}
      </div>
    </aside>
  );
}
