import { useCallback, useEffect, useState } from "react";
import { aiApi } from "@/api/ai";
import type { RecordOverviewResponse } from "@/types/ai";
import type { RecordDetail } from "@/types/records";
import { AskIrisMark, SynthesisIcon } from "@/features/ai/components/AskIrisIcons";
import { CitationText } from "@/features/ai/components/CitationText";
import { DegradedNotice } from "@/features/ai/components/PassageQuote";

/**
 * AI Overview — a grounded summary of the record being viewed.
 *
 * **Cached server-side, not re-asked on every view (IR-334, IR-335).** This
 * used to fire `/ai/ask/` from this component's own `useEffect`, a corpus-
 * wide question on every mount — a paid vendor call on every page view for an
 * answer that is a pure function of the record's own extracted text.
 * `GET /ai/records/<id>/overview/` now generates once, scoped to the record,
 * and returns the cached row on every read after; the vendor is called again
 * only when a re-chunk changes what there is to summarise.
 *
 * This runs the same retrieval and visibility predicate as Ask IRIS, so it
 * can only ever draw on the record being viewed. Nothing here is invented
 * locally: whatever the pipeline could not produce is reported as
 * unavailable rather than filled in (ADR-008).
 *
 * Rendered as markdown through `CitationText` (IR-335) rather than plain
 * text — the same renderer chat uses, so headings, lists and emphasis in the
 * summary read as such, and its citation markers become the same clickable
 * chips that open the in-app reader at the cited page and passage.
 */
export function PaperAiOverview({ record }: { record: RecordDetail }) {
  const [response, setResponse] = useState<RecordOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await aiApi.overview(record.id);
      setResponse(data);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [record.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const state = response?.state;
  const overview = response?.overview ?? null;

  return (
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 flex items-center gap-2">
          <AskIrisMark className="w-3.5 h-3.5 text-brand" />
          AI Overview
        </h2>
        {state === "ready" && (
          <span className="text-[11px] text-stone-400">RAG-indexed paper synthesis</span>
        )}
      </div>

      {loading && (
        <div>
          <p className="flex items-center gap-2 text-[12px] text-stone-400 mb-3">
            <SynthesisIcon className="w-4 h-4" spinning />
            Reading the indexed record set…
          </p>
          <div className="space-y-2 animate-pulse">
            <div className="h-3 w-full rounded bg-stone-100" />
            <div className="h-3 w-11/12 rounded bg-stone-100" />
            <div className="h-3 w-4/5 rounded bg-stone-100" />
          </div>
        </div>
      )}

      {!loading && failed && (
        <div className="flex items-start gap-3">
          <i className="fas fa-plug-circle-xmark text-[13px] text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-stone-700">AI overview unavailable</p>
            <p className="text-[12px] text-stone-500 mt-0.5">
              IRIS could not reach the answering service. Nothing is summarised here rather than
              guessed.
            </p>
            <button
              type="button"
              onClick={() => void load()}
              className="mt-2 text-[12px] font-semibold text-brand hover:underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {!loading && !failed && state === "unavailable" && (
        <div className="flex items-start gap-3">
          <i className="fas fa-microchip text-[13px] text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-stone-700">
              AI summary unavailable
            </p>
            <p className="text-[12px] text-stone-500 mt-0.5 leading-relaxed">
              The answering model could not be reached, so IRIS is not summarising this paper.
              Retrieval still works — see Related Institutional Works below, or ask a question in
              Paper Chat.
            </p>
          </div>
        </div>
      )}

      {!loading && !failed && state === "not_indexed" && (
        <div className="flex items-start gap-3">
          <i className="fas fa-circle-info text-[13px] text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-stone-700">Nothing indexed to summarise</p>
            <p className="text-[12px] text-stone-500 mt-0.5">
              This record has no indexed text the retrieval service could draw on.
            </p>
          </div>
        </div>
      )}

      {!loading && !failed && state === "ready" && overview && (
        <>
          <CitationText
            text={overview.text}
            citations={overview.citations}
            className="text-[13px] text-stone-700 leading-[1.7] [&_h1]:text-[16px] [&_h1]:font-bold [&_h1]:mt-3 [&_h1]:mb-1.5 [&_h2]:text-[14px] [&_h2]:font-bold [&_h2]:mt-3 [&_h2]:mb-1 [&_p]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-2 [&_li]:mb-0.5 [&_strong]:font-semibold [&_strong]:text-stone-800"
          />

          {overview.degraded && <DegradedNotice subject="summary" />}

          {overview.citations.length === 0 && (
            <p className="mt-2 text-[12px] text-stone-400 italic">
              Grounded in this record's indexed passages.
            </p>
          )}
        </>
      )}
    </section>
  );
}
