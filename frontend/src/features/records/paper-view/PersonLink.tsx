import { Link } from "react-router-dom";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { personPath } from "@/lib/access";
import { cn } from "@/lib/utils";

type PersonRole = "Author" | "Adviser";

/**
 * An author or adviser in the byline, as the prototype sets them: an author is
 * an avatar and a name, the Adviser is the word "Adviser" and a name, with no
 * pill around either. The role stays in the accessible name, so a screen reader
 * still hears "Ana Reyes, Author". A profile link is rendered only when the API
 * allows it; otherwise the name is plain text that says it has no public profile.
 */
export function PersonChip({ id, name, role, hasProfile = false }: {
  id?: number;
  name: string;
  role: PersonRole;
  hasProfile?: boolean;
}) {
  const linked = hasProfile && id != null;
  const classes = cn(
    "inline-flex min-h-11 items-center gap-2 rounded-full pl-0.5 pr-2.5 text-small font-semibold text-stone-900",
    linked && "hover:text-brand hover:underline",
    COLOUR_TRANSITION,
    linked && FOCUS_RING,
  );
  const chip = role === "Author" ? (
    <>
      <span
        className="w-7 h-7 shrink-0 rounded-full bg-brand text-white text-2xs font-semibold flex items-center justify-center"
        aria-hidden
      >
        {initials(name)}
      </span>
      <span>{name}</span>
    </>
  ) : (
    <>
      <span className="font-normal text-stone-500">{role}</span>
      <span>{name}</span>
    </>
  );

  if (linked) {
    return (
      <Link to={personPath(id)} aria-label={`${name}, ${role}`} className={classes}>
        {chip}
      </Link>
    );
  }
  // Not a link: the API withholds a profile that would not open (an unverified
  // account, a paper that is not published). Say so, rather than leave a name
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
