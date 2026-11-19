import { cn } from "@/lib/utils";
import type { Opportunity } from "@/types/opportunities";

import { eventDates, typeMeta } from "./opportunityUtils";

interface CallDetailsProps {
  call:    Opportunity;
  /** The title's id, so the Call's own region can be named by it. */
  titleId: string;
  /** Grey the title, for a Call whose submissions have closed. */
  muted?:  boolean;
  /**
   * Two lines of About, as the board shows it. RDCO reviewing a request reads
   * it whole (IR-765).
   */
  clampAbout?: boolean;
}

/**
 * What a Call is, as every screen shows it (IR-764, IR-765): type and the
 * Featured mark, the title, where and which Areas, the event's dates and the
 * fee when given, and About. The board, RDCO's Call Requests and a poster's
 * own Calls all draw it here, so a Call reads the same wherever it appears.
 */
export function CallDetails({ call: o, titleId, muted = false, clampAbout = true }: CallDetailsProps) {
  const type = typeMeta(o.opportunity_type);
  const when = eventDates(o);
  const meta = [o.location, ...(o.area_names ?? [])].filter(Boolean);

  return (
    <>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-label text-stone-600">
        <span className="inline-flex items-center gap-1.5 font-semibold text-stone-700">
          <i className={cn("fas", type.icon, "text-stone-500")} aria-hidden="true" />
          {type.label}
        </span>
        {o.is_featured && (
          <span className="inline-flex items-center gap-1 font-semibold text-brand">
            <i className="fas fa-star" aria-hidden="true" />
            Featured
          </span>
        )}
      </p>

      <h3
        id={titleId}
        className={cn(
          "font-display font-semibold text-title mt-1 break-words text-pretty",
          muted ? "text-stone-600" : "text-stone-900",
        )}
      >
        {o.title}
      </h3>

      {meta.length > 0 && (
        <p className="text-small text-stone-600 mt-1">
          {meta.map((text, i) => (
            <span key={i}>
              {i > 0 && <span aria-hidden="true" className="mx-1.5 text-stone-400">·</span>}
              <span>{text}</span>
            </span>
          ))}
        </p>
      )}

      {(when || o.registration_fee) && (
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-small text-stone-600 mt-1">
          {when && <span>Event: {when}</span>}
          {o.registration_fee && <span>Fee: {o.registration_fee}</span>}
        </p>
      )}

      {/* Justified only when whole: clamped, its last visible line is not the
          paragraph's last, and justifying would stretch it (IR-1221). */}
      {o.description && (
        <p className={cn("text-small text-stone-600 mt-2 max-w-prose whitespace-pre-line", clampAbout ? "line-clamp-2" : "text-justified")}>
          {o.description}
        </p>
      )}
    </>
  );
}
