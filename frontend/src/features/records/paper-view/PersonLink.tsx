import { Link } from "react-router-dom";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { personPath } from "@/lib/access";
import { cn } from "@/lib/utils";
/** A compact author/adviser chip. A profile link is rendered only when the API allows it. */
export function PersonChip({ id, name, role, hasProfile = false }: {
  id?: number;
  name: string;
  role: "Author" | "Adviser";
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
          role === "Adviser" ? "bg-stone-700" : "bg-brand",
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
  return <span className={classes}>{chip}</span>;
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}
