/**
 * Ask IRIS (FR-M3-01). Every question is answered by the AI runtime (IR-957):
 * `/ai` starts a conversation and `/ai/conversations/<uuid>` reopens one.
 *
 * A numeric address is a Conversation Django answered before the switch. It
 * opens read-only (`EarlierConversation`), so nothing a reader asked is lost,
 * and continuing it means asking again here.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useConsumeHandoff } from "@/lib/askHandoff";
import { isAxiosError } from "axios";
import { runtimeReader, TITLE_TOO_LONG, type ReaderConversationSummary } from "@/api/runtimeReader";
import { usePageTitle } from "@/hooks/useDocumentTitle";
import { useUIStore } from "@/store/ui.store";
import { useElementWidth } from "@/hooks/useElementWidth";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { RuntimeReader } from "./components/RuntimeReader";
import { EarlierConversation } from "./components/EarlierConversations";
import { ChatToolbar } from "./components/ChatToolbar";
import { ChatDrawer } from "./components/ChatDrawer";
import { SourcesPanel, type SourcesMode } from "./components/SourcesPanel";
import type { ChatMessage } from "@/types/chat";
import {
  ConversationHistoryList, ConversationSidebar, NewChatButton, SIDEBAR_DEFAULT, SIDEBAR_MAX, SIDEBAR_MIN,
  type RenameConversation,
} from "./components/ConversationSidebar";
import { ASK_PHONE_MAX_PX, ASK_SOURCES_BESIDE_MIN_PX } from "./components/answerLayout";
import { useConversationHistory } from "./hooks/useConversationHistory";

const RUNTIME_ID = /^[0-9a-f-]{36}$/i;
const SIDEBAR_KEY = "iris-ask-sidebar-width";
const PANE_KEY = "iris-ask-pane";

/** The reader's last choice for the conversations pane; blocked storage means open. */
function readPaneOpen() {
  try {
    return localStorage.getItem(PANE_KEY) !== "closed";
  } catch {
    return true;
  }
}
function savePaneOpen(open: boolean) {
  try { localStorage.setItem(PANE_KEY, open ? "open" : "closed"); } catch { /* per-browser convenience */ }
}

function readSidebarWidth() {
  try {
    const stored = Number(localStorage.getItem(SIDEBAR_KEY));
    return stored >= SIDEBAR_MIN && stored <= SIDEBAR_MAX ? stored : SIDEBAR_DEFAULT;
  } catch {
    return SIDEBAR_DEFAULT;
  }
}
const EARLIER_ID = /^[1-9]\d*$/;

export default function RAGChatPage() {
  const rawId = useParams().conversationId;
  if (rawId && EARLIER_ID.test(rawId) && Number.isSafeInteger(Number(rawId))) {
    return <EarlierConversation id={Number(rawId)} />;
  }
  if (rawId && !RUNTIME_ID.test(rawId)) {
    return <p role="alert" className="p-6">This conversation could not be opened.</p>;
  }
  return <RuntimeAskPage />;
}

