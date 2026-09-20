import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { aiApi } from "@/api/ai";
import type { AIAnswer } from "@/types/ai";
import type { RecordDetail } from "@/types/records";
import { AskIrisMark, SynthesisIcon } from "@/features/ai/components/AskIrisIcons";
import {
  DegradedNotice,
  OpenPassageLink,
  PassageQuote,
} from "@/features/ai/components/PassageQuote";

/**
 * AI Overview — a grounded summary of the record being viewed.
 *
 * This runs the same `/ai/ask/` pipeline as Ask IRIS, over the same visibility
 * predicate, so it can only ever draw on records the reader may already open.
 * Nothing here is invented locally: whatever the pipeline could not produce is
 * reported as unavailable rather than filled in.
 *
 * Each claim is backed by a **Passage** — the quoted text and the page it sits
 * on (IR-284) — so a reader can check the summary against the paper rather
 * than taking it on trust.
 *
 * Only the `generative` mode produces an overview. When no model is reachable
 * the endpoint answers `unavailable` and returns the passages unsummarised, so
 * this renders an explicit "AI summary unavailable" state rather than composing
 * one locally — what ADR-008 asks for.
 *
 * The generative branch is live and will render as soon as a provider is
 * configured — that choice is the team's open decision D-4, not this file's.
 */
export function PaperAiOverview({ record }: { record: RecordDetail }) {
  const [answer, setAnswer] = useState<AIAnswer | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await aiApi.ask(
        `${record.title}. Summarise the research objectives, methodology and key findings of this work.`,
        3,
      );
      setAnswer(data);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [record.title]);

  useEffect(() => {
    void load();
  }, [load]);

  const mode = answer?.mode;
  // Only a generative answer is an overview: ADR-008 requires the answer to be
  // replaced by an explicit unavailable state when no model ran, rather than by
  // something assembled here out of the passages.
  const hasOverview = mode === "generative" && Boolean(answer?.answer);

  return (
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 flex items-center gap-2">
          <AskIrisMark className="w-3.5 h-3.5 text-brand" />
          AI Overview
        </h2>
        {mode === "generative" && (
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

      {!loading && !failed && !hasOverview && mode === "unavailable" && (
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

      {!loading && !failed && !hasOverview && mode !== "unavailable" && (
        <div className="flex items-start gap-3">
          <i className="fas fa-circle-info text-[13px] text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-stone-700">Nothing indexed to summarise</p>
            <p className="text-[12px] text-stone-500 mt-0.5">
              {answer?.message ??
                "This record has no indexed text the retrieval service could draw on."}
            </p>
          </div>
        </div>
      )}

      {!loading && !failed && hasOverview && (
        <>
          <p className="text-[13px] text-stone-700 leading-[1.7] whitespace-pre-wrap">
            {answer?.answer}
          </p>

          {answer?.degraded && <DegradedNotice subject="summary" />}

          {answer && (answer.citations.length > 0 || answer.sources.length > 0) && (
            <div className="mt-3 pt-3 border-t border-stone-100">
              <p className="text-[10px] font-bold uppercase tracking-wider text-stone-500 mb-2">
                Grounded in
              </p>
              <ul className="space-y-2 list-none pl-0">
                {answer.citations.map((citation) => (
                  <li
                    key={`${citation.chunk_id}-${citation.marker}`}
                    className="rounded-lg border border-stone-200 bg-stone-50/60 px-2.5 py-2"
                  >
                    <PassageQuote text={citation.text} />
                    <OpenPassageLink citation={citation} className="mt-1.5" />
                  </li>
                ))}
              </ul>

              {/* A model that cited nothing still read something. Naming the
                  records keeps that answer from looking ungrounded, which is
                  what this block showed before passages existed. */}
              {answer.citations.length === 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {answer.sources.map((s) => (
                    <Link
                      key={s.id}
                      to={`/records/${s.id}`}
                      className="max-w-full inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-stone-50 border border-stone-200 text-[11px] font-semibold text-stone-700 hover:border-brand/30 transition-colors"
                    >
                      <i className="fas fa-file-lines text-[9px] text-stone-400" aria-hidden />
                      <span className="truncate">{s.title}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
