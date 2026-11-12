/**
 * The Review workspace tour's steps (IR-997).
 *
 * Every step names a control or area the workspace really has, in the words
 * the workspace uses, and is built from what is on screen right now -- the
 * tabs that exist, whether a paper is shown, whether the details sidebar is
 * folded into a tab, whether a narrow window keeps the pane behind its
 * launcher -- so the tour never describes something that is not there.
 */
export type TourTab = "conversation" | "threads" | "changes" | "details";

/**
 * The DOM ids the tour points at. The layout puts these on its landmarks and
 * the steps read them from here, so renaming one cannot silently hide a step.
 */
export const tourTargets = (ids: string) => ({
  paper: `${ids}-paper`,
  launcher: `${ids}-launcher`,
  tabs: `${ids}-tabs`,
  foot: `${ids}-foot`,
  side: `${ids}-side`,
  detailsTab: `${ids}-tab-details`,
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

const TAB_ABOUT: Record<TourTab, { name: string; text: string }> = {
  conversation: { name: "Conversation", text: "The timeline of what has happened in this review." },
  threads: { name: "Threads", text: "Comments anchored to a place in the paper or to the record as a whole, with their pins on the paper." },
  changes: { name: "Changes", text: "What changed between two Versions of the paper." },
  details: { name: "Details", text: "The people on this review and the record's details." },
};

export interface TourContext {
  /** The workspace's `useId` prefix, which its landmarks' ids start with. */
  ids: string;
  hasPaper: boolean;
  /** Narrow: the pane sits behind a launcher until it is opened. */
  drawer: boolean;
  paneOpen: boolean;
  /** The sidebar is folded into the Details tab. */
  folded: boolean;
  /** The tabs now shown, in order. */
  tabs: readonly TourTab[];
}

export function reviewTourSteps({ ids, hasPaper, drawer, paneOpen, folded, tabs }: TourContext): TourStep[] {
  const paneShown = !drawer || paneOpen;
  const at = tourTargets(ids);
  const steps: TourStep[] = [];

  if (hasPaper) {
    steps.push({
      id: "paper", target: at.paper, title: "The paper",
      body: "The paper you are reviewing. A pin on the page marks where a thread is anchored.",
    });
  }
  if (!paneShown) {
    steps.push({
      id: "launcher", target: at.launcher, title: "The review pane",
      body: "On a narrow screen the review pane sits behind this button. It holds the tabs, your review status and the actions open to you.",
    });
  }
  if (paneShown) {
    steps.push({
      id: "tabs", target: at.tabs, title: "Review pane sections",
      body: "Switch between the pane's sections:",
      items: tabs.map((t) => TAB_ABOUT[t]),
    });
    steps.push({
      id: "foot", target: at.foot, title: "Your review",
      body: "Your own review status, and the actions open to you right now, such as opening or finishing your review. Which ones show depends on your role and the review's state.",
    });
    steps.push(folded
      ? {
        id: "details", target: at.detailsTab, title: "Details tab",
        body: "The people on this review and the record's details, folded into this tab because the window is narrow.",
      }
      : {
        id: "details", target: at.side, title: "People & details",
        body: "Who is on this review and the record's details. Requesting review from another office or adding a colleague is here, when your role allows it.",
      });
  }
  return steps;
}
