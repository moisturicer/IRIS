import { cn } from "@/lib/utils";

import { useAuthedImage } from "./useAuthedImage";

interface PersonAvatarProps {
  /** Relative to the API base, or `null` for the initials. Fetched with auth. */
  photoUrl: string | null;
  initials: string;
  /** Spoken for the large photo; the small one beside a name is decoration. */
  alt?:     string;
  size:     "sm" | "lg";
}

/**
 * A person's circular photo, or their initials on Maroon Wash when they added
 * none or it has not arrived. `lg` is the Profile's mark (80 px on a phone, 112
 * from `sm`); `sm` sits beside a name in a list. Initials are Garamond only at
 * `lg`: a small one is a chip, and Garamond never sets a chip (DESIGN.md, Typeset
 * Title Rule).
 */
export function PersonAvatar({ photoUrl, initials, alt = "", size }: PersonAvatarProps) {
  const src = useAuthedImage(photoUrl);
  const box = size === "lg" ? "h-20 w-20 sm:h-28 sm:w-28" : "h-10 w-10";
  if (src) {
    return <img src={src} alt={alt} className={cn(box, "shrink-0 rounded-full object-cover ring-1 ring-stone-200")} />;
  }
  return (
    <span
      aria-hidden
      className={cn(
        box,
        "grid shrink-0 place-items-center rounded-full bg-brand-50 font-semibold text-brand",
        size === "lg" ? "font-display text-title sm:text-display" : "text-small",
      )}
    >
      {initials}
    </span>
  );
}
