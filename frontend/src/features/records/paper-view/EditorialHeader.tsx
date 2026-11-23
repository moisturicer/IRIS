import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ResearchOriginBadge } from "@/components/shared/ResearchOriginBadge";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import type { Capability, PaperSection } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordDetail, RecordVersion } from "@/types/records";
import { ContinueProposal } from "../ContinueProposal";
import { PersonChip } from "./PersonLink";
import { titleSizeClasses } from "./titleSize";
import { VersionPicker } from "./VersionPicker";

/** Where the paper came from, or went next (IR-1206). */
export function LineageLinks({ lineage }: { lineage: RecordDetail["lineage"] }) {
  return (
    <>
      {lineage?.derived_from && (
        <Link to={`/records/${lineage.derived_from.id}`} className="text-small underline">
          Developed from Proposal #{lineage.derived_from.id} — View proposal
        </Link>
      )}
      {lineage?.continued_as && (
        <Link to={`/records/${lineage.continued_as.id}`} className="text-small underline">
          Continued as {lineage.continued_as.record_type_name} #{lineage.continued_as.id}
        </Link>
      )}
    </>
  );
}

/** The one filled action a region offers (spec §4.6). */
export type PrimaryAction = "elsewhere" | "open_review" | "view" | "save";

interface EditorialHeaderProps {
  record: RecordDetail;
  section: PaperSection;
  can: ReadonlySet<Capability>;
  /** The header's filled action, as the page decides it. */
  primary: PrimaryAction;
  versions: RecordVersion[];
  latestVersion: RecordVersion | null;
  viewedVersion: RecordVersion | null;
  onChooseVersion: (n: number | null) => void;
  onOpenReview: () => Promise<void>;
  onEditDetails: () => void;
  /** In review: the type leads the byline, the version is short and the acts stand beside the title. */
  compact?: boolean;
  /** View, where there is a paper to view. */
  viewAction: ReactNode;
  /** Save, Cite and Share. */
  saveCiteShareActions: ReactNode;
}

/**
 * The editorial header (IR-356, moved out of the page unchanged in IR-1271):
 * what it is, who wrote it, then what to do with it. Not in Paper mode, where
 * the record bar holds the paper in one line (IR-569).
 */
export function EditorialHeader({
  record,
  section,
  can,
  primary,
  versions,
  latestVersion,
  viewedVersion,
  onChooseVersion,
  onOpenReview,
  onEditDetails,
  compact = false,
  viewAction,
  saveCiteShareActions,
}: EditorialHeaderProps) {
  const authorNames = record.authors.map((a) => a.name.trim()).filter(Boolean);
  const acts = (section !== "overview" || primary === "open_review" || can.has("edit_details")) && (
    <div className="flex items-center gap-2 flex-wrap">
      {primary === "open_review" && (
        <button type="button" onClick={() => void onOpenReview()} className={PILL_PRIMARY}>
          <i className="fas fa-clipboard-check text-xs" aria-hidden />
          Open review
        </button>
      )}

      {section !== "overview" && viewAction}

      {can.has("edit_details") && (
        <button type="button" onClick={onEditDetails} className={PILL_SECONDARY}>
          <i className="fas fa-pen text-2xs" aria-hidden />
          Edit details
        </button>
      )}

      {section !== "overview" && saveCiteShareActions}
    </div>
  );
  const picker = latestVersion && (
    <VersionPicker
      compact={compact}
      unsubmitted={record.manuscript_unsubmitted}
      versions={versions}
      viewing={viewedVersion?.number ?? null}
      onChoose={onChooseVersion}
    />
  );
  return (
    <header className={cn("space-y-5", section === "overview" && "pb-1")}>
      {/* Sized by its length (IR-1264), never cut. */}
      <div className={cn(compact && "flex flex-wrap items-start justify-between gap-x-6 gap-y-3")}>
        <h1 className={cn("min-w-0 font-display font-semibold tracking-tight text-stone-900 text-balance", compact && "flex-1 basis-80", titleSizeClasses(record.title))}>
          {record.title}
        </h1>
        {compact && acts}
      </div>

      {/* The byline (IR-1264): each author, then the Adviser when the
          record names one (IR-472), in their own pill. Where the record
          stands is in Record details for those in its review, and the
          year and what it is held under are Record details' rows
          (IR-1089), so the header carries neither. */}
      <div className="flex items-center gap-2 flex-wrap">
        {compact && record.record_type_name && <span className="mr-1 text-small font-medium text-stone-600">{record.record_type_name}</span>}
        {authorNames.length > 0 ? (
          <ul className="flex items-center gap-2 flex-wrap" aria-label="Authors">
            {authorNames.map((name) => {
              const owner = record.owners.find((candidate) => candidate.full_name.trim().toLocaleLowerCase() === name.toLocaleLowerCase());
              return (
                <li key={name}>
                  <PersonChip id={owner?.user} hasProfile={owner?.has_profile} name={name} role="Author" />
                </li>
              );
            })}
          </ul>
        ) : <p className="text-sm text-stone-500 italic">Authors not recorded</p>}
        {record.adviser_name && (
          <ul className="flex items-center gap-2 flex-wrap" aria-label="Adviser">
            <li>
              <PersonChip
                id={record.adviser ?? undefined}
                hasProfile={record.adviser != null && record.adviser_has_profile === true}
                name={record.adviser_name}
                role="Adviser"
              />
            </li>
          </ul>
        )}
        <ResearchOriginBadge origin={record.origin} />
        {compact && picker}
      </div>

      <LineageLinks lineage={record.lineage} />
      {can.has("continue_as") && <ContinueProposal recordId={record.id} />}
      {/* The version picker (IR-416) whenever there is a version,
          v1 alone included (IR-1214), and beside the owner's
          unsubmitted revision (IR-273). */}
      {!compact && picker}

      {!compact && acts}
    </header>
  );
}
