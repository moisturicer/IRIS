import { useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { conversationPath } from "@/lib/askHandoff";
import {
  answerReference,
  citedPage,
  landedAsPageContext,
  trustedCitation,
  type AnswerReturn,
} from "@/lib/citedPage";
import { useCitationReference } from "./useCitationReference";

/**
 * Landing on Paper View from a citation (IR-1269, moved out of the page
 * unchanged): which page to open at, the passage to draw, and the way back
 * to the answer it was followed from.
 *
 * `openPaperChat` opens this page's Paper Chat panel, the way back to an
 * answer Paper Chat gave.
 */
export function useCitationLanding(id: string | undefined, openPaperChat: () => void) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const location = useLocation();

  // A citation links here with `?page=` (IR-284), so acting on it lands on
  // the page that supports the claim rather than the paper's first. The
  // rules for reading that number live in `lib/citedPage`, testable without
  // standing up this screen.
  //
  // The answer it was followed from rides in the address as ids (IR-578).
  // A citation this page load carried is used as it is; any other -- after a
  // reload, from a restored tab -- is re-resolved through the reader's own
  // Conversation, and the page it reads now wins over the address's.
  const reference = answerReference(searchParams);
  const carried = trustedCitation(location.state, reference);
  const resolution = useCitationReference(carried ? null : reference, id ? Number(id) : null);
  const resolvedPage =
    resolution.status === "passage" ? resolution.citation.page
      : resolution.status === "changed" ? resolution.page
        : null;
  const openAtPage = resolvedPage ?? citedPage(searchParams.get("page"));
  // The reader lands once per navigation, so it waits for the re-read: a
  // landing on the address's page would not move again to the page it reads now.
  const landingPage = resolution.status === "loading" ? null : openAtPage;
  // Back to answer (IR-578): Ask IRIS's lives at its address; Paper Chat's is
  // this page's panel, opened on that conversation.
  const [chatReturn, setChatReturn] = useState<AnswerReturn | null>(null);
  const backToAnswer =
    reference && resolution.status !== "gone" && resolution.status !== "loading"
      ? () => {
          if (reference.from === "ask") {
            navigate(`${conversationPath(reference.conversationId)}?turn=${reference.turnId}`);
            return;
          }
          openPaperChat();
          setChatReturn((last) => ({
            conversationId: reference.conversationId,
            turnId: reference.turnId,
            key: (last?.key ?? 0) + 1,
          }));
        }
      : undefined;

  // A citation carries the exact chunk it points at as router `state`
  // (IR-335), so the reader draws its highlight with no second fetch. A
  // navigation this link did not originate -- a typed URL, a refresh, a
  // bookmark -- carries no state, and the reader still opens at `openAtPage`
  // with nothing to highlight, which is the same graceful case a passage
  // with no recovered regions already is.
  const navCitation = carried ?? (resolution.status === "passage" ? resolution.citation : null);
  // The Overview cites a page as a whole: only that page is marked (IR-578).
  const pageContext = landedAsPageContext(searchParams, location.state);

  return { resolution, openAtPage, landingPage, backToAnswer, chatReturn, navCitation, pageContext };
}
