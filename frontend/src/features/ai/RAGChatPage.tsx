/**
 * FR-M3-01 — Conversational RAG chatbot UI (SDD Module 3).
 *
 * Conversations are persisted server-side (IR-295) and read/written through
 * the same API Paper Chat uses (IR-298) -- there is one Conversation model
 * for both surfaces, not a local transcript glued into the question on every
 * turn. History travels as a `conversation_id`; a question is just a
 * question, and IRIS resolves what "its" refers to on the server.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { aiApi } from "@/api/ai";
import { useUIStore } from "@/store/ui.store";
import { newChatMessage, turnToMessages } from "@/lib/chatMessages";
import type { ChatMessage } from "@/types/chat";
import type { AIStatus, ConversationSummary } from "@/types/ai";
import { recordsApi } from "@/api/records";
import { AskIrisMark } from "./components/AskIrisIcons";
import { ChatMessageList } from "./components/ChatMessageList";
import { ChatInput } from "./components/ChatInput";
import { ChatToolbar } from "./components/ChatToolbar";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { SourceContextPanel } from "./components/SourceContextPanel";

/** The most recent reply that cited anything — what the sources panel shows. */
function latestGrounded(messages: ChatMessage[]): ChatMessage | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "assistant" && m.citations && m.citations.length > 0) {
      return m;
    }
  }
  return null;
}

/**
 * The key chat history lived under before Conversations were persisted
 * server-side. Read only to decide whether to explain the sidebar emptying
 * (IR-298) -- what it held is demo and testing chats against a corpus of
 * stub files, not migrated (IR-294 §Further Notes).
 */
const LEGACY_STORAGE_KEY = "iris_rag_conversations";

function useLegacyConversationsNotice() {
  const [visible, setVisible] = useState(() => {
    try {
      return localStorage.getItem(LEGACY_STORAGE_KEY) !== null;
    } catch {
      return false;
    }
  });

  const dismiss = () => {
    try {
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
      /* per-browser convenience only */
    }
    setVisible(false);
  };

  return { visible, dismiss };
}

