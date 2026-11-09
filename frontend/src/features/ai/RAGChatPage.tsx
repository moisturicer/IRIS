/**
 * Ask IRIS (FR-M3-01). Every question is answered by the AI runtime (IR-957):
 * `/ai` starts a conversation and `/ai/conversations/<uuid>` reopens one.
 *
 * A numeric address is a Conversation Django answered before the switch. It
 * opens read-only (`EarlierConversation`), so nothing a reader asked is lost,
 * and continuing it means asking again here.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useConsumeHandoff } from "@/lib/askHandoff";
import { runtimeReader, type ReaderConversationSummary } from "@/api/runtimeReader";
import { useUIStore } from "@/store/ui.store";
import { useElementWidth } from "@/hooks/useElementWidth";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { RuntimeReader } from "./components/RuntimeReader";
import { EarlierConversation } from "./components/EarlierConversations";
import { ChatToolbar } from "./components/ChatToolbar";
import { ChatDrawer } from "./components/ChatDrawer";
import { ConversationHistoryList, ConversationSidebar, NewChatButton } from "./components/ConversationSidebar";
import { ASK_PANELS_INLINE_PX } from "./components/answerLayout";

const RUNTIME_ID = /^[0-9a-f-]{36}$/i;
const EARLIER_ID = /^[1-9]\d*$/;

type AskPanel = "history";

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

  const [conversations, setConversations] = useState<ReaderConversationSummary[]>([]);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<ReaderConversationSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [observePage, pageWidth] = useElementWidth<HTMLDivElement>();
  const asDrawers = pageWidth > 0 && pageWidth < ASK_PANELS_INLINE_PX;
  const [drawer, setDrawer] = useState<AskPanel | null>(null);
  const drawerOpener = useRef<HTMLElement | null>(null);

  const refreshList = useCallback(async () => {
    try { setConversations(await api.list()); } catch { /* the list is a convenience; the reader still works */ }
  }, [api]);
  useEffect(() => { void refreshList(); }, [refreshList, conversationId]);
  useEffect(() => { setDrawer(null); }, [conversationId]);
  useEffect(() => { setDrawer(null); }, [asDrawers]);

  const shown = (panel: AskPanel) => asDrawers ? drawer === panel : historyOpen;
  const toggle = (panel: AskPanel) => {
    if (!asDrawers) { setHistoryOpen(v => !v); return; }
    drawerOpener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDrawer(panel);
  };

  if (rawRecord !== null && (!recordId || !Number.isSafeInteger(recordId))) {
    return <p role="alert" className="p-6">This paper could not be opened.</p>;
  }

  const title = conversations.find(c => c.id === conversationId)?.title || "New chat";
  const newChat = () => navigate("/ai");

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
    <div className="relative flex min-h-0 min-w-0 flex-1" {...(drawer ? { inert: "" } : {})}>
      {!asDrawers && <ConversationSidebar conversations={conversations} activeId={conversationId ?? null}
        open={historyOpen} onNewChat={newChat}
        onDelete={id => setDeleteTarget(conversations.find(c => c.id === id) ?? null)} />}
      <div className="relative flex min-w-0 flex-1 flex-col bg-surface">
        <ChatToolbar sessionTitle={title} historyOpen={shown("history")}
          onToggleHistory={() => toggle("history")} asDrawers={asDrawers} />
        <div className="min-h-0 flex-1">
          <RuntimeReader key={`${recordId}:${conversationId}`} conversationId={conversationId} recordId={recordId}
            initialDraft={conversationId ? undefined : draft ?? undefined}
            onAnswered={() => void refreshList()}
            onConversation={id => {
              void refreshList();
              if (id !== conversationId) navigate(`/ai/conversations/${id}${recordId ? `?record=${recordId}` : ""}`, { replace: true });
            }} />
        </div>
      </div>
    </div>

    {drawer === "history" && <ChatDrawer title="Chat history" side="start" closeLabel="Close chat history"
      onClose={() => setDrawer(null)} returnTo={drawerOpener.current}>
      <div className="shrink-0 px-3 pt-3">
        <NewChatButton onClick={() => { setDrawer(null); newChat(); }} />
      </div>
      <ConversationHistoryList conversations={conversations} activeId={conversationId ?? null}
        onDelete={id => { setDrawer(null); setDeleteTarget(conversations.find(c => c.id === id) ?? null); }} />
    </ChatDrawer>}
    <ConfirmDialog open={deleteTarget !== null} title="Delete conversation?"
      message={`Delete “${deleteTarget?.title || "New conversation"}” and its messages? This cannot be undone.`}
      confirmLabel="Delete conversation" danger focusCancel confirming={deleting} error={deleteError}
      onCancel={() => setDeleteTarget(null)} onConfirm={() => void remove()} />
  </div>;
}
