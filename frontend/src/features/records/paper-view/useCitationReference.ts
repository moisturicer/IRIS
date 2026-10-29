/**
 * A citation re-resolved from the address it landed with (IR-578).
 *
 * A citation followed in this page load carries itself as router state, and
 * the paper view draws its highlight with no fetch (IR-335). After a reload,
 * or from a restored tab, that state is not trusted: the address names the
 * reader's own Conversation, the Turn and the citation's marker, ids only,
 * and this asks the owner-scoped Conversation API for the Turn as it reads
 * now. The backend re-resolves every stored citation against the reader
 * (`conversations.turns_for_reader`): a Record they lost is dropped, a
 * re-chunked passage comes back as a record-level pointer with no regions.
 * So nothing here can highlight what the reader may no longer see, or draw a
 * rectangle from another Manuscript version.
 */
import { useEffect, useState } from "react";

import { aiApi } from "@/api/ai";
import { hasCitationQuote, type AnswerReference } from "@/lib/citedPage";
import type { Citation } from "@/types/ai";

export type CitationResolution =
  /** Nothing to re-resolve: no reference, or a trusted citation in hand. */
  | { status: "none" }
  | { status: "loading" }
  /** The passage as it reads now, regions included. */
  | { status: "passage"; citation: Citation }
  /** Still this Record, but the passage changed since; `page` is where it was. */
  | { status: "changed"; page: number | null }
  /** The answer is there, but this citation is not one of its readable ones. */
  | { status: "missing" }
  /** The citation is there, but points at another paper than this one. */
  | { status: "elsewhere" }
  /** No such Conversation or Turn for this reader: there is no answer to go back to. */
  | { status: "gone" };

export function useCitationReference(
  reference: AnswerReference | null,
  recordId: number | null,
): CitationResolution {
  const [resolution, setResolution] = useState<CitationResolution>({ status: "none" });
  const conversationId = reference?.conversationId ?? null;
  const turnId = reference?.turnId ?? null;
  const marker = reference?.marker ?? null;

  useEffect(() => {
    if (conversationId == null || turnId == null || recordId == null) {
      setResolution({ status: "none" });
      return;
    }
    let cancelled = false;
    setResolution({ status: "loading" });
    aiApi.conversations
      .get(conversationId)
      .then(({ data }) => {
        if (cancelled) return;
        const turn = data.turns.find((t) => t.id === turnId);
        if (!turn) return setResolution({ status: "gone" });
        if (marker == null) return setResolution({ status: "none" });
        const citation = turn.citations.find((c) => c.marker === marker);
        if (!citation) return setResolution({ status: "missing" });
        // A citation into another Record does not belong on this page.
        if (citation.record_id !== recordId) return setResolution({ status: "elsewhere" });
        setResolution(
          hasCitationQuote(citation)
            ? { status: "passage", citation }
            : { status: "changed", page: citation.page },
        );
      })
      .catch(() => {
        // Someone else's Conversation reads exactly like a missing one.
        if (!cancelled) setResolution({ status: "gone" });
      });
    return () => { cancelled = true; };
  }, [conversationId, turnId, marker, recordId]);

  return resolution;
}