export default function RAGChatPage() {
  const [searchParams] = useSearchParams();
  const addToast       = useUIStore((s) => s.addToast);
  const legacyNotice    = useLegacyConversationsNotice();

  const [conversations, setConversations]   = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId]             = useState<number | null>(null);
  const [messages, setMessages]             = useState<ChatMessage[]>([]);
  const [loading, setLoading]               = useState(false);
  const [historyOpen, setHistoryOpen]       = useState(true);
  const [sourcesOpen, setSourcesOpen]       = useState(false);
  const [status, setStatus]                 = useState<AIStatus | null>(null);
  const [suggestions, setSuggestions]       = useState<string[]>([]);

  // Read off the reply itself, so the panel cannot show one conversation's
  // cards beside another's passages, and a reload restores both together
  // (IR-284). The panel used to fetch a record per citation; the answer has
  // already been told whose work each passage is.
  const grounded = useMemo(() => latestGrounded(messages), [messages]);
  const citations = grounded?.citations ?? [];
  const sources = grounded?.sources ?? [];
  const sourcesAvailable = citations.length > 0;

  const activeTitle =
    conversations.find((c) => c.id === activeId)?.title || "New chat";

  const refreshList = useCallback(async () => {
    const { data } = await aiApi.conversations.list();
    setConversations(data);
    return data;
  }, []);

  const loadConversation = useCallback(async (id: number) => {
    const { data } = await aiApi.conversations.get(id);
    setActiveId(id);
    setMessages(data.turns.flatMap(turnToMessages));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const recordId = searchParams.get("record");

    (async () => {
      try {
        const list = await refreshList();
        if (cancelled) return;

        if (recordId) {
          const prefill = `Tell me about research record #${recordId} and summarize its key contributions.`;
          const { data } = await aiApi.conversations.create({ record: Number(recordId) });
          if (cancelled) return;
          setActiveId(data.id);
          setMessages([newChatMessage("user", prefill)]);
          refreshList();
          return;
        }

        if (list.length > 0) {
          await loadConversation(list[0].id);
        } else {
          const { data } = await aiApi.conversations.create();
          if (cancelled) return;
          setActiveId(data.id);
          setMessages([]);
        }
      } catch {
        if (!cancelled) {
          addToast({
            type:    "error",
            message: "Could not load your conversations. Check that the AI service is available.",
          });
        }
      }
    })();

    return () => { cancelled = true; };
    // refreshList / loadConversation are stable (useCallback, no deps) —
    // only a change to the `record` query param should re-run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    let cancelled = false;

    aiApi
      .status()
      .then(({ data }) => !cancelled && setStatus(data))
      .catch(() => {});

    // Suggested prompts are built from classifications that actually exist,
    // so a suggestion never leads to an empty answer.
    recordsApi
      .classifications()
      .then(({ data }) => {
        if (cancelled) return;
        const names = (data.results ?? []).map((c) => c.name).slice(0, 3);
        setSuggestions(
          names.length > 0
            ? names.map((n) => `What research exists on ${n.toLowerCase()}?`)
            : ["What research has been published at CIT-U?"],
        );
      })
      .catch(() => {});

    return () => { cancelled = true; };
  }, []);

  const handleNewChat = async () => {
    const { data } = await aiApi.conversations.create();
    setActiveId(data.id);
    setMessages([]);
    setSourcesOpen(false);
    refreshList();
  };

  const handleSelect = async (id: number) => {
    await loadConversation(id);
    setSourcesOpen(false);
  };

  const handleDelete = async (id: number) => {
    await aiApi.conversations.remove(id);
    const list = await refreshList();
    if (activeId === id) {
      if (list.length > 0) {
        await loadConversation(list[0].id);
      } else {
        const { data } = await aiApi.conversations.create();
        setActiveId(data.id);
        setMessages([]);
      }
    }
    addToast({ type: "info", message: "Chat removed." });
  };

  const handleSend = async (text: string) => {
    if (!activeId) return;

    const userMsg = newChatMessage("user", text);
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);

    setLoading(true);
    try {
      const { data } = await aiApi.ask(text, { conversationId: activeId });
      const body =
        data.answer ?? data.message ?? "No readable sources matched that question.";
      // ADR-008: a reader is told when an answer came the slow way. Carried on
      // the message rather than spliced into its markdown, so the bubble
      // renders it as its own labelled note and a test can find it by name.
      const assistantMsg = newChatMessage("assistant", body, {
        citations: data.citations,
        sources:   data.sources,
        degraded:  data.degraded,
        widened:   data.widened,
      });
      setMessages([...nextMessages, assistantMsg]);
      if (data.citations?.length) {
        setSourcesOpen(true);
      }
      // The title names itself from the first question, and `updated_at`
      // reorders the sidebar -- both are the server's doing now.
      refreshList();
    } catch {
      addToast({
        type:    "error",
        message: "IRIS could not answer right now. Check that the AI service is available.",
      });
      setMessages(nextMessages);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen min-h-[480px] bg-[#FBFCFD]">
      <div className="flex flex-1 min-h-0 relative">
        <ConversationSidebar
          conversations={conversations}
          activeId={activeId}
          open={historyOpen}
          onSelect={handleSelect}
          onDelete={handleDelete}
        />

        {/* Center: chat */}
        <div className="flex flex-col flex-1 min-w-0 relative">
          <ChatToolbar
            sessionTitle={activeTitle}
            historyOpen={historyOpen}
            sourcesOpen={sourcesOpen}
            sourcesAvailable={sourcesAvailable}
            onToggleHistory={() => setHistoryOpen((v) => !v)}
            onToggleSources={() => setSourcesOpen((v) => !v)}
            onNewChat={handleNewChat}
          />

          {legacyNotice.visible && (
            <div
              role="status"
              className="shrink-0 flex items-start gap-2 px-4 py-2 bg-stone-50 border-b border-stone-200 text-[11px] text-stone-600"
            >
              <AskIrisMark className="w-4 h-4 shrink-0 mt-px" />
              <p className="flex-1">
                <strong>Your previous chats are gone.</strong> They were stored only in this
                browser and are not carried over now that conversations are saved to your
                account.
              </p>
              <button
                type="button"
                onClick={legacyNotice.dismiss}
                aria-label="Dismiss"
                className="text-stone-400 hover:text-stone-700 shrink-0"
              >
                <i className="fas fa-xmark text-[11px]" aria-hidden />
              </button>
            </div>
          )}

          {status?.disclosure_bypass && (
            <div
              role="status"
              className="shrink-0 flex items-start gap-2 px-4 py-2 bg-rose-50 border-b border-rose-200 text-[11px] text-rose-900"
            >
              <AskIrisMark className="w-4 h-4 shrink-0 mt-px" />
              <p>
                <strong>Development mode: disclosure gate bypassed.</strong> Answers are drawn
                from content that no embargo check cleared, so this is not how a deployment
                behaves. Development only.
              </p>
            </div>
          )}

          {status && !status.generative && (
            <div className="shrink-0 flex items-start gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-[11px] text-amber-800">
              <AskIrisMark className="w-4 h-4 shrink-0 mt-px" />
              <p>
                <strong>Retrieval-only mode.</strong> IRIS finds and ranks real passages, but no
                answering model is configured, so it will return sources rather than a written
                answer. Set <code className="font-mono">LLM_API_KEY</code> to enable synthesis.
              </p>
            </div>
          )}

          <ChatMessageList
            messages={messages}
            isLoading={loading}
            showInlineSources={!sourcesOpen}
            suggestions={suggestions}
            onSuggestion={handleSend}
            indexedRecords={status?.indexed_records ?? null}
          />
          <ChatInput
            onSend={handleSend}
            disabled={loading || !activeId}
            placeholder="Ask a follow-up about the research corpus…"
          />
        </div>

        <SourceContextPanel
          open={sourcesOpen}
          citations={citations}
          sources={sources}
          onClose={() => setSourcesOpen(false)}
        />
      </div>
    </div>
  );
}
