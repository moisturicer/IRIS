/**
 * FR-M3-01 — Conversational RAG chatbot UI (SDD Module 3).
 *
 * Conversations are persisted server-side (IR-295) and read/written through
 * the same API Paper Chat uses (IR-298) -- there is one Conversation model
 * for both surfaces, not a local transcript glued into the question on every
 * turn. History travels as a `conversation_id`; a question is just a
 * question, and IRIS resolves what "its" refers to on the server.
 *
 * **Every conversation has its own address (IR-548)**,
 * `/ai/conversations/<id>`. `/ai` itself only decides which one to open --
 * the latest, a new one, a Record's (`?record=`) or one for a handed-off
 * draft -- and replaces itself with that address. Opening an address,
 * refreshing it, or moving back and forward loads the conversation through
 * the owner-scoped API, so the address grants nothing: someone else's reads
 * exactly like a missing one. A queued question still answering when the
 * page opens is followed again from its first event; one that ended without
 * its answer says so and offers Retry.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { conversationPath, useConsumeHandoff } from "@/lib/askHandoff";
import { aiApi } from "@/api/ai";
import { useUIStore } from "@/store/ui.store";
import type { ChatMessage } from "@/types/chat";
import type { AIStatus, ConversationDetail, ConversationSummary } from "@/types/ai";
import { recordsApi } from "@/api/records";
import { AskIrisMark } from "./components/AskIrisIcons";
import { ChatMessageList } from "./components/ChatMessageList";
import { ChatInput } from "./components/ChatInput";
import { ChatToolbar } from "./components/ChatToolbar";
import { ChatDrawer } from "./components/ChatDrawer";
import { ConversationHistoryList, ConversationSidebar } from "./components/ConversationSidebar";
import { SourceContextPanel, SourcePassages } from "./components/SourceContextPanel";
import { ASK_PANELS_INLINE_PX } from "./components/answerLayout";
import { useElementWidth } from "@/hooks/useElementWidth";
import { useConversationClient } from "./conversation/useConversationClient";

/** History or sources: the two panels that sit beside the answer, or open over it (IR-570). */
type AskPanel = "history" | "sources";

/** The composer's accessible name, and its placeholder where there is room. */
const FOLLOW_UP_LABEL = "Ask a follow-up about the research corpus…";

