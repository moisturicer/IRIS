/**
 * The Review workspace tour's steps (IR-997, made detailed in IR-1309).
 *
 * The workspace is not self-explanatory, so the tour does more than name its
 * areas: each step says what an area is for and how to use it, in the words
 * the workspace's own controls use, and the last step walks the usual order of
 * a review (claim or open it, comment, finish with a verdict).
 *
 * Every step is still built from what is on screen right now -- the tabs that
 * exist and where each sits, whether a paper is shown, whether the reviewer
 * may start a thread, whether a tab may open on the right, whether a narrow
 * window keeps the pane behind its launcher -- so the tour never describes
 * something that is not there.
 */
export type TourTab = "documents" | "conversation" | "threads" | "changes" | "details";

/**
 * The DOM ids the tour points at. The layout puts these on its landmarks and
 * the steps read them from here, so renaming one cannot silently hide a step.
 */
export const tourTargets = (ids: string) => ({
  paper: `${ids}-paper`,
  launcher: `${ids}-launcher`,
  head: `${ids}-head`,
  tabs: `${ids}-tabs`,
  /** A tab's own button in the pane's row. */
  tab: (name: string) => `${ids}-tab-${name}`,
  /** The columns button that opens a tab on the right. */
  beside: `${ids}-beside`,
  /** The right column, holding the tab moved there. */
  side: `${ids}-side`,
  foot: `${ids}-foot`,
});

export interface TourStep {
  id: string;
  /** The DOM id of the control or area this step highlights. */
  target: string;
  title: string;
  body: string;
  /** A short list under the body, one entry per name. */
  items?: { name: string; text: string }[];
}

type Item = { name: string; text: string };

/** What each tab is for and how to use it. `drafting`: new threads may wait as drafts. */
function tabStep(tab: TourTab, { canStart, canComment, drafting }: { canStart: boolean; canComment: boolean; drafting: boolean }) {
  const about: Record<TourTab, { title: string; body: string; items: (Item | false)[] }> = {
    documents: {
      title: "Documents",
      body: "Everything filed with this record. The pane opens here.",
      items: [
        { name: "Manuscript", text: "The paper itself, with each Version the authors sent." },
        { name: "Other documents", text: "Forms and attachments, each with its own versions. Open one to read it where the paper is; opening a thread or a change brings the paper back." },
        { name: "Requests", text: "Ask the authors for a missing document with Request documents, where you may, and see whether each one asked for has arrived." },
      ],
    },
    conversation: {
      title: "Conversation",
      body: "The review's timeline: the submission, each office's moves, each new Version and every comment. The number on the tab counts the comments sent.",
      items: [
        canComment && { name: "Comment on the whole paper", text: "Use the comment box in the timeline for a remark that is not about one passage." },
        { name: "Open threads", text: "A comment that is part of a thread takes you to it in Threads." },
      ],
    },
    threads: {
      title: "Threads",
      body: "Comments pinned to a passage of the paper, or to the record as a whole, each with its replies. The number on the tab counts the open ones.",
      items: [
        { name: "Open, Yours, Resolved, All", text: "Filter the list. Start with Open: those still need an answer." },
        canStart && { name: "Start a thread", text: "Select a passage in the paper and press C, or use New comment for a remark on the whole record." },
        drafting && { name: "Drafts", text: "While your review is open a new thread can be saved as a draft. Only you see it. Drafts are sent together when you finish your review, or one at a time with Post." },
        { name: "p. 4 · v2", text: "The link on a thread goes to its passage on the page." },
        { name: "Reply and Resolve", text: "Answer a thread with Reply. Once its point is settled, it can be resolved; it moves to Resolved and can be reopened." },
      ],
    },
    changes: {
      title: "Changes",
      body: "What changed between two Versions of the paper. Until the authors send a second Version there is nothing to compare.",
      items: [
        { name: "Compare … with", text: "Choose the two Versions to compare." },
        { name: "Viewed", text: "Tick a changed section once you have read it, so you know where you left off." },
        { name: "Show in v2, p. 4", text: "Goes to the change on the page, in the Version it is in." },
        { name: "Threads in this section", text: "Threads pinned inside a changed section are listed under it, so you can check whether the change answers them." },
      ],
    },
    details: {
      title: "Details",
      body: "The people on this review and the record's facts.",
      items: [
        { name: "Readiness", text: "What your part depends on, when something does, each with a link to act on it." },
        { name: "Reviewers", text: "Each office or person asked to review and where they stand. Where you may, the sliders button requests another office's review and Add a colleague brings someone into yours." },
        { name: "Researchers, Adviser, Classification", text: "Who wrote the paper, who advises it, and its type, area and keywords." },
        { name: "Version history", text: "Each Version, oldest first, with the documents sent with it." },
      ],
    },
  };
  const { title, body, items } = about[tab];
  return { title, body, items: items.filter((i): i is Item => i !== false) };
}

