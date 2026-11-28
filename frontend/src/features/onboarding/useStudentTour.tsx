import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { GuidedTour } from "@/components/tour/GuidedTour";
import { reachable } from "@/components/tour/reachable";
import type { TourStep } from "@/components/tour/types";
import { PUBLISH_PARAM } from "@/features/publish/publishLink";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore } from "@/store/ui.store";

import { TOUR_LABELS } from "./studentTours";
import { TOUR_PARAM, type TourKey } from "./tourKeys";
import { saveToursOff, TOURS_OFF_LABEL, TOURS_SETTINGS_HREF } from "./toursOff";
import { useTourSession } from "./tourSession";

/** The app shell's `main`, where focus goes when a tour that started by itself closes. */
const MAIN_ID = "main-content";

interface Options {
  /**
   * The page has settled: its first read has finished. A tour never starts
   * before, because `GuidedTour` closes itself when no target is on screen,
   * and that would use the tour up on a page still loading (AC 6).
   */
  ready: boolean;
  steps: readonly TourStep[];
  /** Where to draw it; a dialog's panel for Publish (see `GuidedTour`). */
  container?: Element | null;
}

/**
 * A student's guided tour of one page (IR-1342). Returns the tour, or `null`.
 *
 * It starts by itself the first time a Student opens the page, once the page
 * is `ready` and one of its steps is on screen, and never for any other role
 * or an account still waiting for one (AC 4). Settings › Help starts it again
 * with `?tour=<key>`, seen or not (AC 5); the parameter is then removed, so
 * Back does not replay it.
 *
 * It is marked seen on the account when the student closes it (Skip tour,
 * Escape or Done) or leaves the page with it open, and only if a step was
 * shown (AC 6). Marking is optimistic: if the request fails, this session
 * still counts it as seen, so a flaky network never replays a tour.
 *
 * One tour at a time: a page's tour waits while Publish is open, and Publish
 * opening over it closes it without marking it, so it comes back on the
 * page's next visit.
 *
 * "Don't show tours again" (IR-1349): while the account has it set, no tour
 * starts by itself; Help's `?tour=` still starts one. The card shows it as a
 * tickbox, and whatever it holds is saved when a tour that showed a step
 * closes, as `tours_seen` is. Ticking it says so in a toast that opens
 * Settings › Help, where it is turned back on.
 */
export function useStudentTour(key: TourKey, { ready, steps, container }: Options): ReactNode {
  const user = useAuthStore((s) => s.user);
  const [params, setParams] = useSearchParams();
  const active = useTourSession((s) => s.active);
  const markedHere = useTourSession((s) => s.marked.has(key));
  const start = useTourSession((s) => s.start);
  const stop = useTourSession((s) => s.stop);

  const isStudent = user?.role_name === ROLES.STUDENT;
  // A payload without the field is not "seen nothing": start no tour on it.
  const seen = markedHere || !user?.tours_seen || user.tours_seen.includes(key);
  const off = user?.tours_off === true;
  const navigate = useNavigate();
  const asked = params.get(TOUR_PARAM) === key;
  const publishOpen = key !== "publish" && params.has(PUBLISH_PARAM);
  const running = active === key;

  const [forced, setForced] = useState(false);
  // Publish opened over this tour: it waits for the page's next visit.
  const [interrupted, setInterrupted] = useState(false);
  const shown = useRef(false);
  // The card's "Don't show tours again", as the student left it.
  const [ticked, setTicked] = useState(false);
  const tickedRef = useRef(false);
  tickedRef.current = ticked;
  const opener = useRef<HTMLElement | null>(null);
  const stepsRef = useRef(steps);
  stepsRef.current = steps;

  // Settings › Help's link: take it, then take it out of the address.
  useEffect(() => {
    if (!asked) return;
    setForced(true);
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete(TOUR_PARAM);
      return next;
    }, { replace: true });
  }, [asked, setParams]);

  const wanted = isStudent && ready && !publishOpen && !interrupted && active === null && (forced || (!seen && !off));

  useEffect(() => {
    if (!wanted) return;
    const tryStart = () => {
      if (!stepsRef.current.some((s) => reachable(s.target))) return false;
      const focused = document.activeElement;
      opener.current = focused instanceof HTMLElement && focused !== document.body
        ? focused
        : container
          ? container.closest<HTMLElement>('[role="dialog"]')
          : document.getElementById(MAIN_ID);
      shown.current = false;
      if (start(key)) {
        setForced(false);
        setTicked(useAuthStore.getState().user?.tours_off === true);
      }
      return true;
    };
    if (tryStart()) return;
    // The page is ready but its targets are not drawn yet (a child still
    // reading): start as soon as one is.
    const observer = new MutationObserver(() => {
      if (tryStart()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["id", "inert", "aria-hidden"] });
    return () => observer.disconnect();
  }, [wanted, key, start, container]);

  const markSeen = useCallback(() => {
    useTourSession.getState().mark(key);
    const current = useAuthStore.getState().user;
    if (!current || current.tours_seen?.includes(key)) return;
    const { updateUser } = useAuthStore.getState();
    updateUser({ ...current, tours_seen: [...(current.tours_seen ?? []), key] });
    accountsApi.markTourSeen(key).then(({ data }) => {
      const now = useAuthStore.getState().user;
      if (now && now.id === current.id && Array.isArray(data?.tours_seen)) {
        useAuthStore.getState().updateUser({ ...now, tours_seen: data.tours_seen });
      }
    }).catch(() => {
      /* Still seen for this session (`useTourSession.marked`); the next session asks again. */
    });
  }, [key]);

  // Saved as the tour closes, and only when it changed.
  const saveTicked = useCallback(() => {
    const value = tickedRef.current;
    if (value === (useAuthStore.getState().user?.tours_off === true)) return;
    const { addToast } = useUIStore.getState();
    void saveToursOff(value).then((saved) => {
      if (!saved) {
        addToast({ type: "error", message: `Could not save ${TOURS_OFF_LABEL}. Try again in Settings › Help.` });
      } else if (value) {
        addToast({
          type: "info",
          message: "Tours won't start by themselves. Turn them back on in Settings › Help.",
          action: { label: "Open Settings", onClick: () => navigate(TOURS_SETTINGS_HREF) },
        });
      }
    });
  }, [navigate]);

  const close = useCallback(() => {
    stop(key);
    if (shown.current) {
      markSeen();
      saveTicked();
    }
  }, [key, stop, markSeen, saveTicked]);
  const onShown = useCallback(() => { shown.current = true; }, []);

  // Publish opened over the page: close this tour unmarked (one tour at a time).
  useEffect(() => {
    if (running && publishOpen) {
      stop(key);
      setInterrupted(true);
    }
  }, [running, publishOpen, key, stop]);

  // Leaving the page with the tour open counts, if a step was shown.
  const markRef = useRef(markSeen);
  markRef.current = markSeen;
  const saveRef = useRef(saveTicked);
  saveRef.current = saveTicked;
  useEffect(() => () => {
    const session = useTourSession.getState();
    if (session.active !== key) return;
    session.stop(key);
    if (shown.current) {
      markRef.current();
      saveRef.current();
    }
  }, [key]);

  // Hidden in the same render Publish opens, so this tour hands focus back
  // before the dialog takes it, never after.
  if (!running || publishOpen) return null;
  return (
    <GuidedTour
      steps={steps}
      label={TOUR_LABELS[key]}
      opener={opener.current}
      onClose={close}
      onShown={onShown}
      container={container}
      optOut={{ label: TOURS_OFF_LABEL, checked: ticked, onChange: setTicked }}
    />
  );
}
