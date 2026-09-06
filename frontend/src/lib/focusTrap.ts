/**
 * The keyboard half of a modal dialog (IR-158).
 *
 * `Modal` had `role="dialog"` and `aria-modal` but no focus management, so Tab
 * walked straight out of the panel and into the page behind the backdrop. A
 * keyboard user could not stay inside a dialog that gates two irreversible
 * actions (reject confirmation, role approval).
 *
 * The wrap-around arithmetic lives here rather than in the component so it can
 * be tested without a DOM: `nextTrapFocus` is generic over the element type and
 * never inspects its arguments, only their identity and position. See
 * `focusTrap.test.ts`.
 */

/**
 * Every element a user can Tab to, in document order.
 *
 * `:not([disabled])` drops inert controls; `tabindex="-1"` is excluded because
 * it means "focusable by script, not by Tab", which is exactly the distinction
 * this list needs to honour.
 */
const TABBABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/** The tabbable elements inside `root`, in document order. */
export function tabbableWithin(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(TABBABLE)).filter(
    // `offsetParent` is null for anything `display: none`, which keeps hidden
    // panels (a collapsed section, a closed dropdown) out of the tab ring.
    // `position: fixed` elements report null too, so they are let through on
    // the strength of having a client rect instead.
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  );
}

/**
 * Where Tab should land next, staying inside `focusables`.
 *
 * Returns `null` when there is nothing to focus, which tells the caller to let
 * the keypress through rather than swallowing Tab and stranding the user in a
 * dialog with no way out.
 *
 * When `current` is not in the list — focus has already escaped the dialog, or
 * nothing is focused yet — this pulls it back to the near end: the first element
 * going forward, the last going backward.
 */
export function nextTrapFocus<T>(
  focusables: readonly T[],
  current: T | null,
  shiftKey: boolean,
): T | null {
  if (focusables.length === 0) return null;

  const index = current === null ? -1 : focusables.indexOf(current);

  if (index === -1) {
    return shiftKey ? focusables[focusables.length - 1] : focusables[0];
  }

  const delta = shiftKey ? -1 : 1;
  // `+ length` keeps the modulo positive when stepping backward off the front.
  const next = (index + delta + focusables.length) % focusables.length;
  return focusables[next];
}
