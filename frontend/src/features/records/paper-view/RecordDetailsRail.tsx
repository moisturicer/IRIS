import { StatusBadge } from "@/components/shared/StatusBadge";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";
import { ContactPersonCard } from "./ContactPersonCard";
import { EmbargoCard } from "./EmbargoCard";
import { PaperGovernance } from "./PaperGovernance";
import { OVERVIEW_ASIDE_MAX_HEIGHT, OVERVIEW_ASIDE_TOP } from "./paneLayout";
import { RdcoPaperControls } from "./RdcoPaperControls";
import { ReviewRoutingTracker } from "./ReviewRoutingTracker";
import { UnlistedCard } from "./UnlistedCard";

interface RecordDetailsRailProps {
  record: RecordDetail;
  /** The id of the rail's heading, which names the aside. */
  headingId: string;
  /** In the record's review: the routing tracker and every governance row. */
  participant: boolean;
  /** Folded away while Ask IRIS is open beside the page (IR-569). */
  hidden: boolean;
  /** Bumped when a document request changes, so the tracker reloads. */
  trackerVersion: number;
  onOpenHistory: () => void;
  onChanged: () => Promise<void>;
  onWithdrawn: () => void;
}

/**
 * The Overview's Record details (IR-1271, moved out of the page unchanged):
 * what the record is held under, and what is attached (spec §4.6). Beside
 * the page while it is wide, sticky under the record bar; under it
 * otherwise. The party status strip is for participants.
 */
export function RecordDetailsRail({
  record,
  headingId,
  participant,
  hidden,
  trackerVersion,
  onOpenHistory,
  onChanged,
  onWithdrawn,
}: RecordDetailsRailProps) {
  return (
    // Folds away while Ask IRIS is open (rows when it sits under the
    // page, the column when it sits beside), and is inert meanwhile.
    <div
      aria-hidden={hidden || undefined}
      {...(hidden ? { inert: "" } : {})}
      className={cn(
        "grid min-w-0 transition-[grid-template-rows,opacity,visibility] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none",
        // The track is the scroller's content box, so the aside can
        // fit what its own scrollbar leaves rather than the full
        // column (IR-1178).
        "overview-wide:sticky overview-wide:grid-rows-[1fr] overview-wide:grid-cols-[minmax(0,1fr)] overview-wide:overflow-y-auto overview-wide:overflow-x-hidden",
        OVERVIEW_ASIDE_TOP,
        OVERVIEW_ASIDE_MAX_HEIGHT,
        hidden ? "grid-rows-[0fr] opacity-0 invisible" : "grid-rows-[1fr] opacity-100",
      )}
    >
      <aside
        aria-labelledby={headingId}
        // The column's width, held while the column folds, but never
        // wider than the scroller leaves it: its scrollbar takes ~23px
        // and the scroller clipped every row's right edge (IR-1178).
        className="min-h-0 space-y-4 overflow-hidden overview-wide:w-[clamp(17rem,25cqw,22rem)] overview-wide:min-w-[15rem] overview-wide:max-w-full overview-wide:overflow-visible"
      >
        <h2 id={headingId} className="font-display text-section font-semibold text-stone-900">
          Record details
        </h2>
        {/* Where the record stands, for those in its review, with who
            has cleared it; the history is Review's (IR-1264). */}
        {participant && (
          <ReviewRoutingTracker
            key={trackerVersion}
            recordId={record.id}
            status={<StatusBadge state={record.workflow_state} label={record.workflow_state_label} compact />}
            onOpenHistory={onOpenHistory}
          />
        )}
        <PaperGovernance
          record={record}
          // Those in the review see every row; anyone else only the
          // ones that say something (IR-1264). Decided by participation,
          // never by role (IR-411).
          full={participant}
          showStatus={!participant}
        />
        <ContactPersonCard record={record} onChanged={onChanged} />
        <EmbargoCard record={record} onChanged={onChanged} />
        <UnlistedCard record={record} onChanged={onChanged} />
        <RdcoPaperControls
          record={record}
          onChanged={onChanged}
          onWithdrawn={onWithdrawn}
        />
        {/* No Documents card (IR-1244): Review's Documents tab lists them for
            those who may download them, and nobody else is sent them. */}
      </aside>
    </div>
  );
}
