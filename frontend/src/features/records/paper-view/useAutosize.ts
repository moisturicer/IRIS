import { useLayoutEffect, type RefObject } from "react";

/** The tallest a comment field grows before it scrolls, in px. */
const MAX_HEIGHT = 256;

/**
 * Grows a textarea with what is typed in it, up to a cap. An empty field keeps
 * its one-row height so its placeholder never sizes it.
 */
export function useAutosize(ref: RefObject<HTMLTextAreaElement | null>, value: string) {
  useLayoutEffect(() => {
    const field = ref.current;
    if (!field) return;
    field.style.height = "auto";
    if (value && field.scrollHeight > 0) field.style.height = `${Math.min(field.scrollHeight + 2, MAX_HEIGHT)}px`;
  }, [ref, value]);
}
