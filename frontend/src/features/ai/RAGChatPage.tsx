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
import type { AIStatus } from "@/types/ai";
import { recordsApi } from "@/api/records";
import { AskIrisMark } from "./components/AskIrisIcons";
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
  const [status, setStatus]                 = useState<AIStatus | null>(null);
  const [suggestions, setSuggestions]       = useState<string[]>([]);

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
      const body =
        data.answer ??
        data.message ??
        "No published record matched that question.";
      const assistantMsg = newMessage("assistant", body, data.citations);
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

          {status && !status.generative && (
            <div className="shrink-0 flex items-start gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-[11px] text-amber-800">
              <AskIrisMark className="w-4 h-4 shrink-0 mt-px" />
              <p>
                <strong>Retrieval-only mode.</strong> IRIS ranks and quotes real records but no
                language model is configured, so answers are not written prose. Set{" "}
                <code className="font-mono">ANTHROPIC_API_KEY</code> to enable synthesis.
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
          citationIds={citationIds}
          onClose={() => setSourcesOpen(false)}
        />
      </div>
    </div>
  );
}
