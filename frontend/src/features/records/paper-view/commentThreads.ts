import type { PublicComment } from "@/types/records";

/**
 * How the public comments of a paper are laid out as threads (IR-1024).
 *
 * The API stores `reply_to`, which can point at any comment, so the data is a
 * tree of any depth. The page shows two levels, like Facebook: a top-level
 * comment and everything beneath it in order. A reply to a reply keeps its
 * `reply_to` and is shown in the same thread with the name of who it answers.
 */

/** A thread with more replies than this starts collapsed. */
export const COLLAPSE_ABOVE = 2;

/** Top-level comments shown at first and added by each "View more". */
export const PAGE_SIZE = 5;

/** A body longer than this is cut, with "See more". */
export const SEE_MORE_AT = 300;

export type CommentOrder = "oldest" | "newest";

export interface Thread {
  root: PublicComment;
  /** Every comment beneath the root, oldest first, however deep it was posted. */
  replies: PublicComment[];
}

const byAge = (left: PublicComment, right: PublicComment) => Date.parse(left.created_at) - Date.parse(right.created_at);

const isLive = (comment: PublicComment) => comment.deletion_kind === null;

/**
 * The threads to show, in order.
 *
 * A deleted or removed comment stays only while a live comment sits beneath it,
 * so the replies keep their context; a deleted comment with nothing live under
 * it is not shown at all. A reply whose parent is not in the list is shown as
 * a top-level comment rather than lost.
 */
export function buildThreads(comments: PublicComment[], order: CommentOrder = "oldest"): Thread[] {
  const sorted = [...comments].sort(byAge);
  const byId = new Map(sorted.map((comment) => [comment.id, comment]));

  // Who each comment answers. A missing parent, or the oldest comment of a
  // reply chain that loops back on itself, becomes a top-level comment.
  const parent = new Map<number, number | null>(
    sorted.map((comment) => [comment.id, comment.reply_to !== null && byId.has(comment.reply_to) ? comment.reply_to : null]),
  );
  for (const comment of sorted) {
    const walked: number[] = [];
    let current: number | null = comment.id;
    while (current !== null && !walked.includes(current)) {
      walked.push(current);
      current = parent.get(current) ?? null;
    }
    if (current !== null) {
      // `walked` ends in a loop; cut it at its oldest member (the list is oldest first).
      const loop = walked.slice(walked.indexOf(current));
      const oldest = loop.reduce((a, b) => (sorted.findIndex((c) => c.id === a) <= sorted.findIndex((c) => c.id === b) ? a : b));
      parent.set(oldest, null);
    }
  }

  const rootOf = (comment: PublicComment): PublicComment => {
    let current = comment;
    for (let up = parent.get(current.id); up != null; up = parent.get(current.id)) current = byId.get(up) as PublicComment;
    return current;
  };

  // A deleted comment is kept when something live is anywhere beneath it.
  const kept = new Set<number>();
  for (const comment of sorted) {
    if (!isLive(comment)) continue;
    for (let up = parent.get(comment.id); up != null; up = parent.get(up)) kept.add(up);
  }
  const shown = (comment: PublicComment) => isLive(comment) || kept.has(comment.id);

  const repliesByRoot = new Map<number, PublicComment[]>();
  const roots: PublicComment[] = [];
  for (const comment of sorted) {
    if (!shown(comment)) continue;
    if (parent.get(comment.id) === null) {
      roots.push(comment);
    } else {
      const rootId = rootOf(comment).id;
      repliesByRoot.set(rootId, [...(repliesByRoot.get(rootId) ?? []), comment]);
    }
  }

  const ordered = [...roots].sort(order === "newest" ? (left, right) => byAge(right, left) : byAge);
  return ordered.map((root) => ({ root, replies: repliesByRoot.get(root.id) ?? [] }));
}

/** A comment's age as Facebook words it, plus the same thing for a screen reader. */
export function relativeTime(iso: string, now: number = Date.now()): { short: string; long: string } {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return { short: iso, long: iso };

  const minutes = Math.max(0, Math.floor((now - then) / 60_000));
  if (minutes < 1) return { short: "Just now", long: "just now" };
  if (minutes < 60) return { short: `${minutes}m`, long: `${minutes} ${minutes === 1 ? "minute" : "minutes"} ago` };
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return { short: `${hours}h`, long: `${hours} ${hours === 1 ? "hour" : "hours"} ago` };
  const days = Math.floor(hours / 24);
  if (days < 7) return { short: `${days}d`, long: `${days} ${days === 1 ? "day" : "days"} ago` };

  const sameYear = new Date(then).getFullYear() === new Date(now).getFullYear();
  const date = new Intl.DateTimeFormat(undefined, sameYear ? { month: "short", day: "numeric" } : { dateStyle: "medium" }).format(then);
  return { short: date, long: date };
}

/** First and last name's first letters; `?` for a comment with no author. */
export function initials(name: string | null): string {
  const parts = (name ?? "").replace(/\./g, "").split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const first = parts[0][0];
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return `${first}${last}`.toUpperCase();
}

/** A body cut at a word boundary, and whether it was cut. */
export function truncateBody(body: string, limit: number = SEE_MORE_AT): { text: string; truncated: boolean } {
  if (body.length <= limit) return { text: body, truncated: false };
  return { text: `${body.slice(0, limit).replace(/\s+\S*$/, "")}…`, truncated: true };
}
