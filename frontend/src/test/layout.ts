/**
 * Pretend every element is laid out (IR-516).
 *
 * jsdom computes no layout: every element has no `offsetParent` and no client
 * rects, so `tabbableWithin` -- which drops anything not rendered -- returns
 * nothing, and `Modal`'s focus trap lets Tab through untested. Giving each
 * element one client rect stands in for "rendered", which leaves the trap's
 * other rules (`visibility`, closed `<details>`, radio groups) deciding the
 * ring, as they do in a browser.
 *
 * Returns the spy; call `mockRestore()` on it when the test ends.
 */
import { vi } from "vitest";

export function pretendLaidOut() {
  return vi
    .spyOn(HTMLElement.prototype, "getClientRects")
    .mockReturnValue({ length: 1 } as unknown as DOMRectList);
}
