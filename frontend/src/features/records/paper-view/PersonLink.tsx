import { Fragment } from "react";
import { Link } from "react-router-dom";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { personPath } from "@/lib/access";
import { cn } from "@/lib/utils";
import type { RecordOwner } from "@/types/records";

/** A person's name, opening their Profile (IR-700). Used only where the server says it can open. */
export function PersonLink({ id, name }: { id: number; name: string }) {
  return (
    <Link
      to={personPath(id)}
      className={cn("rounded-sm font-semibold text-stone-800 underline underline-offset-2 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
    >
      {name}
    </Link>
  );
}

/**
 * A published paper's owners, in the byline's meta row (IR-700). It shows only
 * when at least one owner has a Profile to open: owners are accounts, and the
 * authors above are byline names. An owner without a visible Profile (suspended
 * or former) is plain text in the list, never a link to a not-found page.
 */
export function OwnerNames({ owners }: { owners: RecordOwner[] | undefined }) {
  const list = owners ?? [];
  if (!list.some((owner) => owner.has_profile)) return null;
  return (
    <span>
      Owners:{" "}
      {list.map((owner, index) => (
        <Fragment key={owner.id}>
          {index > 0 && ", "}
          {owner.has_profile ? <PersonLink id={owner.user} name={owner.full_name} /> : owner.full_name}
        </Fragment>
      ))}
    </span>
  );
}
