/**
 * FR-M3-01 — Conversational RAG chatbot UI (SDD Module 3).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { aiApi } from "@/api/ai";
import {
  buildRagQuestion,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  saveConversation,
  titleFromFirstMessage,
} from "@/lib/chatStorage";
import { useUIStore } from "@/store/ui.store";
import type { ChatMessage, Conversation } from "@/types/chat";
import { ChatMessageList } from "./components/ChatMessageList";
import { ChatInput } from "./components/ChatInput";
import { ChatToolbar } from "./components/ChatToolbar";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { SourceContextPanel } from "./components/SourceContextPanel";

function newMessage(role: ChatMessage["role"], content: string, citations?: number[]): ChatMessage {
  return {
    id:        crypto.randomUUID(),
    role,
    content,
    citations,
    createdAt: new Date().toISOString(),
  };
}

function latestCitationIds(messages: ChatMessage[]): number[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "assistant" && m.citations && m.citations.length > 0) {
      return m.citations;
    }
  }
  return [];
}

export default function RAGChatPage() {
  const [searchParams] = useSearchParams();
  const addToast       = useUIStore((s) => s.addToast);

  const [conversations, setConversations]   = useState<Conversation[]>([]);
  const [activeId, setActiveId]             = useState<string | null>(null);
  const [messages, setMessages]             = useState<ChatMessage[]>([]);
  const [loading, setLoading]               = useState(false);
  const [historyOpen, setHistoryOpen]       = useState(true);
  const [sourcesOpen, setSourcesOpen]       = useState(false);

  const citationIds = useMemo(() => latestCitationIds(messages), [messages]);
  const sourcesAvailable = citationIds.length > 0;

  const activeTitle =
    conversations.find((c) => c.id === activeId)?.title ?? "New chat";

  const refreshList = useCallback(() => {
    setConversations(listConversations());
  }, []);

  const loadConversation = useCallback((id: string) => {
    const c = getConversation(id);
    if (c) {
      setActiveId(id);
      setMessages(c.messages);
    }
  }, []);

  useEffect(() => {
    const recordId = searchParams.get("record");
    refreshList();

    if (recordId) {
      const prefill = `Tell me about research record #${recordId} and summarize its key contributions.`;
      const userMsg = newMessage("user", prefill);
      const c: Conversation = {
        id:        crypto.randomUUID(),
        title:     titleFromFirstMessage(prefill),
        messages:  [userMsg],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      saveConversation(c);
      refreshList();
      setActiveId(c.id);
      setMessages([userMsg]);
      return;
    }

    const existing = listConversations();
    if (existing.length > 0) {
      loadConversation(existing[0].id);
    } else {
      const c = createConversation();
      refreshList();
      setActiveId(c.id);
      setMessages([]);
    }
  }, [searchParams, refreshList, loadConversation]);

  const persist = (convId: string, nextMessages: ChatMessage[], title?: string) => {
    const existing = getConversation(convId);
    if (!existing) return;
    saveConversation({
      ...existing,
      messages: nextMessages,
      title: title ?? existing.title,
    });
    refreshList();
  };

  const handleNewChat = () => {
    const c = createConversation();
    refreshList();
    setActiveId(c.id);
    setMessages([]);
    setSourcesOpen(false);
  };

  const handleSelect = (id: string) => {
    loadConversation(id);
    setSourcesOpen(false);
  };

  const handleDelete = (id: string) => {
    deleteConversation(id);
    refreshList();
    if (activeId === id) {
      const remaining = listConversations();
      if (remaining.length > 0) {
        loadConversation(remaining[0].id);
      } else {
        const c = createConversation();
        refreshList();
        setActiveId(c.id);
        setMessages([]);
      }
    }
    addToast({ type: "info", message: "Chat removed." });
  };

  const handleSend = async (text: string) => {
    if (!activeId) return;

    const userMsg = newMessage("user", text);
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);

    const conv = getConversation(activeId!);
    const title =
      conv && conv.messages.length === 0 ? titleFromFirstMessage(text) : conv?.title ?? "New chat";
    persist(activeId!, nextMessages, title);

    setLoading(true);
    try {
      const { data } = await aiApi.ask(buildRagQuestion(nextMessages));
      const assistantMsg = newMessage("assistant", data.answer ?? "", data.citations);
      const withReply = [...nextMessages, assistantMsg];
      setMessages(withReply);
      persist(activeId!, withReply, title);
      if (data.citations?.length) {
        setSourcesOpen(true);
      }
    } catch {
      addToast({
        type:    "error",
        message: "IRIS could not answer right now. Check that the AI service is available.",
      });
      setMessages(nextMessages);
      persist(activeId, nextMessages, title);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="-m-6 flex flex-col h-[calc(100vh-3.5rem)] min-h-[480px] bg-[#FAFAF9]">
      <div className="flex flex-1 min-h-0 relative">
        <ConversationSidebar
          conversations={conversations}
          activeId={activeId}
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
          onSelect={handleSelect}
          onNew={handleNewChat}
          onDelete={handleDelete}
        />

        {/* Center: chat */}
        <div className="flex flex-col flex-1 min-w-0 relative">
          {!historyOpen && (
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              className="absolute left-3 top-3 z-10 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg
                bg-white border border-stone-200 shadow-sm text-[11px] font-semibold text-stone-600
                hover:border-[#6B0F12]/30 hover:text-[#6B0F12]"
              aria-label="Show chat history"
            >
              <i className="fas fa-clock-rotate-left text-[11px]" />
              History
            </button>
          )}

          <ChatToolbar
            sessionTitle={activeTitle}
            historyOpen={historyOpen}
            sourcesOpen={sourcesOpen}
            sourcesAvailable={sourcesAvailable}
            onToggleHistory={() => setHistoryOpen((v) => !v)}
            onToggleSources={() => setSourcesOpen((v) => !v)}
            onNewChat={handleNewChat}
          />

          <ChatMessageList
            messages={messages}
            isLoading={loading}
            showInlineSources={!sourcesOpen}
          />
          <ChatInput
            onSend={handleSend}
            disabled={loading || !activeId}
            placeholder="Ask a follow-up about the research corpus…"
          />
        </div>

        <SourceContextPanel
          open={sourcesOpen}
          citationIds={citationIds}
          onClose={() => setSourcesOpen(false)}
        />
      </div>
    </div>
  );
}
