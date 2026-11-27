/**
 * The student guided tours' steps (IR-1342), one builder per page.
 *
 * Like the Review tour's (`reviewTourSteps`), each builder writes only what is
 * on screen: a page passes what it has (whether Publish is offered, which tabs
 * exist), and a step whose target is not reachable when the tour runs, such as
 * the sidebar behind a phone's menu, drops out of the walk. Copy uses the words
 * the page's own controls use.
 *
 * Targets are DOM ids from `TOUR_TARGETS`. The pages put these ids on their
 * controls and the steps read them from here, so renaming one cannot silently
 * hide a step. Each page renders once per route, so the ids are fixed strings.
 */
import type { TourStep } from "@/components/tour/types";
import { pathFor } from "@/lib/access";

import { TOUR_PARAM, type TourKey } from "./tourKeys";
import { PUBLISH_PARAM } from "@/features/publish/publishLink";

export const SIDEBAR_ID = "app-sidebar";

export const TOUR_TARGETS = {
  discover: {
    heading: "tour-discover-heading",
    search: "tour-discover-search",
    controls: "tour-discover-controls",
    publish: "tour-discover-publish",
  },
  library: {
    tabs: "tour-library-tabs",
    publish: "tour-library-publish",
    waiting: "tour-library-waiting",
    recent: "tour-library-recent",
  },
  ask: {
    question: "tour-ask-question",
    history: "tour-ask-history",
    phoneHistory: "tour-ask-history-button",
  },
  calls: {
    filters: "tour-calls-filters",
    saved: "tour-calls-saved",
    board: "tour-calls-board",
  },
  guidelines: {
    types: "tour-guidelines-types",
    manuscript: "tour-guidelines-manuscript",
  },
  notifications: {
    feed: "tour-notifications-feed",
    show: "tour-notifications-show",
    markAll: "tour-notifications-mark-all",
  },
  publish: {
    steps: "tour-publish-steps",
    type: "tour-publish-type",
    manuscript: "tour-publish-manuscript",
    footer: "tour-publish-footer",
  },
} as const;

/** Each tour's accessible name, which is also the card's dialog name. */
export const TOUR_LABELS: Record<TourKey, string> = {
  discover: "Discover tour",
  library: "My Library tour",
  ask: "Ask IRIS tour",
  calls: "Calls & Conferences tour",
  guidelines: "Guidelines tour",
  notifications: "Notifications tour",
  publish: "Publish tour",
};

/**
 * Settings › Help's list (AC 5): each tour by its page's name and where taking
 * it again goes. Publish opens over Discover, as its button there does; the
 * dialog creates nothing until a file is chosen.
 */
export const TOUR_PAGES: { key: TourKey; page: string; href: string }[] = [
  { key: "discover", page: "Discover", href: `/?${TOUR_PARAM}=discover` },
  { key: "publish", page: "Publish", href: `/?${PUBLISH_PARAM}=new&${TOUR_PARAM}=publish` },
  { key: "library", page: "My Library", href: `/records/mine?${TOUR_PARAM}=library` },
  { key: "ask", page: "Ask IRIS", href: `/ai?${TOUR_PARAM}=ask` },
  { key: "calls", page: "Calls & Conferences", href: `/opportunities?${TOUR_PARAM}=calls` },
  { key: "guidelines", page: "Guidelines", href: `${pathFor("guidelines")}?${TOUR_PARAM}=guidelines` },
  { key: "notifications", page: "Notifications", href: `/notifications?${TOUR_PARAM}=notifications` },
];

const AGAIN = "Settings › Help lists every tour, to take one again whenever you like.";

export function discoverTourSteps({ canPublish }: { canPublish: boolean }): TourStep[] {
  const at = TOUR_TARGETS.discover;
  const steps: TourStep[] = [
    {
      id: "welcome", target: at.heading, title: "Welcome to IRIS",
      body: "IRIS is where CIT-U's research is published, reviewed and found. Discover is your home: research, projects and reference papers you can read. Each page gives you a short tour the first time you open it.",
    },
    {
      id: "sidebar", target: SIDEBAR_ID, title: "Your pages",
      body: "The sidebar takes you everywhere else.",
      items: [
        { name: "My Library", text: "Your submissions, saved papers and saved calls." },
        { name: "Ask IRIS", text: "Questions answered from the research you can read." },
        { name: "Calls & Conferences", text: "Calls for papers, with their deadlines." },
        { name: "Guidelines", text: "What each type of record needs." },
      ],
    },
    {
      id: "search", target: at.search, title: "Search",
      body: "Search research, people and topics. Results update as you type.",
    },
    {
      id: "controls", target: at.controls, title: "Papers, People and filters",
      body: "Switch between Papers and People, sort the papers, and narrow them with Filters by type, college, classification or year.",
    },
  ];
  if (canPublish) {
    steps.push({
      id: "publish", target: at.publish, title: "Publish",
      body: `Publish starts a record of your own research: you upload the manuscript and fill in its details, and it goes to your Adviser for review. ${AGAIN}`,
    });
  } else {
    steps[steps.length - 1] = { ...steps[steps.length - 1], body: `${steps[steps.length - 1].body} ${AGAIN}` };
  }
  return steps;
}

