import { useEffect, useRef, type FormEvent, type KeyboardEvent, type Ref } from "react";

import { cn } from "@/lib/utils";
import type { PublicComment } from "@/types/records";

import { CommentAvatar } from "./CommentAvatar";
import { relativeTime, truncateBody } from "./commentThreads";
import { useAutosize } from "./useAutosize";

/** What every comment on the page shares: who is reading, and what is open. */
export interface CommentContext {
  signedIn: boolean;
  saving: boolean;
  maxLength: number;
  now: number;
  /** The comment whose "..." menu is open. */
  menuFor: number | null;
  editingId: number | null;
  editDraft: string;
  /** The comment that was just posted or linked to, shown highlighted. */
  highlightId: number | null;
  /** Comments whose long text has been opened. */
  expandedBodies: ReadonlySet<number>;
  setMenuFor: (id: number | null) => void;
  setEditDraft: (value: string) => void;
  startReply: (comment: PublicComment) => void;
  startEdit: (comment: PublicComment) => void;
  cancelEdit: () => void;
  saveEdit: () => void;
  askDelete: (comment: PublicComment) => void;
  askReport: (comment: PublicComment) => void;
  showWholeBody: (id: number) => void;
  jumpTo: (id: number) => void;
}

interface CommentItemProps {
  comment: PublicComment;
  size: "root" | "reply";
  /** Set when this comment answers another reply rather than the thread's top comment. */
  answering: PublicComment | null;
  /** Draw the thread line down from the avatar, because replies follow. */
  showRail: boolean;
  ctx: CommentContext;
}

const FULL_DATE = { dateStyle: "medium", timeStyle: "short" } as const;

function fullDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, FULL_DATE).format(date);
}

