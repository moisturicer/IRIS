/**
 * Ask IRIS (FR-M3-01). Every question is answered by the AI runtime (IR-957):
 * `/ai` starts a conversation and `/ai/conversations/<uuid>` reopens one.
 *
 * A numeric address is a Conversation Django answered before the switch. It
 * opens read-only (`EarlierConversation`), so nothing a reader asked is lost,
 * and continuing it means asking again here.
 */
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useConsumeHandoff } from "@/lib/askHandoff";
import { RuntimeReader } from "./components/RuntimeReader";
import { EarlierConversation, EarlierConversationList } from "./components/EarlierConversations";

const RUNTIME_ID = /^[0-9a-f-]{36}$/i;
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
  const rawRecord = params.get("record");
  const recordId = rawRecord && /^[1-9]\d*$/.test(rawRecord) ? Number(rawRecord) : undefined;
  if (rawRecord !== null && (!recordId || !Number.isSafeInteger(recordId))) {
    return <p role="alert" className="p-6">This paper could not be opened.</p>;
  }
  return <div className="flex h-full min-h-0 flex-col">
    <header className="flex items-center justify-between gap-4 border-b border-stone-200 px-6 py-4">
      <h1 className="font-display text-2xl text-stone-900">Ask IRIS</h1>
      <button type="button" className="min-h-11 text-sm text-brand underline" onClick={() => navigate("/ai")}>New conversation</button>
    </header>
    <RuntimeReader key={`${recordId}:${conversationId}`} conversationId={conversationId} recordId={recordId}
      initialDraft={conversationId ? undefined : draft ?? undefined}
      onConversation={id => { if (id !== conversationId) navigate(`/ai/conversations/${id}${recordId ? `?record=${recordId}` : ""}`, { replace: true }); }} />
    {!conversationId && <EarlierConversationList />}
  </div>;
}
