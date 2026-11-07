import { useEffect, useState } from "react";

import { profileApi } from "@/api/profile";

/**
 * An object URL for a photo served behind auth, or `null` while it loads,
 * when there is none, or when it cannot be fetched. The API authenticates with
 * a Bearer header, which an `<img src>` cannot send, so the photo is fetched
 * like a document is (IR-699). Shared by the Profile page and the edit page.
 */
export function useAuthedImage(photoUrl: string | null): string | null {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    setSrc(null);
    if (!photoUrl) return;
    let objectUrl: string | null = null;
    let current = true;
    profileApi.photo(photoUrl)
      .then(({ data }) => {
        if (!current) return;
        objectUrl = URL.createObjectURL(data);
        setSrc(objectUrl);
      })
      .catch(() => { if (current) setSrc(null); });
    return () => {
      current = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photoUrl]);
  return src;
}
