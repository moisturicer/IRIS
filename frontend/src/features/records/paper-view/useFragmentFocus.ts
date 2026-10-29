import { useEffect } from "react";

/**
 * Bring the element a URL's `#fragment` names into view and give it focus,
 * once it exists (IR-625). A My Library link names a panel that renders only
 * after the record, and in the document-request panel's case its own fetch,
 * has loaded, so the browser's own jump finds nothing. The target needs
 * `tabIndex={-1}` to take focus. Gives up quietly when nothing by that id
 * appears: the request may have been answered meanwhile.
 */
export function useFragmentFocus(hash: string, ready: boolean) {
  useEffect(() => {
    const id = decodeURIComponent(hash.replace(/^#/, ""));
    if (!id || !ready) return;
    const land = () => focusFragmentTarget(id);
    if (land()) return;
    const observer = new MutationObserver(() => {
      if (land()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
    const timer = window.setTimeout(() => observer.disconnect(), 10_000);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
    };
  }, [hash, ready]);
}

/** Scroll to and focus the element with this id; false when it is absent. */
export function focusFragmentTarget(id: string): boolean {
  const target = document.getElementById(id);
  if (!target) return false;
  // jsdom has no scrollIntoView.
  target.scrollIntoView?.({ block: "start" });
  target.focus({ preventScroll: true });
  return true;
}