function RuntimeAskPage() {
  const { conversationId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const draft = useConsumeHandoff();
  const addToast = useUIStore(s => s.addToast);
  const rawRecord = params.get("record");
  const recordId = rawRecord && /^[1-9]\d*$/.test(rawRecord) ? Number(rawRecord) : undefined;
  const api = useMemo(() => runtimeReader(), []);

  const { conversations, setConversations, refresh: refreshList, titleOf, retitle, search } = useConversationHistory(api, conversationId);
  const [sidebarWidth, setSidebarWidth] = useState(readSidebarWidth);
  const resizeSidebar = (width: number) => {
    setSidebarWidth(width);
    try { localStorage.setItem(SIDEBAR_KEY, String(width)); } catch { /* per-browser convenience */ }
  };
  const [deleteTarget, setDeleteTarget] = useState<ReaderConversationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [observePage, pageWidth] = useElementWidth<HTMLDivElement>();

  // The conversations pane (IR-1233). Beside the chat it pushes it over, open or
  // closed to a strip, and the choice is kept per browser. On a phone it is a
  // dialog over the chat instead, closed whenever the page is.
  const phone = pageWidth > 0 && pageWidth <= ASK_PHONE_MAX_PX;
  const paneId = useId();
  const [paneOpen, setPaneOpen] = useState(readPaneOpen);
  const [dialogOpen, setDialogOpen] = useState(false);
  const dialogOpener = useRef<HTMLElement | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [searchAsked, setSearchAsked] = useState(0);
  const paneShown = phone ? dialogOpen : paneOpen;

  useEffect(() => { setDialogOpen(false); }, [conversationId, phone]);

  // The Sources panel (IR-1237): closed until a chip, the count or the header toggle
  // opens it. It describes the answer a reader picked, else the newest one; `marker`
  // is the passage it highlights, none when it was opened from the count or the toggle.
  const sourcesId = useId();
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [latest, setLatest] = useState<ChatMessage | null>(null);
  const [picked, setPicked] = useState<{ message: ChatMessage; marker: number | null } | null>(null);
  const sourcesOpener = useRef<HTMLElement | null>(null);
  const sourcesMode: SourcesMode = phone ? "sheet" : pageWidth > 0 && pageWidth < ASK_SOURCES_BESIDE_MIN_PX ? "over" : "beside";
  const shown = picked?.message ?? latest;
  // Another conversation has other answers: nothing carries over.
  useEffect(() => { setPicked(null); setLatest(null); }, [conversationId]);
  const rememberOpener = () => {
    sourcesOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  };
  const openSources = useCallback((message: ChatMessage, marker: number | null) => {
    rememberOpener();
    setPicked({ message, marker });
    setSourcesOpen(true);
  }, []);
  const toggleSources = () => {
    if (sourcesOpen) { setSourcesOpen(false); return; }
    rememberOpener();
    setPicked(p => p && { ...p, marker: null });
    setSourcesOpen(true);
  };
  const sourcesDialog = sourcesOpen && sourcesMode !== "beside";

  const setPane = useCallback((open: boolean) => { setPaneOpen(open); savePaneOpen(open); }, []);
  const openDialog = useCallback(() => {
    dialogOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDialogOpen(true);
  }, []);

  // Search from a closed pane (the strip's Search, or Ctrl+K) opens it first.
  const openSearch = useCallback(() => {
    if (phone) openDialog(); else setPane(true);
    setSearchAsked(n => n + 1);
  }, [phone, openDialog, setPane]);
  // `preventScroll`: the pane is still narrowing or widening, and a focus that
  // scrolled its clipped box sideways would leave the list shifted.
  useEffect(() => { if (searchAsked > 0) searchRef.current?.focus({ preventScroll: true }); }, [searchAsked]);
  // While the pane is shown the list takes Ctrl+K itself; here it is closed.
  useEffect(() => {
    if (paneShown) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paneShown, openSearch]);

  // A conversation names the tab with its own title (IR-1073); a new chat keeps "Ask IRIS".
  usePageTitle(titleOf(conversationId));

  if (rawRecord !== null && (!recordId || !Number.isSafeInteger(recordId))) {
    return <p role="alert" className="p-6">This paper could not be opened.</p>;
  }

  const title = titleOf(conversationId) || "New chat";
  const newChat = () => navigate("/ai");

  const rename: RenameConversation = async (id, next) => {
    try {
      retitle(id, await api.rename(id, next));
      return null;
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 422) return TITLE_TOO_LONG;
      return "Could not rename this conversation. Try again.";
    }
  };

  const remove = async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true); setDeleteError(null);
    try {
      await api.remove(deleteTarget.id);
      setConversations(all => all.filter(c => c.id !== deleteTarget.id));
      if (deleteTarget.id === conversationId) navigate("/ai", { replace: true });
      setDeleteTarget(null);
      addToast({ type: "info", message: "Chat removed." });
    } catch {
      setDeleteError("Could not delete this conversation. Please try again.");
    } finally { setDeleting(false); }
  };


  return <div ref={observePage} className="relative flex h-full min-h-0 flex-col overflow-hidden bg-canvas">
    <div className="relative flex min-h-0 min-w-0 flex-1" {...(dialogOpen || sourcesDialog ? { inert: "" } : {})}>
      {!phone && <ConversationSidebar id={paneId} conversations={conversations} activeId={conversationId ?? null}
        open={paneOpen} search={search} searchRef={searchRef} onNewChat={newChat} onSearch={openSearch}
        onToggle={() => setPane(!paneOpen)}
        onRename={rename} width={sidebarWidth} onResize={resizeSidebar}
        onDelete={id => setDeleteTarget(conversations.find(c => c.id === id) ?? null)} />}
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-surface">
        <ChatToolbar sessionTitle={title}
          phoneHistory={phone ? { open: dialogOpen, onOpen: openDialog } : undefined}
          sources={{ open: sourcesOpen, onToggle: toggleSources, controls: sourcesId, asDialog: sourcesMode !== "beside" }}
          onDownload={conversationId ? () => api.download(conversationId) : undefined} />
        <div className="flex min-h-0 flex-1 flex-col">
          <RuntimeReader key={`${recordId}:${conversationId}`} conversationId={conversationId} recordId={recordId}
            initialDraft={conversationId ? undefined : draft ?? undefined}
            sourcePanel={{ selectedId: sourcesOpen ? shown?.id ?? null : null, marker: picked?.marker ?? null, onOpen: openSources }}
            onAnswered={message => { setLatest(message); void refreshList(); }}
            onTitle={retitle}
            onConversation={id => {
              void refreshList();
              if (id !== conversationId) navigate(`/ai/conversations/${id}${recordId ? `?record=${recordId}` : ""}`, { replace: true });
            }} />
        </div>
      </div>
      {sourcesOpen && sourcesMode === "beside" && <SourcesPanel mode="beside" id={sourcesId} citations={shown?.citations ?? []}
        sources={shown?.sources ?? []} active={picked?.marker ?? null} question={shown?.question ?? null}
        onClose={() => setSourcesOpen(false)} returnTo={null} />}
    </div>

    {sourcesDialog && <SourcesPanel mode={sourcesMode} id={sourcesId} citations={shown?.citations ?? []}
      sources={shown?.sources ?? []} active={picked?.marker ?? null} question={shown?.question ?? null}
      onClose={() => setSourcesOpen(false)} returnTo={sourcesOpener.current} />}

    {phone && dialogOpen && <ChatDrawer title="Chat history" side="start" closeLabel="Close chat history"
      onClose={() => setDialogOpen(false)} returnTo={dialogOpener.current}>
      <div className="flex shrink-0 px-3 pt-3">
        <NewChatButton onClick={() => { setDialogOpen(false); newChat(); }} />
      </div>
      <ConversationHistoryList conversations={conversations} activeId={conversationId ?? null} search={search}
        searchRef={searchRef}
        onRename={rename} onDelete={id => { setDialogOpen(false); setDeleteTarget(conversations.find(c => c.id === id) ?? null); }} />
    </ChatDrawer>}
    <ConfirmDialog open={deleteTarget !== null} title="Delete conversation?"
      message={`Delete “${deleteTarget?.title || "New conversation"}” and its messages? This cannot be undone.`}
      confirmLabel="Delete conversation" danger focusCancel confirming={deleting} error={deleteError}
      onCancel={() => setDeleteTarget(null)} onConfirm={() => void remove()} />
  </div>;
}
