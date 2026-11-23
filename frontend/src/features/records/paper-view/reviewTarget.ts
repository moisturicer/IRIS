/**
 * A place in Review a link can land on: one of its tabs and, in Threads or
 * Conversation, the party whose request it is. `?tab=threads&party=ierc`
 * beside `?section=review`. Read once and dropped, as `?documents=open` is, so
 * the tab is the reader's to change afterwards.
 */
export interface ReviewTarget {
  /** A tab's name. One the viewer's workspace does not have is ignored. */
  tab: string;
  party: string | null;
}

export function reviewTargetFrom(params: URLSearchParams): ReviewTarget | null {
  const tab = params.get("tab");
  return tab ? { tab, party: params.get("party") } : null;
}

/** The view parameters that open `target`. */
export const reviewTargetParams = (target: ReviewTarget) => ({
  section: "review", tab: target.tab, party: target.party,
});