export interface TourContext {
  /** The workspace's `useId` prefix, which its landmarks' ids start with. */
  ids: string;
  hasPaper: boolean;
  /** Narrow: the pane sits behind a launcher until it is opened. */
  drawer: boolean;
  paneOpen: boolean;
  /** A tab may open in a right column, so the columns button is on screen. */
  beside: boolean;
  /** Every tab the workspace has, in order, wherever it is shown. */
  tabs: readonly TourTab[];
  /** The tab shown in the right column, if one is. */
  sideTab?: TourTab | null;
  /** The viewer may start a thread on a passage (`start_thread`). */
  canStart?: boolean;
  /** The viewer may comment in the Conversation (`comment_review`). */
  canComment?: boolean;
  /** New threads may wait as drafts until Finish review (`finish_review`). */
  drafting?: boolean;
}

export function reviewTourSteps({
  ids, hasPaper, drawer, paneOpen, beside, tabs, sideTab = null, canStart = false, canComment = false, drafting = false,
}: TourContext): TourStep[] {
  const paneShown = !drawer || paneOpen;
  const at = tourTargets(ids);
  const steps: TourStep[] = [];

  if (hasPaper) {
    steps.push({
      id: "paper", target: at.paper, title: "The paper",
      body: "The paper under review, page by page. Every comment on a passage is pinned to its place here.",
      items: [
        ...(canStart ? [{ name: "Comment on a passage", text: "Select the text, then press C or the Comment button above the page. Your comment opens in the Threads tab." }] : []),
        { name: "Pins", text: "A numbered pin marks a thread. A filled pin is an open thread; an outlined one is your draft, which no one else sees yet. Click a pin to open its thread." },
      ],
    });
  }
  if (!paneShown) {
    steps.push({
      id: "launcher", target: at.launcher, title: "The review pane",
      body: "On a narrow screen the paper takes the whole width, and the review pane waits behind Open review pane. It holds the tabs, your part and the actions open to you. Back to paper brings you here again.",
    });
  }
  if (!paneShown) return steps;

  steps.push({
    id: "head", target: at.head, title: "Where the review stands",
    body: "The top of the pane says where the record is now.",
    items: [
      { name: "With …", text: "Who holds the record now, and so whose move it is." },
      { name: "… sent v2", text: "Who sent the Version you are reading, and when. A new Version comes when the authors answer a revision request." },
      ...(!drawer && hasPaper ? [{ name: "Pane width", text: "Drag the pane's left edge to widen it or give the paper more room. Double-click the edge to reset it." }] : []),
      { name: "Take a tour", text: "Runs this tour again whenever you need it." },
    ],
  });
  steps.push({
    id: "tabs", target: at.tabs, title: "The pane's tabs",
    body: "The pane has one tab for each part of the review. Click a tab, or use the arrow keys once one has focus. The next steps go through them one by one.",
  });
  for (const tab of tabs) {
    const step = tabStep(tab, { canStart, canComment, drafting });
    const onRight = tab === sideTab;
    steps.push({
      id: `tab-${tab}`, target: onRight ? at.side : at.tab(tab),
      title: onRight ? `${step.title}, on the right` : step.title,
      body: onRight ? `${step.body} You moved it to the right column; close it there to put it back in the row.` : step.body,
      items: step.items,
    });
  }
  if (beside) {
    steps.push({
      id: "beside", target: at.beside, title: "Two tabs side by side",
      body: "Opens one tab in a column on the right, so you can, for example, keep Threads open while reading the Conversation. Close the column with its × to put the tab back. Your choice is remembered.",
    });
  }
  steps.push({
    id: "foot", target: at.foot, title: "Your part",
    body: "Where your part of the review stands, and the actions open to you. They change with your role and the review's state.",
    items: [
      { name: "The icon", text: "Maroon means something waits on you; a check means your part is done." },
      { name: "The line under it", text: "The most pressing item, and how many of your draft comments are not sent yet." },
      { name: "See what it depends on", text: "Opens the full list in Details." },
    ],
  });
  steps.push({
    id: "flow", target: at.foot, title: "How a review goes",
    body: "Most reviews take three steps, each started from this footer.",
    items: [
      { name: "1. Claim or open it", text: "If the review is offered to your office, claim it first. Then press Open review to start." },
      { name: "2. Read and comment", text: "Comment on passages in the paper and on the whole record in Conversation or Threads." + (drafting ? " Your comments wait as drafts." : "") },
      { name: "3. Finish review", text: "Choose a verdict, such as Comment only, Request changes or Accept, add a summary, and your drafts are sent with it in one go. Send comments sends drafts without a verdict." },
    ],
  });
  return steps;
}
