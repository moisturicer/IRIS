import { Link } from "react-router-dom";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { personPath } from "@/lib/access";
import { cn } from "@/lib/utils";

type PersonRole = "Author" | "Adviser";

/**
 * An author or the Adviser in the byline, each in their own pill (IR-1264): an
 * initials disc, then the name. An author's disc is maroon; the Adviser's is
 * white with a stone ring and the name is followed by "· Adviser", so the two
 * tell apart without a label in front. The role stays in the accessible name,
 * so a screen reader still hears "Ana Reyes, Author". A profile link is
 * rendered only when the API allows it; otherwise the name is plain text that
 * says it has no public profile.
 */
export function PersonChip({ id, name, role, hasProfile = false }: {
  id?: number;
  name: string;
  role: PersonRole;
  hasProfile?: boolean;
}) {
  const linked = hasProfile && id != null;
  const classes = cn(
    "inline-flex min-h-11 reading-split:min-h-9 items-center gap-2 rounded-full bg-stone-100 py-0.5 pl-0.5 pr-3.5 text-small font-semibold text-stone-900",
    linked && "hover:bg-stone-200 hover:text-brand",
    COLOUR_TRANSITION,
    linked && FOCUS_RING,
  );
  const chip = (
    <>
      <span
        className={cn(
          "w-7 h-7 shrink-0 rounded-full text-2xs font-semibold flex items-center justify-center",
          role === "Author" ? "bg-brand text-white" : "bg-white text-stone-900 ring-1 ring-inset ring-stone-300",
        )}
        aria-hidden
      >
        {initials(name)}
      </span>
      <span className="break-words">
        {name}
        {role === "Adviser" && (
          <span className="font-normal text-stone-600">
            <span aria-hidden> · </span>
            <span>Adviser</span>
          </span>
        )}
      </span>
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
