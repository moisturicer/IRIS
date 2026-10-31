import type { ReactNode } from "react";

import { canAccess, hasReviewWork } from "@/lib/access";
import type { RoleName } from "@/lib/constants";
import type { ReviewAccess } from "@/types/auth";

/** Who is reading Help: enough to know which screens they can open. */
export interface HelpReader {
  role:          RoleName | null | undefined;
  reviewAccess?: ReviewAccess | null;
}

export interface HelpSection {
  /** The anchor: `/help#<id>`. Stable, because other screens link to it. */
  id:    string;
  title: string;
  /**
   * Whether this reader sees the section. Each one asks the same question the
   * sidebar and route guards ask (`lib/access.ts`), so Help never explains a
   * screen the reader cannot open. Absent means everyone.
   */
  shownTo?: (reader: HelpReader) => boolean;
  body: ReactNode;
}

const reviews = (r: HelpReader) => canAccess(r.role, "reviewQueue") && hasReviewWork(r.reviewAccess);

/**
 * Help's content (IR-745), in reading order.
 *
 * Written in the project's vocabulary (CONTEXT.md) and describing only what
 * is built: PRODUCT.md's honest-copy rule applies to Help as much as to any
 * screen. When a feature changes, its section here changes with it.
 */
export const HELP_SECTIONS: HelpSection[] = [
  {
    id: "discover",
    title: "Finding research",
    body: (
      <>
        <p>
          Discover is the catalogue of published research. Search it, and narrow the results by
          record type, year, or whether a record has IP.
        </p>
        <p>
          Open a result to read it. A record has an <strong>Overview</strong>, with its abstract and
          an AI Overview that IRIS derived from the paper, and a <strong>Paper</strong> section with
          the manuscript itself. The abstract is what the authors wrote; the AI Overview is not, and
          it cites the pages it draws on.
        </p>
        <p>
          From a record you can <strong>Save</strong> it to your Library, <strong>Share</strong> its
          link, cite it, or use Paper Chat to ask questions about that one paper.
        </p>
      </>
    ),
  },
  {
    id: "downloads",
    title: "Downloading a paper",
    body: (
      <>
        <p>
          Every reader who can see a published paper can read it inside IRIS. Saving a copy to take
          away is a download, and needs RDCO's approval: choose <strong>Request download</strong>{" "}
          and say why you need it.
        </p>
        <p>
          If RDCO approves, you can download that paper while signed in until the grant expires. A
          declined or expired request can be made again. A paper's owners, its Adviser, office
          staff and its assigned reviewers download without asking.
        </p>
      </>
    ),
  },
  {
    id: "ask-iris",
    title: "Asking IRIS",
    shownTo: (r) => canAccess(r.role, "ai"),
    body: (
      <>
        <p>
          Ask IRIS answers questions from the research you are allowed to read. Each answer cites
          the passages it is based on, with the page they come from; open a citation to go to that
          page of the paper and check it.
        </p>
        <p>
          Your conversations are saved, and only you can see them. Reopen one from the conversation
          list to carry on where you left off.
        </p>
        <p>
          When IRIS cannot write an answer, it says so and still shows the sources it found, rather
          than guessing.
        </p>
      </>
    ),
  },
  {
    id: "library",
    title: "Your Library",
    shownTo: (r) => canAccess(r.role, "library"),
    body: (
      <>
        <p>
          My Library holds the records you have saved. Nobody else can see it. Give a saved record a
          reading status (Want to read, Reading or Completed), and group saved records as you
          like.
        </p>
        <p>
          Your own research is listed there too. Reading history, the papers you opened recently,
          stays in this browser and is cleared when you sign out.
        </p>
      </>
    ),
  },
  {
    id: "calls",
    title: "Calls & Conferences",
    shownTo: (r) => canAccess(r.role, "opportunities"),
    body: (
      <p>
        Calls for papers and conferences open to the CIT-U research community. RDCO, KTTO and
        Advisers post them and keep them up to date.
      </p>
    ),
  },
  {
    id: "publishing",
    title: "Publishing your research",
    shownTo: (r) => canAccess(r.role, "submit"),
    body: (
      <>
        <p>
          Choose <strong>Publish</strong> on Discover to start a record. Pick its type (Proposal,
          Thesis / Research or Project), fill in its details, name your Adviser and upload the
          manuscript. Your Adviser cannot also be one of the record&rsquo;s owners.
        </p>
        <p>
          Once submitted, the record goes to your Adviser first. If anyone reviewing it asks for a
          revision, the record waits on you: make the changes and <strong>submit a new
          version</strong>. An accepted Proposal can be continued as a Thesis or Project.
        </p>
      </>
    ),
  },
  {
    id: "review-workflow",
    title: "How a record moves through review",
    body: (
      <>
        <p>
          Every record is reviewed by its Adviser first. A Proposal ends there: the Adviser accepts
          or rejects it, and an accepted Proposal is not published.
        </p>
        <p>
          For a Thesis / Research or Project, the Adviser can accept and publish it, or accept it
          and route it to the specialist offices whose questions it raises: ITSO for intellectual
          property, IERC for ethics and KTTO for commercialisation. Those offices review it at the
          same time, and each settles its own clearance. When the last one finishes, the record goes
          to RDCO, which decides: publish it, keep it unlisted, or reject it.
        </p>
        <p>
          Any reviewer may ask the owners for a revision. The owners answer with a new version, and
          only the offices that need to look again do so; clearances already given stand. A rejected
          record is archived and cannot be resubmitted: start a new record instead.
        </p>
      </>
    ),
  },
  {
    id: "reviewing",
    title: "Reviewing records",
    shownTo: reviews,
    body: (
      <>
        <p>
          My Reviews is your own review work: <strong>To review</strong>, <strong>In review</strong>{" "}
          and <strong>Done</strong>. It includes records your office holds that nobody has claimed
          yet; claim one to review it.
        </p>
        <p>
          Record your verdict with a written reason. A specialist office never rejects or returns a
          record itself: a negative verdict is a finding, and it travels to RDCO, which decides. To
          get changes made, request a revision; while it is open, the record waits on its owners.
        </p>
      </>
    ),
  },
  {
    id: "office-console",
    title: "Coordinating your office",
    shownTo: (r) => reviews(r) && r.reviewAccess?.is_coordinator === true,
    body: (
      <p>
        As your office&rsquo;s coordinator you see every review in your office, not only your own,
        and you assign its records to reviewers. Open the office console from My Reviews. You may
        also extend a due date, with a reason that stays visible beside the original date.
      </p>
    ),
  },
  {
    id: "analytics",
    title: "Workflow analytics",
    shownTo: (r) => canAccess(r.role, "reviewAnalytics"),
    body: (
      <p>
        Workflow analytics shows how review is going: your office&rsquo;s own figures, or every
        office&rsquo;s for RDCO. Open it from My Reviews.
      </p>
    ),
  },
  {
    id: "administration",
    title: "Administration",
    shownTo: (r) => canAccess(r.role, "audit"),
    body: (
      <>
        <p>The Administration part of the sidebar is RDCO&rsquo;s:</p>
        <ul>
          <li><strong>Role Requests</strong>: approve or decline the role someone asked for when they registered.</li>
          <li><strong>Users</strong>: change a role, lock or unlock an account, and name office coordinators.</li>
          <li><strong>Download Requests</strong> and <strong>Delete Requests</strong>: decide what readers and owners have asked for.</li>
          <li><strong>Import Records</strong>: file research on someone&rsquo;s behalf.</li>
          <li><strong>Audit Log</strong>: the record of workflow acts.</li>
        </ul>
      </>
    ),
  },
  {
    id: "account",
    title: "Your account",
    shownTo: (r) => canAccess(r.role, "settings"),
    body: (
      <>
        <p>
          Settings &amp; Profile, in the menu under your name, holds your profile (shown on records
          you author), your account and security, data privacy and consent, and your role.
        </p>
        <p>
          Notifications arrive under the bell at the top of the sidebar; <strong>View all
          notifications</strong> opens the full list. Forgot your password? Use <strong>Forgot password?</strong> on the
          sign-in screen.
        </p>
      </>
    ),
  },
  {
    id: "still-stuck",
    title: "Still stuck?",
    body: (
      <p>
        Contact the Research and Development Coordinating Office (RDCO). If something went wrong on
        a page, its error screen has details you can copy and send them.
      </p>
    ),
  },
];

/** The sections this reader sees, in order. */
export function sectionsFor(reader: HelpReader): HelpSection[] {
  return HELP_SECTIONS.filter((s) => !s.shownTo || s.shownTo(reader));
}
