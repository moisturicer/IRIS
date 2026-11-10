/**
 * Saved replies (ADR-032 §7 Conveniences, IR-877): a person's own reusable
 * texts, offered beside a review comment box. Choosing one **only adds
 * text**: it goes in at the cursor, after any selection, so nothing already
 * written is replaced. The server never hears that a reply was used.
 *
 * The list is fetched when the menu is first opened, so a page with several
 * comment boxes asks for nothing until someone wants a reply.
 */
import { useEffect, useId, useRef, useState, type FormEvent, type RefObject } from "react";

import { reviewsApi } from "@/api/reviews";
import { Button, Modal } from "@/components/ui";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import type { SavedReply } from "@/types/reviews";

type Loaded = { state: "idle" | "loading" | "failed" } | { state: "ready"; replies: SavedReply[] };

/** Is `r` a saved reply as we read one (F1)? */
function isReply(r: unknown): r is SavedReply {
  return !!r && typeof r === "object" && typeof (r as SavedReply).id === "number"
    && typeof (r as SavedReply).title === "string" && typeof (r as SavedReply).body === "string";
}

/** The replies in a response, or null when it isn't the shape we read (F1). */
function repliesIn(data: unknown): SavedReply[] | null {
  const results = (data as { results?: unknown } | null)?.results;
  return Array.isArray(results) ? results.filter(isReply) : null;
}

const byTitle = (a: SavedReply, b: SavedReply) =>
  a.title.localeCompare(b.title, undefined, { sensitivity: "base" });

/** `value` with `text` added at `at`: nothing is removed. */
function insertAt(value: string, text: string, at: number): { value: string; caret: number } {
  const i = Math.max(0, Math.min(at, value.length));
  return { value: value.slice(0, i) + text + value.slice(i), caret: i + text.length };
}