/** The address's conversation id: `undefined` at `/ai`, `null` if malformed. */
function parseConversationParam(raw: string | undefined): number | null | undefined {
  if (raw === undefined) return undefined;
  return /^[1-9]\d*$/.test(raw) ? Number(raw) : null;
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
  const recordParam = searchParams.get("record");
  const routeId = parseConversationParam(useParams().conversationId);
  const atIndex = routeId === undefined;
  const navigate = useNavigate();
  const addToast       = useUIStore((s) => s.addToast);
  const legacyNotice    = useLegacyConversationsNotice();
  const handoff         = useConsumeHandoff();

  const [conversations, setConversations]   = useState<ConversationSummary[]>([]);
  const [historyOpen, setHistoryOpen]       = useState(true);
  const [sourcesOpen, setSourcesOpen]       = useState(false);
  const [status, setStatus]                 = useState<AIStatus | null>(null);
  const [suggestions, setSuggestions]       = useState<string[]>([]);
  // Too narrow to hold history and sources beside the answer, they open one at
  // a time as drawers over it, closed until asked for (IR-570). Unmeasured
  // (jsdom, the first paint) counts as wide: the layout this page always had.
  const [observePage, pageWidth]            = useElementWidth<HTMLDivElement>();
  const panelsAsDrawers = pageWidth > 0 && pageWidth < ASK_PANELS_INLINE_PX;
  const [drawer, setDrawer]                 = useState<AskPanel | null>(null);
  // The toggle that opened the drawer, read as it is activated: once the page
  // behind goes inert the browser has already taken focus off it.
  const drawerOpener                        = useRef<HTMLElement | null>(null);
  /** Whether `panel` is showing: in its drawer, or as its column. */
  const panelShown = (panel: AskPanel) =>
    panelsAsDrawers ? drawer === panel : panel === "history" ? historyOpen : sourcesOpen;
  /** The toolbar's toggle: opens `panel`'s drawer, or shows or hides its column. */
  const togglePanel = (panel: AskPanel) => {
    if (!panelsAsDrawers) {
      (panel === "history" ? setHistoryOpen : setSourcesOpen)((v) => !v);
      return;
    }
    drawerOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDrawer(panel);
  };
  const refreshList = useCallback(async () => {
    const { data } = await aiApi.conversations.list();
    setConversations(data);
    return data;
  }, []);

  // Transcripts, drafts, selected answers and answers in flight, one set per
  // conversation, each answer bound to the conversation that asked (IR-562).
  const client = useConversationClient({
    onAnswered: (_conversationId, message, onScreen) => {
      if (onScreen && message.citations?.length) setSourcesOpen(true);
      refreshList();
    },
    onFailed: () => {
      addToast({
        type:    "error",
        message: "IRIS could not answer right now. Check that the AI service is available.",
      });
    },
  });
  const { activeId, unavailable, messages, selected } = client;
  const loading = client.isAnswering;

  // Read off the selected reply itself, so the panel cannot show one answer's
  // passages beside another, or one conversation's beside another's (IR-284,
  // IR-562). A newer answer that cited nothing shows that, not older sources.
  const citations = selected?.citations ?? [];
  const sources = selected?.sources ?? [];
  const sourcesAvailable = selected !== null;

  const activeTitle = unavailable
    ? "Conversation unavailable"
    : conversations.find((c) => c.id === activeId)?.title || "New chat";

  const { open, show, showUnavailable, isOnScreen, setDraftFor } = client;

  /** Shows `conversation` and makes its address the current one. */
  const goTo = useCallback(
    (conversation: ConversationDetail, replace = false, nextDraft: string | null = null) => {
      show(conversation);
      if (nextDraft) setDraftFor(conversation.id, nextDraft);
      navigate(conversationPath(conversation.id), {
        replace,
        // The draft also rides in router state, never the address (IR-559),
        // so reloading the conversation's address still finds it.
        state: nextDraft ? { draft: nextDraft } : null,
      });
    },
    [navigate, setDraftFor, show],
  );

  // `/ai` decides which conversation to open and replaces itself with its
  // address. An address that names one opens it in the effect below.
  useEffect(() => {
    let cancelled = false;
    const recordId = recordParam;

    (async () => {
      try {
        const list = await refreshList();
        if (cancelled || !atIndex) return;

        if (recordId) {
          // A draft scoped to the Record, never an ask: the reader sends it.
          const nextDraft = `Tell me about research record #${recordId} and summarize its key contributions.`;
          const { data: scoped } = await aiApi.conversations.list({ record: Number(recordId) });
          if (cancelled) return;
          const { data } = scoped.length > 0
            ? await aiApi.conversations.get(scoped[0].id)
            : await aiApi.conversations.create({ record: Number(recordId) });
          if (cancelled) return;
          goTo(data, true, nextDraft);
          return;
        }

        if (handoff) {
          // A handed-off question opens a new Conversation as an editable draft.
          const { data } = await aiApi.conversations.create();
          if (cancelled) return;
          goTo(data, true, handoff);
          return;
        }

        const { data } = list.length > 0
          ? await aiApi.conversations.get(list[0].id)
          : await aiApi.conversations.create();
        if (cancelled) return;
        goTo(data, true);
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
    // refreshList, goTo and the client's callbacks are stable across renders,
    // and `handoff` is read once on arrival — only the `record` query param, or arriving at `/ai`
    // itself, should re-run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordParam, atIndex]);

  // A draft that arrived with a conversation's own address -- a reload after
  // a handoff -- belongs to the first conversation that address opens.
  const routedDraft = useRef(atIndex ? null : handoff);

  // Opening an address: directly, on refresh, or by back and forward.
  useEffect(() => {
    if (routeId === undefined || (routeId !== null && isOnScreen(routeId))) return;
    if (routeId === null) {
      showUnavailable();
      return;
    }
    open(routeId)
      .then(() => {
        const draft = routedDraft.current;
        routedDraft.current = null;
        if (draft && isOnScreen(routeId)) setDraftFor(routeId, draft);
      })
      .catch(() => {
        addToast({
          type:    "error",
          message: "Could not load this conversation. Check that the AI service is available.",
        });
      });
  }, [routeId, isOnScreen, open, setDraftFor, showUnavailable, addToast]);

  // A drawer belongs to the layout that opened it, and to the conversation it
  // was opened over: widening the page or moving to another conversation (a
  // link in history, New chat) puts the answer back in front.
  useEffect(() => {
    setDrawer(null);
  }, [panelsAsDrawers, activeId]);

  // The sources column describes an answer in the conversation on screen, so
  // another conversation opens with it closed, until its own answer cites.
  useEffect(() => {
    setSourcesOpen(false);
  }, [activeId]);

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
        const names = (data.results ?? []).map((c) => c.name).slice(0, 4);
        const fromCatalogue = names.map((n) => `What research exists on ${n.toLowerCase()}?`);
        // Generic, catalogue-agnostic prompts fill out to 4 when there are
        // fewer than 4 classifications -- still safe to suggest since they
        // never assume a specific classification exists.
        const fallback = [
          "What research has been published at CIT-U?",
          "What are the most recent submissions?",
          "Summarize a thesis from the repository",
          "What departments have published research?",
        ];
        const combined = [...fromCatalogue, ...fallback.filter((p) => !fromCatalogue.includes(p))];
        setSuggestions(combined.slice(0, 4));
      })
      .catch(() => {});

    return () => { cancelled = true; };
  }, []);

  const handleNewChat = async () => {
    const { data } = await aiApi.conversations.create();
    goTo(data);
    refreshList();
  };

  const handleDelete = async (id: number) => {
    await aiApi.conversations.remove(id);
    client.forget(id);
    const list = await refreshList();
    if (isOnScreen(id) || unavailable) {
      const { data } = list.length > 0
        ? await aiApi.conversations.get(list[0].id)
        : await aiApi.conversations.create();
      // The deleted address must not come back with Back.
      goTo(data, true);
    }
    addToast({ type: "info", message: "Chat removed." });
  };

  const handleRetry = async (message: ChatMessage) => {
    try {
      await client.retry(message);
    } catch {
      addToast({ type: "error", message: "IRIS could not retry that question right now." });
    }
  };

  return (
    // `dvh`, not `vh`: the page is the height of what a phone shows, so the
    // composer stays above the software keyboard rather than under it (IR-570).
    <div ref={observePage} className="relative flex flex-col h-dvh bg-canvas overflow-hidden">
      <div
        className="flex flex-1 min-h-0 min-w-0 relative"
        // Behind an open drawer the page waits, so focus cannot wander to it.
        {...(drawer ? { inert: "" } : {})}
      >
        {!panelsAsDrawers && (
          <ConversationSidebar
            conversations={conversations}
            activeId={activeId}
            open={historyOpen}
            onDelete={handleDelete}
          />
        )}

        {/* Center: chat. The only `surface` white on the page (IR-570). */}
        <div className="flex flex-col flex-1 min-w-0 relative bg-surface">
          <ChatToolbar
            sessionTitle={activeTitle}
            historyOpen={panelShown("history")}
            sourcesOpen={panelShown("sources")}
            sourcesAvailable={sourcesAvailable}
            onToggleHistory={() => togglePanel("history")}
            onToggleSources={() => togglePanel("sources")}
            onNewChat={handleNewChat}
            asDrawers={panelsAsDrawers}
          />

          {legacyNotice.visible && (
            <div
              role="status"
              className="shrink-0 flex items-start gap-2 px-4 py-2 bg-stone-50 border-b border-stone-200 text-[13px] text-stone-600"
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
                <i className="fas fa-xmark text-[12px]" aria-hidden />
              </button>
            </div>
          )}

          {status?.disclosure_bypass && (
            <div
              role="status"
              className="shrink-0 flex items-start gap-2 px-4 py-2 bg-rose-50 border-b border-rose-200 text-[13px] text-rose-900"
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
            <div className="shrink-0 flex items-start gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-[13px] text-amber-800">
              <AskIrisMark className="w-4 h-4 shrink-0 mt-px" />
              <p>
                <strong>Retrieval-only mode.</strong> IRIS finds and ranks real passages, but no
                answering model is configured, so it will return sources rather than a written
                answer. Set <code className="font-mono">LLM_API_KEY</code> to enable synthesis.
              </p>
            </div>
          )}

          {unavailable ? (
            <div role="status" className="flex-1 flex items-center justify-center p-8 text-center">
              <div className="max-w-md">
                <h2 className="text-[20px] font-bold text-stone-900 mb-2">This conversation is not available.</h2>
                <p className="text-[15px] text-stone-500 leading-relaxed mb-5">
                  It may have been deleted, or the link may be wrong.
                </p>
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="rounded-lg bg-brand px-4 py-2 text-[14px] font-semibold text-white hover:bg-brand/90"
                >
                  Start a new chat
                </button>
              </div>
            </div>
          ) : (
            <ChatMessageList
              messages={messages}
              isLoading={loading}
              streaming={client.streaming}
              suggestions={suggestions}
              onSuggestion={client.send}
              indexedRecords={status?.indexed_records ?? null}
              onRetry={handleRetry}
              onStop={() => void client.stop()}
              selectedId={selected?.id ?? null}
              onSelectSources={(message) => {
                client.select(message.id);
                if (panelsAsDrawers) togglePanel("sources");
                else setSourcesOpen(true);
              }}
            />
          )}
          <ChatInput
            onSend={client.send}
            draft={client.draft}
            onDraftChange={client.setDraft}
            disabled={loading || !activeId}
            label={FOLLOW_UP_LABEL}
            // One line in a phone's composer; the name above stays whole.
            placeholder={panelsAsDrawers ? "Ask a follow-up…" : FOLLOW_UP_LABEL}
          />
        </div>

        {!panelsAsDrawers && (
          <SourceContextPanel
            open={sourcesOpen}
            citations={citations}
            sources={sources}
            question={selected?.question ?? null}
            onClose={() => setSourcesOpen(false)}
          />
        )}
      </div>

      {drawer === "history" && (
        <ChatDrawer
          title="Chat history"
          side="start"
          closeLabel="Close chat history"
          onClose={() => setDrawer(null)}
          returnTo={drawerOpener.current}
        >
          {/* The toolbar has no room for New chat on a phone; this is its place. */}
          <div className="shrink-0 px-3 pt-3">
            <button
              type="button"
              onClick={handleNewChat}
              className="w-full inline-flex items-center justify-center gap-2 min-h-11 px-3 rounded-lg border border-stone-200
                text-[14px] font-semibold text-stone-700 hover:bg-stone-50 hover:text-stone-900 transition-colors"
            >
              <i className="fas fa-plus text-[11px]" aria-hidden />
              New chat
            </button>
          </div>
          <ConversationHistoryList conversations={conversations} activeId={activeId} onDelete={handleDelete} />
        </ChatDrawer>
      )}
      {drawer === "sources" && (
        <ChatDrawer
          title="Referenced passages"
          description={selected?.question ? `For “${selected.question}”` : "The exact text behind the answer"}
          side="end"
          closeLabel="Hide sources panel"
          onClose={() => setDrawer(null)}
          returnTo={drawerOpener.current}
        >
          <SourcePassages citations={citations} sources={sources} answered={selected !== null} />
        </ChatDrawer>
      )}
    </div>
  );
}
