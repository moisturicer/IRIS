import { useCallback, useEffect, useState } from "react";
import { useAuthStore } from "@/store/auth.store";

export interface Pin { id: string; title: string }

function read(key: string): Pin[] {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(value) ? value.filter(p => typeof p?.id === "string" && typeof p?.title === "string") : [];
  } catch {
    return [];
  }
}

/**
 * The reader's pinned Conversations, kept in this browser only: a pin is a
 * convenience, not account state, and is not carried to another device.
 */
export function usePinnedConversations() {
  const userId = useAuthStore(s => s.user?.id);
  const key = `iris-runtime-pins:${userId ?? "anonymous"}`;
  const [pins, setPins] = useState<Pin[]>(() => read(key));
  useEffect(() => setPins(read(key)), [key]);

  const save = useCallback((update: (current: Pin[]) => Pin[]) => {
    setPins(current => {
      const next = update(current);
      try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* per-browser convenience */ }
      return next;
    });
  }, [key]);

  const toggle = useCallback((pin: Pin) => save(current =>
    current.some(p => p.id === pin.id) ? current.filter(p => p.id !== pin.id) : [pin, ...current]), [save]);
  const retitle = useCallback((id: string, title: string) => save(current =>
    current.some(p => p.id === id && p.title !== title)
      ? current.map(p => (p.id === id ? { ...p, title } : p)) : current), [save]);

  const unpin = useCallback((id: string) => save(current =>
    current.some(p => p.id === id) ? current.filter(p => p.id !== id) : current), [save]);

  return { pins, toggle, retitle, unpin };
}
