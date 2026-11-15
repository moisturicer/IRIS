import { useEffect, useRef, useState } from "react";

/**
 * Where focus goes when the control that opened a dialog is about to leave the
 * page (IR-1028). `useDialogFocus` gives focus back to the opener, but only
 * while the opener is still there; after an approval the row is gone, so focus
 * would drop to <body> and a keyboard user would restart from the top.
 *
 * Attach `ref` to a control that survives (a tab, Refresh), call `focusNext()`
 * with the state updates that remove the row, and focus lands there on the
 * commit after, once the dialog's own cleanup has run. It must be a control
 * that is not disabled while the list reloads.
 */
export function useFocusAfterCommit<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!pending) return;
    ref.current?.focus();
    setPending(false);
  }, [pending]);

  return { ref, focusNext: () => setPending(true) };
}
