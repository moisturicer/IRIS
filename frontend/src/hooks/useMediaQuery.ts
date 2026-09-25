import { useEffect, useState } from "react";

/**
 * Whether a CSS media query matches, updated as it starts or stops matching
 * (IR-352). `false` wherever `matchMedia` does not exist (jsdom).
 *
 * For behaviour that has to follow a breakpoint; layout alone should stay in
 * Tailwind's responsive classes.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window.matchMedia === "function" && window.matchMedia(query).matches,
  );

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
