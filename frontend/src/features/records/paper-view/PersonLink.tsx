import { Link } from "react-router-dom";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { personPath } from "@/lib/access";
import { cn } from "@/lib/utils";

type PersonRole = "Author" | "Adviser";
const ROLE_AVATAR_STYLES: Record<PersonRole, string> = {
  Author: "bg-brand",
  Adviser: "bg-stone-700",
};

/**
 * A compact author/adviser chip. A profile link is rendered only when the API
 * allows it; otherwise the chip is plain text that says it has no public profile.
 */
export function PersonChip({ id, name, role, hasProfile = false }: {
  id?: number;
  name: string;
  role: PersonRole;
  hasProfile?: boolean;
}) {
  const classes = cn(
    "inline-flex min-h-11 items-center gap-2 rounded-full bg-white pl-1 pr-3.5 py-1 ring-1 ring-stone-200 text-small font-semibold text-stone-800",
    hasProfile && id != null && "hover:ring-brand-300 hover:text-brand",
    COLOUR_TRANSITION,
    hasProfile && id != null && FOCUS_RING,
  );
  const chip = (
    <>
      <span
        className={cn(
          "w-6 h-6 shrink-0 rounded-full text-white text-3xs font-bold flex items-center justify-center",
          ROLE_AVATAR_STYLES[role],
        )}
        aria-hidden
      >
        {initials(name)}
      </span>
      <span className="whitespace-nowrap">{name}</span>
      <span className="whitespace-nowrap border-l border-stone-200 pl-2 text-2xs font-medium text-stone-500">{role}</span>
    </>
  );

  if (hasProfile && id != null) {
    return (
      <Link to={personPath(id)} aria-label={`${name}, ${role}`} className={classes}>
        {chip}
      </Link>
    );
  }
  // Not a link: the API withholds a profile that would not open (an unverified
  // account, a paper that is not published). Say so, rather than leave a chip
  // that looks like its linked neighbours and does nothing (IR-1025).
  return (
    <span className={classes} title={NO_PROFILE_HINT}>
      {chip}
      <span className="sr-only">{NO_PROFILE_HINT}</span>
    </span>
  );
}

const NO_PROFILE_HINT = "No public profile available";

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}
