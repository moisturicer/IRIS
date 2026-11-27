/**
 * A tour's target counts only while someone could see it: in the page, and
 * not under an inert or hidden ancestor (the review pane is both while a
 * narrow window keeps it closed; the sidebar is inert behind a phone's menu).
 * Layout is not consulted, so the rule is the same with or without it.
 *
 * Shared by `GuidedTour`, which drops unreachable steps, and by the student
 * tours, which start only once a step is reachable (IR-1342).
 */
export function reachable(id: string): HTMLElement | null {
  const el = document.getElementById(id);
  return el && !el.closest('[inert],[aria-hidden="true"]') ? el : null;
}
