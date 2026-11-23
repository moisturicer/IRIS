/**
 * A place in Review a link can land on: one of its tabs and, in Threads or
 * Conversation, the party whose request it is, or one thread.
 * `?tab=threads&party=ierc` or `?tab=threads&thread=12` beside `?section=review`. Read once and dropped, as `?documents=open` is, so
 * the tab is the reader's to change afterwards.
 */
export interface ReviewTarget {
  /** A tab's name. One the viewer's workspace does not have is ignored. */
  tab: string;
  party: string | null;
  /** One thread, in Threads. */
  thread?: number | null;
}

export function reviewTargetFrom(params: URLSearchParams): ReviewTarget | null {
  const tab = params.get("tab");
  if (!tab) return null;
  const thread = Number(params.get("thread"));
  return { tab, party: params.get("party"), thread: Number.isInteger(thread) && thread > 0 ? thread : null };
}

/** The view parameters that open `target`. */
export const reviewTargetParams = (target: ReviewTarget) => ({
  section: "review", tab: target.tab, party: target.party, thread: target.thread ? String(target.thread) : null,
});