export function SavedReplies({ textareaRef, value, onChange }: {
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  value: string;
  onChange: (value: string) => void;
}) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const [managing, setManaging] = useState(false);
  const [loaded, setLoaded] = useState<Loaded>({ state: "idle" });
  // A box nobody has been in reports its cursor at the start; a reply then
  // belongs at the end, after what is already written.
  const visited = useRef(false);
  useEffect(() => {
    const box = textareaRef.current;
    const mark = () => { visited.current = true; };
    box?.addEventListener("focus", mark);
    return () => box?.removeEventListener("focus", mark);
  }, [textareaRef]);

  const load = async () => {
    setLoaded({ state: "loading" });
    try {
      const { data } = await reviewsApi.savedReplies();
      const replies = repliesIn(data);
      setLoaded(replies ? { state: "ready", replies } : { state: "failed" });
    } catch {
      setLoaded({ state: "failed" });
    }
  };

  const toggle = () => {
    if (!open && loaded.state !== "ready") void load();
    setOpen(!open);
  };

  const insert = (reply: SavedReply) => {
    const box = textareaRef.current;
    // After the selection, never over it: inserting only adds text.
    const at = box && visited.current ? box.selectionEnd : value.length;
    const next = insertAt(value, reply.body, at);
    onChange(next.value);
    setOpen(false);
    requestAnimationFrame(() => {
      box?.focus();
      box?.setSelectionRange(next.caret, next.caret);
    });
  };

  const replies = loaded.state === "ready" ? loaded.replies : [];

  return (
    <div className="space-y-1.5">
      <Button type="button" size="sm" variant="ghost" onClick={toggle}
        aria-expanded={open} aria-controls={open ? menuId : undefined}>
        <i className="fas fa-reply-all mr-1.5" aria-hidden />Saved replies
      </Button>
      {open && (
        <div id={menuId} className="rounded-lg border border-stone-200 bg-white p-2 space-y-1.5">
          {loaded.state === "loading" && <p className="text-2xs text-stone-600">Loading your saved replies…</p>}
          {loaded.state === "failed" && <p className="text-2xs text-stone-600">Your saved replies couldn&rsquo;t be loaded.</p>}
          {loaded.state === "ready" && replies.length === 0 && (
            <p className="text-2xs text-stone-600">No saved replies yet.</p>
          )}
          {replies.length > 0 && (
            <ul aria-label="Your saved replies" className="flex flex-wrap gap-1.5">
              {replies.map((r) => (
                <li key={r.id}>
                  <Button type="button" size="sm" variant="secondary" onClick={() => insert(r)}
                    aria-label={`Insert “${r.title}”`} title={r.body}>
                    {r.title}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {/* Only over a loaded list: managing an unloaded one would lose the rest. */}
          {loaded.state === "ready" && (
            <Button type="button" size="sm" variant="ghost" onClick={() => setManaging(true)}>
              Manage saved replies
            </Button>
          )}
        </div>
      )}
      <ManageSavedReplies
        open={managing}
        replies={replies}
        onChange={(next) => setLoaded({ state: "ready", replies: [...next].sort(byTitle) })}
        onStale={() => void load()}
        onClose={() => setManaging(false)}
      />
    </div>
  );
}

function ManageSavedReplies({ open, replies, onChange, onStale, onClose }: {
  open: boolean;
  replies: SavedReply[];
  onChange: (replies: SavedReply[]) => void;
  /** A write answered with a body we can't read (F1): the list is read again. */
  onStale: () => void;
  onClose: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="Saved replies"
      footer={<div className="flex justify-end"><Button type="button" onClick={onClose}>Done</Button></div>}>
      <div className="space-y-4">
        <p className="text-small text-stone-700">Only you see these. Inserting one adds its text to your comment.</p>
        {replies.length > 0 && (
          <ul className="space-y-2">
            {replies.map((r) => (
              <ReplyItem key={r.id} reply={r}
                onSaved={(saved) => (isReply(saved)
                  ? onChange(replies.map((x) => (x.id === saved.id ? saved : x))) : onStale())}
                onDeleted={() => onChange(replies.filter((x) => x.id !== r.id))} />
            ))}
          </ul>
        )}
        <section aria-label="Add a saved reply" className="space-y-2">
          <h3 className="text-small font-semibold text-stone-800">Add a saved reply</h3>
          <ReplyForm submitLabel="Save reply" clearOnSuccess
            onSubmit={async (body) => {
              const { data } = await reviewsApi.createSavedReply(body);
              if (isReply(data)) onChange([...replies, data]);
              else onStale();
            }} />
        </section>
      </div>
    </Modal>
  );
}

function ReplyItem({ reply, onSaved, onDeleted }: {
  reply: SavedReply;
  onSaved: (reply: unknown) => void;
  onDeleted: () => void;
}) {
  const titleId = useId();
  const [mode, setMode] = useState<"view" | "edit" | "confirm">("view");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await reviewsApi.deleteSavedReply(reply.id);
      onDeleted();
    } catch (err) {
      setError(errorDetail(err, "The reply couldn't be deleted."));
      setBusy(false);
    }
  };

  return (
    <li aria-labelledby={titleId} className="rounded-lg border border-stone-200 p-2 space-y-1.5">
      <p id={titleId} className="text-small font-semibold text-stone-800">{reply.title}</p>
      {mode === "edit" ? (
        <ReplyForm submitLabel="Save changes" initial={reply} onCancel={() => setMode("view")}
          onSubmit={async (body) => {
            const { data } = await reviewsApi.updateSavedReply(reply.id, body);
            onSaved(data);
            setMode("view");
          }} />
      ) : (
        <>
          <p className="whitespace-pre-wrap break-words text-small text-stone-700">{reply.body}</p>
          {error && <p role="alert" className="text-small text-brand">{error}</p>}
          {mode === "confirm" ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-small text-stone-800">Delete this saved reply?</span>
              <Button type="button" size="sm" variant="danger" onClick={remove} disabled={busy}>Yes, delete</Button>
              <Button type="button" size="sm" variant="secondary" onClick={() => setMode("view")} disabled={busy}>Keep it</Button>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={() => setMode("edit")}
                aria-label={`Edit “${reply.title}”`}>Edit</Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setMode("confirm")}
                aria-label={`Delete “${reply.title}”`}>Delete</Button>
            </div>
          )}
        </>
      )}
    </li>
  );
}

function ReplyForm({ submitLabel, initial, clearOnSuccess, onSubmit, onCancel }: {
  submitLabel: string;
  initial?: SavedReply;
  clearOnSuccess?: boolean;
  onSubmit: (body: { title: string; body: string }) => Promise<void>;
  onCancel?: () => void;
}) {
  const ids = useId();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setError(null), [title, body]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !body.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ title: title.trim(), body: body.trim() });
      if (clearOnSuccess) {
        setTitle("");
        setBody("");
      }
    } catch (err) {
      setError(fieldError(err, "title", "body") ?? errorDetail(err, "The reply couldn't be saved."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-1.5">
      <label htmlFor={`${ids}-title`} className={LABEL}>Title</label>
      <input id={`${ids}-title`} value={title} maxLength={60} onChange={(e) => setTitle(e.target.value)}
        className={fieldClasses(false)} />
      <label htmlFor={`${ids}-body`} className={LABEL}>Text</label>
      <textarea id={`${ids}-body`} rows={3} value={body} onChange={(e) => setBody(e.target.value)}
        className={fieldClasses(false)} />
      {error && <p role="alert" className="text-small text-brand">{error}</p>}
      <div className="flex justify-end gap-2">
        {onCancel && <Button type="button" size="sm" variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>}
        <Button type="submit" size="sm" disabled={busy || !title.trim() || !body.trim()}>{submitLabel}</Button>
      </div>
    </form>
  );
}
