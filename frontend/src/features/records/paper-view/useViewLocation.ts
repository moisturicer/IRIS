import { useRef } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { landingSection, type PaperSection } from "@/features/records/capabilities";

import { reviewTargetFrom, type ReviewTarget } from "./reviewTarget";

export interface ViewLocation {
  /** The section shown: the one asked for, else the reader for a cited page, else Overview. */
  section: PaperSection;
  /** The section that holds this viewer's reader: Paper, else Review, else Overview. */
  readerSection: PaperSection;
  /** Review's Documents tab is asked for (`?documents=open`, or an old `?section=files`). */
  documentsWanted: boolean;
  /** The tab of Review a link asked for, and whose request in it; null for none. */
  reviewTarget: ReviewTarget | null;
  /** `?edit=details` is in the address. Whether the viewer may edit is the caller's to decide. */
  editRequested: boolean;
  /** The version `?version=` asks for, as a number (0 or NaN when none). */
  askedVersion: number;
  /** The location key of the last arrival. A view change made on this page keeps it. */
  arrivalKey: string;
  /** Set or clear view parameters in place, keeping the rest and the router state. */
  setViewParams: (changes: Record<string, string | null>) => void;
  setViewParam: (name: string, value: string | null) => void;
}

/**
 * Paper View's address (IR-1269, moved out of the page unchanged): reading
 * and writing its view parameters -- section, version, documents, edit --
 * and telling a new arrival apart from a view change made on the page.
 *
 * `sections` are the ones this viewer may open (capabilities adapter), and
 * `openAtPage` the page a citation or `?page=` asks for (useCitationLanding).
 */
export function useViewLocation({
  sections,
  openAtPage,
}: {
  sections: PaperSection[];
  openAtPage: number | null;
}): ViewLocation {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();

  // What counts as arriving. A change of section or of the Edit details
  // dialog rewrites the URL, which gives the location a new key, but nobody
  // arrived: the reader is still on this paper, in the conversation they had.
  // Such a change records the exact address it asked for, and a new key at
  // that address is the change landing; every other new key -- a citation, a
  // link, Back or Forward -- is an arrival. Read during render, and
  // idempotent there: a second render of the same location changes nothing.
  const viewChange = useRef<string | null>(null);
  const lastKey = useRef(location.key);
  const arrivalKey = useRef(location.key);
  if (location.key !== lastKey.current) {
    lastKey.current = location.key;
    if (viewChange.current === `${location.pathname}${location.search}`) viewChange.current = null;
    else arrivalKey.current = location.key;
  }

  const setViewParams = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [name, value] of Object.entries(changes)) {
      if (value == null) next.delete(name);
      else next.set(name, value);
    }
    const search = next.toString();
    viewChange.current = `${location.pathname}${search ? `?${search}` : ""}`;
    setSearchParams(next, { replace: true, state: location.state });
  };
  const setViewParam = (name: string, value: string | null) => setViewParams({ [name]: value });

  // The section asked for, else the reader for a citation's page -- Paper, or
  // a participant's Review, which holds their reader (IR-879) -- else
  // Overview. One the viewer may not open is Overview too, and a
  // participant's old Paper or Files link lands in Review.
  const landing = landingSection(searchParams.get("section"), sections);
  const readerSection: PaperSection = sections.includes("paper")
    ? "paper"
    : sections.includes("review")
      ? "review"
      : "overview";
  const section: PaperSection = landing?.section ?? (openAtPage != null ? readerSection : "overview");
  // Review's Documents tab (IR-1203; the drawer it replaced was IR-879):
  // `?documents=open`, or an old `?section=files`, opens it.
  const documentsWanted = section === "review" && (landing?.documents === true || searchParams.get("documents") === "open");

  return {
    section,
    readerSection,
    documentsWanted,
    reviewTarget: section === "review" ? reviewTargetFrom(searchParams) : null,
    editRequested: searchParams.get("edit") === "details",
    askedVersion: Number(searchParams.get("version")),
    arrivalKey: arrivalKey.current,
    setViewParams,
    setViewParam,
  };
}
