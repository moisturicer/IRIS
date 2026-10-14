import { useCallback, useEffect, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import type { RecordOverviewResponse } from "@/types/ai";
import type { RecordDetail } from "@/types/records";
import { AskIrisMark, SynthesisIcon } from "@/features/ai/components/AskIrisIcons";
import { CitationText } from "@/features/ai/components/CitationText";
import { OVERVIEW_MARKDOWN } from "@/features/ai/components/answerLayout";
import { DegradedNotice } from "@/features/ai/components/PassageQuote";
import { cn } from "@/lib/utils";
import { CONTROL_BASE, CONTROL_OUTLINE } from "./controls";
import { SectionHeading } from "./headings";

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

  const load = useCallback(async (retry = false) => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await (retry ? aiApi.overview(record.id, true) : aiApi.overview(record.id));
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

  useEffect(() => {
    if (response?.state !== "generating" || failed) return;

    const timeout = window.setTimeout(() => {
      void aiApi.overview(record.id).then(
        ({ data }) => setResponse(data),
        () => setFailed(true),
      );
    }, 2500);

    return () => window.clearTimeout(timeout);
  }, [failed, record.id, response]);

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
    // On the page, like the Abstract above it: a heading and the text, with no
    // card around it (IR-569).
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <SectionHeading>
          <span className="inline-flex items-center gap-2">
            <AskIrisMark className="w-4 h-4 text-brand" />
            AI Overview
          </span>
        </SectionHeading>
        {state === "ready" && overview && (
          <button type="button" onClick={() => void copy()} className={cn("px-3 text-stone-600", CONTROL_BASE, CONTROL_OUTLINE)}>
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

      {loading && (
        <div>
          <p className="flex items-center gap-2 text-xs text-stone-500 mb-3">
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
          <i className="fas fa-plug-circle-xmark text-sm text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-700">AI overview unavailable</p>
            <p className="text-xs text-stone-500 mt-0.5">
              IRIS could not reach the answering service. Nothing is summarised here rather than
              guessed.
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

      {!loading && !failed && state === "unavailable" && (
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
        <div className="flex items-start gap-3">
          <i className="fas fa-circle-info text-sm text-stone-300 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-700">Nothing indexed to summarise</p>
            <p className="text-xs text-stone-500 mt-0.5">
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
            pageMarkers
            className={OVERVIEW_MARKDOWN}
          />

          {overview.degraded && <DegradedNotice subject="summary" />}

          {overview.citations.length === 0 && (
            <p className="mt-2 text-xs text-stone-500 italic">
              Grounded in this record's indexed passages.
            </p>
          )}
        </>
      )}
    </section>
  );
}
