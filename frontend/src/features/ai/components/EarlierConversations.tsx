/**
 * Conversations Django answered before Ask IRIS moved to the AI runtime (IR-957).
 *
 * They stay readable, through the same owner-scoped API as before, so someone
 * else's reads as missing. They cannot be continued: Django no longer answers.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { aiApi } from "@/api/ai";
import { conversationPath } from "@/lib/askHandoff";
import { CitationConversationContext } from "@/lib/citedPage";
import { newChatMessage, turnToMessages } from "@/lib/chatMessages";
import { readFailureKind } from "@/lib/readFailure";
import type { ChatMessage } from "@/types/chat";
import type { ConversationDetail, ConversationSummary } from "@/types/ai";
import { ChatMessageList } from "./ChatMessageList";

const UNANSWERED =
  "This question ended without an answer when Ask IRIS changed how it answers. Ask it again in a new conversation.";

/** The Turns, then a question that was still waiting when Django stopped answering. */
export function earlierTranscript(conversation: ConversationDetail): ChatMessage[] {
  const messages = conversation.turns.flatMap(turnToMessages);
  const run = conversation.latest_run;
  if (run) {
    messages.push(newChatMessage("user", run.question));
    messages.push(newChatMessage("assistant", UNANSWERED, { question: run.question }));
  }
  return messages;
}

export function EarlierConversation({ id }: { id: number }) {
  const [conversation, setConversation] = useState<ConversationDetail>();
  const [failure, setFailure] = useState<"unavailable" | "failed">();

  useEffect(() => {
    let current = true;
    setConversation(undefined); setFailure(undefined);
    aiApi.conversations.get(id).then(
      ({ data }) => { if (current) setConversation(data); },
      (error) => { if (current) setFailure(readFailureKind(error) === "unavailable" ? "unavailable" : "failed"); },
    );
    return () => { current = false; };
  }, [id]);

  return <div className="flex h-full min-h-0 flex-col">
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-stone-200 px-6 py-4">
      <div className="min-w-0">
        <h1 className="font-display text-2xl text-stone-900 break-words">{conversation?.title || "Earlier conversation"}</h1>
        <p className="text-sm text-stone-600">An earlier conversation. You can read it here; to continue, ask in a new conversation.</p>
      </div>
      <Link to="/ai" className="inline-flex min-h-11 items-center text-sm text-brand underline">New conversation</Link>
    </header>
    {failure === "unavailable" && <p role="alert" className="p-6">This conversation is not available. It may have been deleted, or the link may be wrong.</p>}
    {failure === "failed" && <p role="alert" className="p-6">This conversation could not be loaded. Reload the page to try again.</p>}
    {!conversation && !failure && <p role="status" className="p-6 text-sm text-stone-600">Opening conversation…</p>}
    {conversation && <CitationConversationContext.Provider value={conversation.id}>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ChatMessageList messages={earlierTranscript(conversation)} isLoading={false} />
      </div>
    </CitationConversationContext.Provider>}
  </div>;
}

/** Links to the reader's earlier conversations, shown only when there are any. */
export function EarlierConversationList() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  useEffect(() => {
    let current = true;
    aiApi.conversations.list().then(({ data }) => { if (current) setConversations(data); }, () => undefined);
    return () => { current = false; };
  }, []);

  if (conversations.length === 0) return null;
  return <details className="shrink-0 border-t border-stone-200 px-3 py-2 text-sm">
    <summary className="min-h-11 cursor-pointer py-2 text-stone-700">Earlier conversations ({conversations.length})</summary>
    <ul className="mt-2 space-y-1">
      {conversations.map(c => <li key={c.id} className="min-w-0">
        <Link to={conversationPath(c.id)} className="inline-flex min-h-11 items-center break-words text-brand underline [overflow-wrap:anywhere]">
          {c.title || "Untitled conversation"}
        </Link>
      </li>)}
    </ul>
  </details>;
}
