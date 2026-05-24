import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type RefCallback,
} from "react";

interface DiscoverSearchContextValue {
  /** null = not on Discover (header search always shown). */
  heroSearchVisible: boolean | null;
  registerHeroSearch: RefCallback<HTMLElement>;
}

const DiscoverSearchContext = createContext<DiscoverSearchContextValue | null>(null);

export function DiscoverSearchProvider({ children }: { children: ReactNode }) {
  const [heroSearchVisible, setHeroSearchVisible] = useState<boolean | null>(null);
  const [heroNode, setHeroNode] = useState<HTMLElement | null>(null);

  const registerHeroSearch: RefCallback<HTMLElement> = useCallback((node) => {
    setHeroNode(node);
  }, []);

  useEffect(() => {
    if (!heroNode) {
      setHeroSearchVisible(null);
      return;
    }

    setHeroSearchVisible(true);

    const scrollRoot = heroNode.closest("main");
    const observer = new IntersectionObserver(
      ([entry]) => setHeroSearchVisible(entry.isIntersecting),
      {
        root: scrollRoot,
        threshold: 0,
        rootMargin: "-64px 0px 0px 0px",
      }
    );

    observer.observe(heroNode);
    return () => observer.disconnect();
  }, [heroNode]);

  const value = useMemo(
    () => ({ heroSearchVisible, registerHeroSearch }),
    [heroSearchVisible, registerHeroSearch]
  );

  return (
    <DiscoverSearchContext.Provider value={value}>{children}</DiscoverSearchContext.Provider>
  );
}

export function useDiscoverSearch() {
  const ctx = useContext(DiscoverSearchContext);
  if (!ctx) {
    throw new Error("useDiscoverSearch must be used within DiscoverSearchProvider");
  }
  return ctx;
}

/** Safe for Header — returns null visibility when provider missing. */
export function useHeaderSearchVisible() {
  const ctx = useContext(DiscoverSearchContext);
  if (!ctx) return true;
  if (ctx.heroSearchVisible === null) return true;
  return !ctx.heroSearchVisible;
}