/** A comment: avatar, a bubble with the words, and the few things a reader can do with it. */
export function CommentItem({ comment, size, answering, showRail, ctx }: CommentItemProps) {
  const deleted = comment.deletion_kind !== null;
  const own = comment.can_edit && !deleted;
  const canReport = ctx.signedIn && comment.can_report && !deleted;
  const hasMenu = own || canReport;
  const editing = ctx.editingId === comment.id;
  const menuOpen = ctx.menuFor === comment.id;
  const name = comment.author_name ?? "";
  const avatarSize = size === "root" ? "md" : "sm";

  const { setMenuFor } = ctx;
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);
  const wasEditing = useRef(false);

  // A menu opens onto its first item, and closes on Escape or a click elsewhere.
  useEffect(() => {
    if (!menuOpen) return;
    firstItemRef.current?.focus();
    const onPointer = (event: MouseEvent) => {
      if (!wrapperRef.current?.contains(event.target as Node)) setMenuFor(null);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuFor(null);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen, setMenuFor]);

  // Leaving the editor puts focus back where the reader started it.
  useEffect(() => {
    if (wasEditing.current && !editing) triggerRef.current?.focus();
    wasEditing.current = editing;
  }, [editing]);

  const body = comment.body ?? "";
  const shown = ctx.expandedBodies.has(comment.id) ? { text: body, truncated: false } : truncateBody(body);
  const time = relativeTime(comment.created_at, ctx.now);

  return (
    <article
      id={`comment-${comment.id}`}
      className={cn("grid scroll-mt-24 gap-2", size === "root" ? "grid-cols-[2.25rem_minmax(0,1fr)]" : "grid-cols-[1.75rem_minmax(0,1fr)]")}
    >
      <div className="flex flex-col items-center">
        <CommentAvatar name={deleted ? null : comment.author_name} size={avatarSize} />
        {showRail && <span aria-hidden="true" className="mt-1 w-0.5 flex-1 rounded-full bg-stone-300" />}
      </div>

      <div className="min-w-0">
        {deleted ? (
          <div className="inline-block max-w-full rounded-2xl border border-dashed border-stone-300 px-3.5 py-2">
            <p className="text-sm italic text-stone-600">{comment.deletion_kind === "writer" ? "[deleted]" : "[removed]"}</p>
          </div>
        ) : editing ? (
          <EditForm ctx={ctx} />
        ) : (
          <>
            <div className="group flex max-w-full items-center gap-0.5">
              <div
                className={cn(
                  "min-w-0 max-w-full rounded-2xl px-3.5 py-2 transition-colors duration-300 motion-reduce:transition-none",
                  ctx.highlightId === comment.id ? "bg-brand-100" : "bg-stone-100",
                )}
              >
                <header className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                  <span className="text-xs font-semibold text-stone-900">{name}</span>
                  {comment.is_author && (
                    <span className="rounded-full bg-brand/10 px-2 py-0.5 text-3xs font-semibold text-brand">Author</span>
                  )}
                </header>
                <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-stone-800">
                  {answering && (
                    <>
                      <a
                        href={`#comment-${answering.id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          ctx.jumpTo(answering.id);
                        }}
                        className="font-semibold text-brand hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                      >
                        @{answering.deletion_kind ? "[deleted comment]" : answering.author_name}
                      </a>{" "}
                    </>
                  )}
                  {shown.text}
                  {shown.truncated && (
                    <>
                      {" "}
                      <button
                        type="button"
                        onClick={() => ctx.showWholeBody(comment.id)}
                        className="font-semibold text-stone-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                      >
                        See more
                      </button>
                    </>
                  )}
                </p>
              </div>

              {hasMenu && (
                <div ref={wrapperRef} className="relative shrink-0">
                  <button
                    ref={triggerRef}
                    id={`menu-btn-${comment.id}`}
                    type="button"
                    aria-haspopup="true"
                    aria-expanded={menuOpen}
                    aria-label={`More actions for ${name}'s comment`}
                    onClick={() => ctx.setMenuFor(menuOpen ? null : comment.id)}
                    className="inline-flex h-11 w-11 items-center justify-center rounded-full text-stone-600 transition-colors duration-150 hover:bg-stone-100 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand motion-reduce:transition-none reading-split:h-8 reading-split:w-8 reading-split:opacity-0 reading-split:group-focus-within:opacity-100 reading-split:group-hover:opacity-100 aria-expanded:opacity-100"
                  >
                    <svg viewBox="0 0 24 24" fill="currentColor" className="h-[18px] w-[18px]" aria-hidden="true">
                      <circle cx="5" cy="12" r="1.8" />
                      <circle cx="12" cy="12" r="1.8" />
                      <circle cx="19" cy="12" r="1.8" />
                    </svg>
                  </button>
                  {menuOpen && (
                    <div className="absolute left-0 top-full z-20 mt-1 min-w-40 rounded-xl border border-stone-200 bg-overlay p-1 shadow-card-md">
                      {own && (
                        <>
                          <MenuItem innerRef={firstItemRef} onClick={() => ctx.startEdit(comment)}>Edit</MenuItem>
                          <MenuItem tone="danger" onClick={() => ctx.askDelete(comment)}>Delete</MenuItem>
                        </>
                      )}
                      {!own && canReport && <MenuItem innerRef={firstItemRef} onClick={() => ctx.askReport(comment)}>Report</MenuItem>}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-x-1 pl-2.5 text-2xs text-stone-600">
              {ctx.signedIn && (
                <>
                  <button
                    id={`reply-btn-${comment.id}`}
                    type="button"
                    aria-label={`Reply to ${name}`}
                    onClick={() => ctx.startReply(comment)}
                    className="inline-flex min-h-11 items-center rounded-lg px-1.5 text-2xs font-semibold text-stone-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand reading-split:min-h-8"
                  >
                    Reply
                  </button>
                  <span aria-hidden="true">·</span>
                </>
              )}
              <time dateTime={comment.created_at} title={fullDate(comment.created_at)} aria-label={time.long} className="px-1">
                {time.short}
              </time>
              {comment.edited_at && (
                <>
                  <span aria-hidden="true">·</span>
                  <span title={fullDate(comment.edited_at)}>Edited</span>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </article>
  );
}

function MenuItem({
  children,
  onClick,
  tone,
  innerRef,
}: {
  children: string;
  onClick: () => void;
  tone?: "danger";
  innerRef?: Ref<HTMLButtonElement>;
}) {
  return (
    <button
      ref={innerRef}
      type="button"
      onClick={onClick}
      className={cn(
        "block min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-stone-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand reading-split:min-h-9",
        tone === "danger" ? "text-brand" : "text-stone-800",
      )}
    >
      {children}
    </button>
  );
}

/** The comment's words, edited where they are. Escape leaves them unchanged. */
function EditForm({ ctx }: { ctx: CommentContext }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const remaining = ctx.maxLength - ctx.editDraft.length;
  const canSave = ctx.editDraft.trim().length > 0 && remaining >= 0 && !ctx.saving;

  useAutosize(ref, ctx.editDraft);
  useEffect(() => {
    ref.current?.focus();
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (canSave) ctx.saveEdit();
  };
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      ctx.cancelEdit();
    } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (canSave) ctx.saveEdit();
    }
  };

  return (
    <form onSubmit={submit}>
      <label htmlFor="comment-edit-field" className="sr-only">Edit comment</label>
      <textarea
        ref={ref}
        id="comment-edit-field"
        value={ctx.editDraft}
        onChange={(event) => ctx.setEditDraft(event.target.value)}
        onKeyDown={keyDown}
        maxLength={ctx.maxLength}
        rows={2}
        className="block max-h-64 w-full resize-none overflow-y-auto rounded-2xl border border-stone-300 bg-surface px-3.5 py-2.5 text-sm text-stone-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
      />
      {remaining <= 300 && <p className="mt-1 text-right text-2xs text-stone-600">{remaining} characters remaining</p>}
      <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 pl-1">
        <button
          type="submit"
          disabled={!canSave}
          className="inline-flex min-h-11 items-center rounded-full bg-brand px-4 text-small font-semibold text-white transition-colors duration-150 hover:bg-brand-light focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-600 motion-reduce:transition-none reading-split:min-h-9"
        >
          Save edit
        </button>
        <button
          type="button"
          onClick={ctx.cancelEdit}
          className="inline-flex min-h-11 items-center rounded-lg text-small text-stone-700 underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand reading-split:min-h-9"
        >
          Cancel edit
        </button>
        <span className="text-2xs text-stone-600">Esc to cancel</span>
      </div>
    </form>
  );
}
