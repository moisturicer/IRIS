import { useCallback, useEffect, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import type { RecordOverviewResponse } from "@/types/ai";
import type { RecordDetail } from "@/types/records";
import { AskIrisMark, SynthesisIcon } from "@/features/ai/components/AskIrisIcons";
import { CitationText } from "@/features/ai/components/CitationText";
import { CitationOriginContext } from "@/lib/citedPage";
import { OVERVIEW_MARKDOWN } from "@/features/ai/components/answerLayout";
import { DegradedNotice } from "@/features/ai/components/PassageQuote";
import { cn } from "@/lib/utils";
import { CONTROL_BASE } from "./controls";
import { OverviewNote } from "./OverviewNote";

/**
 * AI Overview — a grounded summary of the record being viewed.
 *
 * **Cached server-side, not re-asked on every view (IR-334, IR-335).** This
 * used to fire `/ai/ask/` from this component's own `useEffect`, a corpus-
 * wide question on every mount — a paid vendor call on every page view for an
 * answer that is a pure function of the record's own extracted text.
 * `GET /ai/records/<id>/overview/` reads a per-record cache. Generation runs
 * in a worker after chunking; this panel polls only while that work is pending.
 *
 * The backend reads only the record's active chunk set and applies the same
 * record visibility rule as other reads. Nothing is invented locally:
 * unavailable generation is reported rather than filled in (ADR-008).
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
  // Told apart from an outage, so a reader waits rather than assuming it is down.
  const [throttled, setThrottled] = useState(false);
  const fail = useCallback((error: unknown) => {
    setFailed(true);
    setThrottled((error as { response?: { status?: number } })?.response?.status === 429);
  }, []);

  const load = useCallback(async (retry = false) => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await (retry ? aiApi.overview(record.id, true) : aiApi.overview(record.id));
      setResponse(data);
    } catch (error) {
      fail(error);
    } finally {
      setLoading(false);
    }
  }, [record.id, fail]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (response?.state !== "generating" || failed) return;

    const timeout = window.setTimeout(() => {
      void aiApi.overview(record.id).then(
        ({ data }) => setResponse(data),
        fail,
      );
    }, 2500);

    return () => window.clearTimeout(timeout);
  }, [failed, fail, record.id, response]);

  const state = response?.state;
  const overview = response?.overview ?? null;

  // Copy the text without its markers, so it pastes as prose.
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const copyTimer = useRef<number>();
  useEffect(() => () => window.clearTimeout(copyTimer.current), []);
  const copy = async () => {
    if (!overview) return;
    let outcome: "copied" | "failed" = "copied";
    try {
      await navigator.clipboard.writeText(overview.text.replace(/\s?\[\d+\]/g, ""));
    } catch {
      outcome = "failed";
    }
    setCopied(outcome);
    window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopied("idle"), 2500);
  };

  return (
    // In its own container (IR-1306, reversing IR-569's "no card"): a reader
    // should know at a glance that this text was written by AI, not by the authors.
    <section aria-labelledby="ai-overview-heading"
      className="overflow-hidden rounded-card border border-stone-200 bg-stone-50/70">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-stone-200 bg-surface px-5 py-3">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
          <span aria-hidden className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-brand text-white">
            <AskIrisMark className="size-4" />
          </span>
          <h2 id="ai-overview-heading" className="font-display text-section font-semibold text-stone-900">AI Overview</h2>
          <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-label font-medium text-stone-600 ring-1 ring-stone-300">
            <i aria-hidden className="fas fa-wand-magic-sparkles text-3xs text-brand" />
            AI-generated
          </span>
        </div>
        {state === "ready" && overview && (
          <button type="button" onClick={() => void copy()} className={cn("px-2.5 font-medium text-stone-500 hover:bg-stone-100 hover:text-stone-800", CONTROL_BASE)}>
            <i
              className={cn(
                "fas text-2xs",
                copied === "copied" ? "fa-check text-brand" : copied === "failed" ? "fa-circle-exclamation" : "fa-copy",
              )}
              aria-hidden
            />
            {copied === "copied" ? "Copied" : copied === "failed" ? "Couldn’t copy" : "Copy"}
          </button>
        )}
      </div>

      <div className="px-5 py-5">
      {loading && (
        <div>
          <p className="flex items-center gap-2 text-xs text-stone-500 mb-3">
            <SynthesisIcon className="w-4 h-4" spinning />
            Reading the indexed record set…
          </p>
          <div className="space-y-2 animate-pulse">
            <div className="h-3 w-full rounded-control bg-stone-100" />
            <div className="h-3 w-11/12 rounded-control bg-stone-100" />
            <div className="h-3 w-4/5 rounded-control bg-stone-100" />
          </div>
        </div>
      )}

      {!loading && failed && (
        <div className="flex items-start gap-3">
          <i className="fas fa-plug-circle-xmark text-sm text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-700">
              {throttled ? "AI overview is busy" : "AI overview unavailable"}
            </p>
            <p className="text-xs text-stone-500 mt-0.5">
              {throttled
                ? "Too many requests in a short time. Wait a few minutes, then try again."
                : "IRIS could not reach the answering service. Nothing is summarised here rather than guessed."}
            </p>
            <button
              type="button"
              onClick={() => void load(true)}
              className="mt-2 text-xs font-semibold text-brand hover:underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {!loading && !failed && state === "unavailable" && response?.reason === "no_consent" && (
        <OverviewNote>
          The owner did not consent to AI use of this paper, so nothing is available for AI.
        </OverviewNote>
      )}

      {!loading && !failed && state === "unavailable" && response?.reason !== "no_consent" && (
        <div className="flex items-start gap-3">
          <i className="fas fa-microchip text-sm text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-700">
              AI summary unavailable
            </p>
            <p className="text-xs text-stone-500 mt-0.5 leading-relaxed">
              The answering model could not be reached, so IRIS is not summarising this paper.
              Retrieval still works — see Related Institutional Works below, or put a question to
              Ask IRIS.
            </p>
            <button
              type="button"
              onClick={() => void load(true)}
              className="mt-2 text-xs font-semibold text-brand hover:underline"
            >
              Try again
            </button>
          </div>
        </div>
      )}

      {!loading && !failed && state === "generating" && (
        <div role="status" className="flex items-start gap-3">
          <SynthesisIcon className="w-4 h-4 text-brand" spinning />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-700">AI overview is being prepared</p>
            <p className="text-xs text-stone-500 mt-0.5 leading-relaxed">
              IRIS is reading the indexed paper. This panel will update when the overview is ready.
            </p>
          </div>
        </div>
      )}

      {!loading && !failed && state === "not_indexed" && (
        <OverviewNote>Nothing indexed to summarise.</OverviewNote>
      )}

      {!loading && !failed && state === "ready" && overview && (
        <>
          {/* Its citations are whole pages, and land as such (IR-578). */}
          <CitationOriginContext.Provider value="overview">
            <CitationText
              text={overview.text}
              citations={overview.citations}
              pageMarkers
              className={OVERVIEW_MARKDOWN}
            />
          </CitationOriginContext.Provider>

          {overview.degraded && <DegradedNotice subject="summary" />}

          {overview.citations.length === 0 && (
            <p className="mt-2 text-xs text-stone-500 italic">
              Grounded in this record's indexed passages.
            </p>
          )}
        </>
      )}
      </div>
      {state === "ready" && overview && (
        <p className="border-t border-stone-200 px-5 py-2.5 text-small text-stone-600">
          Written by AI from this paper&rsquo;s text. Check important details against the cited pages.
        </p>
      )}
    </section>
  );
}