export function libraryTourSteps({ tabs, canPublish, overview }: {
  /** The tabs on screen, by their labels, in order. */
  tabs: { label: string; text: string }[];
  canPublish: boolean;
  /** The Overview tab is the one showing, so its cards are on screen. */
  overview: boolean;
}): TourStep[] {
  const at = TOUR_TARGETS.library;
  const steps: TourStep[] = [
    {
      id: "tabs", target: at.tabs, title: "Your Library",
      body: "Everything you keep in IRIS, a tab for each kind.",
      items: tabs.map((t) => ({ name: t.label, text: t.text })),
    },
  ];
  if (overview) {
    steps.push(
      {
        id: "waiting", target: at.waiting, title: "Waiting on you",
        body: "When a reviewer asks you for changes or a document, the record appears here with a link to answer it. Its count shows how many are waiting.",
      },
      {
        id: "recent", target: at.recent, title: "Recent submissions",
        body: "Your latest records, by when they last changed. My Submissions has the full list.",
      },
    );
  }
  if (canPublish) {
    steps.push({
      id: "publish", target: at.publish, title: "Publish",
      body: "Start a new record from here or from Discover. A draft you keep waits in My Submissions until you finish it.",
    });
  }
  return steps;
}

export function askTourSteps(): TourStep[] {
  const at = TOUR_TARGETS.ask;
  return [
    {
      id: "question", target: at.question, title: "Ask a question",
      body: "Ask in your own words. IRIS answers only from papers you may read, and cites each one it uses: open a citation to read the passage in its paper.",
      items: [
        { name: "Research depth", text: "Standard answers sooner. Thorough research searches and reads more before answering." },
      ],
    },
    {
      id: "history", target: at.history, title: "History",
      body: "Your conversations, newest first. Open one to carry on, search them, or start a new conversation.",
    },
    {
      id: "phone-history", target: at.phoneHistory, title: "History",
      body: "Show history opens your conversations, to carry one on or start a new one.",
    },
  ];
}

export function callsTourSteps(): TourStep[] {
  const at = TOUR_TARGETS.calls;
  return [
    {
      id: "board", target: at.board, title: "The board",
      body: "Calls for papers from conferences, journals and other venues, posted by RDCO and advisers, soonest deadline first.",
    },
    {
      id: "filters", target: at.filters, title: "Search and filters",
      body: "Search calls by title, location or Area, choose an Area, or show one type at a time.",
    },
    {
      id: "saved", target: at.saved, title: "Saved",
      body: "Use the bookmark on a call to save it. Saved shows only those, and My Library keeps them under Saved Calls.",
    },
  ];
}

export function guidelinesTourSteps(): TourStep[] {
  const at = TOUR_TARGETS.guidelines;
  return [
    {
      id: "types", target: at.types, title: "One type at a time",
      body: "Choose what you are submitting, such as a Proposal or a Thesis / Research, to see what it needs.",
    },
    {
      id: "manuscript", target: at.manuscript, title: "What you submit",
      body: "Only the manuscript is needed to submit, and you upload it in Publish. Where there is a Template, download it here. The documents listed below it are what RDCO expects, and an office asks for each one during review.",
    },
  ];
}

export function notificationsTourSteps(): TourStep[] {
  const at = TOUR_TARGETS.notifications;
  return [
    {
      id: "feed", target: at.feed, title: "Notifications",
      body: "Updates on your records and reviews, grouped by day. Select one to go to its record. One you haven't read is marked Unread.",
    },
    {
      id: "show", target: at.show, title: "All or Unread",
      body: "Show only the ones you haven't read yet.",
    },
    {
      id: "mark-all", target: at.markAll, title: "Mark all as read",
      body: "Clear every Unread mark at once.",
    },
  ];
}

/** `step`: the dialog's step on screen. Only the first has a type and a file to point at. */
export function publishTourSteps({ step }: { step: number }): TourStep[] {
  const at = TOUR_TARGETS.publish;
  const steps: TourStep[] = [
    {
      id: "steps", target: at.steps, title: "Four steps",
      body: "Publish takes you through four steps, in order.",
      items: [
        { name: "Your manuscript", text: "Choose the type and upload the paper." },
        { name: "Details", text: "Title, abstract, authors, your Adviser and the rest." },
        { name: "Documents", text: "Anything else your type asks for, now or later." },
        { name: "Review & submit", text: "Check it all and submit it for review." },
      ],
    },
  ];
  if (step === 1) {
    steps.push(
      {
        id: "type", target: at.type, title: "What are you publishing?",
        body: "Choose its type first. Guidelines says what each type needs.",
      },
      {
        id: "manuscript", target: at.manuscript, title: "Manuscript file",
        body: "Upload the full paper as a PDF. Choosing the file saves your draft, so from then on it is in My Library, and IRIS reads it to suggest Details.",
      },
    );
  }
  steps.push(
    {
      id: "leaving", target: at.footer, title: "Leaving and coming back",
      body: "Close at any time. Once there is a draft, IRIS asks first: Keep as draft saves it, to finish later from My Library.",
    },
    {
      id: "flow", target: at.footer, title: "How publishing goes",
      body: "After you submit, the record moves through review.",
      items: [
        { name: "1. Your Adviser", text: "Reviews it first, and may ask for a revision, reject it, or accept it. A Proposal ends there." },
        { name: "2. RDCO and the offices", text: "For a Thesis / Research or Project, RDCO decides what happens next and may ask offices to review it." },
        { name: "3. Revisions", text: "If anyone asks for changes, the record waits on you in My Library: submit a new version." },
      ],
    },
  );
  return steps;
}
