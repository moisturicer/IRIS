import { useEffect, useState } from "react";
import { compactionRun, type ReaderConversation, type ReaderRun, type ReaderUsage } from "@/api/runtimeReader";
import { recordsApi } from "@/api/records";
import type { Citation, SemanticSearchResult } from "@/types/ai";
import type { ChatMessage, EndedRunState } from "@/types/chat";

type Turn = ReaderConversation["turns"][number];

/** Cards for the papers a conversation cites, fetched once each. */
export function useCitedRecords(conversation: ReaderConversation | undefined) {
  const [records, setRecords] = useState<Record<number, SemanticSearchResult>>({});
  const ids = [...new Set(conversation?.turns.flatMap(t => t.citations.map(c => c.record_id)) ?? [])];
  const missing = ids.filter(id => !(id in records)).sort((a, b) => a - b).join(",");
  useEffect(() => {
    if (!missing) return;
    let cancelled = false;
    void Promise.all(missing.split(",").map(Number).map(id => recordsApi.detail(id).then(({ data }) => ({
      id, title: data.title, abstract: data.abstract ?? "", score: 0,
      authors: (data.authors ?? []).map(a => a.name).join(", "),
      year: data.publication_year ?? null, classification: data.classification_name ?? null,
    } satisfies SemanticSearchResult)).catch(() => null))).then(found => {
      if (cancelled) return;
      setRecords(current => {
        const next = { ...current };
        for (const card of found) if (card) next[card.id] = card;
        return next;
      });
    });
    return () => { cancelled = true; };
  }, [missing]);
  return records;
}

function citations(turn: Turn, records: Record<number, SemanticSearchResult>): Citation[] {
  return turn.citations.map((c, index) => ({
    marker: index + 1, chunk_id: index, record_id: c.record_id, record_title: records[c.record_id]?.title ?? `Paper ${c.record_id}`,
    page: c.page, text: c.quote, context_path: [], regions: c.regions ?? [],
  }));
}

const ENDED: Partial<Record<ReaderRun["state"], EndedRunState>> = { cancelled: "cancelled", failed: "failed", expired: "expired" };
const ENDED_TEXT: Partial<Record<ReaderRun["state"], string>> = {
  cancelled: "Stopped before an answer was ready.",
  failed: "IRIS could not finish this question.",
  expired: "Research ran out of time before an answer was ready.",
  conflict: "This conversation changed while IRIS was answering. Ask again to continue.",
};

/** The transcript as the message list renders it: a question, then its answer or how it ended. */
export function toMessages(conversation: ReaderConversation | undefined, live: ReaderRun | undefined,
  records: Record<number, SemanticSearchResult>): ChatMessage[] {
  const runs = [...(conversation?.runs ?? [])];
  if (live && !runs.some(r => r.id === live.id)) runs.push(live);
  const out: ChatMessage[] = [];
  for (const stored of runs) {
    const run = stored.id === live?.id ? live : stored;
    if (compactionRun(run)) continue;
    const at = run.created_at ?? new Date().toISOString();
    out.push({ id: `q:${run.id}`, role: "user", content: run.question, createdAt: at });
    const turn = conversation?.turns.find(t => t.run_id === run.id);
    if (turn) {
      const cited = citations(turn, records);
      out.push({ id: `a:${run.id}`, role: "assistant", content: turn.answer, question: run.question,
        citations: cited, papers: turn.papers ?? [], sources: [...new Map(cited.map(c => [c.record_id, records[c.record_id]])).values()].filter(Boolean),
        createdAt: at });
    } else if (ENDED_TEXT[run.state]) {
      const ended = ENDED[run.state];
      out.push({ id: `a:${run.id}`, role: "assistant", content: ENDED_TEXT[run.state] ?? "", question: run.question,
        ...(ended ? { endedRun: { id: run.id, state: ended } } : {}), createdAt: at });
    }
  }
  return out;
}

/** Every run's reported usage in the conversation, summed. */
export function conversationTotals(conversation: ReaderConversation | undefined, live: ReaderRun | undefined) {
  const runs = [...(conversation?.runs ?? [])].map(r => (r.id === live?.id ? live : r));
  if (live && !runs.some(r => r.id === live.id)) runs.push(live);
  const usages = runs.map(r => r.usage).filter((u): u is ReaderUsage => !!u);
  return {
    latest: [...usages].reverse().find(u => u.calls > 0) ?? null,
    totalTokens: usages.reduce((sum, u) => sum + u.total_tokens, 0),
  };
}
