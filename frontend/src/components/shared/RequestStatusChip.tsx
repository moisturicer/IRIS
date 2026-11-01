import { TONES } from "@/components/ui/statusTones";
import { cn } from "@/lib/utils";

/**
 * A staff request's state, as a chip (IR-363): role, delete and download
 * requests all say the same thing the same way.
 *
 * Each state carries its word and, except a cancelled one, an icon, so it never
 * reads by colour alone (01-design-system.md section 0). Tones by meaning
 * (IR-358): pending is quiet grey, approved is near-black, declined and revoked
 * are maroon. An approval whose access has expired goes quiet again; the caller
 * puts the expiry beside it, so the grey is explained.
 */
export type RequestState = "pending" | "approved" | "declined" | "revoked" | "cancelled";

const STATES: Record<RequestState, { word: string; tone: string; icon: string | null }> = {
  pending:   { word: "Pending",   tone: TONES.quiet,     icon: "fa-clock" },
  approved:  { word: "Approved",  tone: TONES.settled,   icon: "fa-check" },
  declined:  { word: "Declined",  tone: TONES.attention, icon: "fa-xmark" },
  revoked:   { word: "Revoked",   tone: TONES.attention, icon: "fa-ban" },
  cancelled: { word: "Cancelled", tone: TONES.quiet,     icon: null },
};

type RequestStatusChipProps = {
  state: RequestState;
  /** An approval whose grant has run out: quiet, with an hourglass. */
  expired?: boolean;
};

export function RequestStatusChip({ state, expired = false }: RequestStatusChipProps) {
  const { word, tone, icon } = STATES[state];
  const lapsed = expired && state === "approved";
  const shownIcon = lapsed ? "fa-hourglass-end" : icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[12px] font-semibold",
        lapsed ? TONES.quiet : tone,
      )}
    >
      {shownIcon && <i className={cn("fas", shownIcon)} aria-hidden />}
      {word}
    </span>
  );
}
