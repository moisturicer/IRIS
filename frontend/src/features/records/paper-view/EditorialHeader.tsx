import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ResearchOriginBadge } from "@/components/shared/ResearchOriginBadge";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
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

/**
 * The one filled action a region offers (spec §4.6). A review is started on the
 * Review tab's cover, not from the header (IR-1336).
 */
export type PrimaryAction = "elsewhere" | "view" | "save";

interface EditorialHeaderProps {
  record: RecordDetail;
  section: PaperSection;
  can: ReadonlySet<Capability>;
  versions: RecordVersion[];
  latestVersion: RecordVersion | null;
  viewedVersion: RecordVersion | null;
  onChooseVersion: (n: number | null) => void;
  onEditDetails: () => void;
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
  versions,
  latestVersion,
  viewedVersion,
  onChooseVersion,
  onEditDetails,
  viewAction,
  saveCiteShareActions,
}: EditorialHeaderProps) {
  const authorNames = record.authors.map((a) => a.name.trim()).filter(Boolean);
  return (
    <header className={cn("space-y-5", section === "overview" && "pb-1")}>
      {/* Sized by its length (IR-1264), never cut. */}
      <h1 className={cn("font-display font-semibold tracking-tight text-stone-900 text-balance", titleSizeClasses(record.title))}>
        {record.title}
      </h1>

      {/* The byline (IR-1264): each author, then the Adviser when the
          record names one (IR-472), in their own pill. Where the record
          stands is in Record details for those in its review, and the
          year and what it is held under are Record details' rows
          (IR-1089), so the header carries neither. */}
      <div className="flex items-center gap-2 flex-wrap">
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
      </div>

      <LineageLinks lineage={record.lineage} />
      {can.has("continue_as") && <ContinueProposal recordId={record.id} />}
      {/* The version picker (IR-416) whenever there is a version,
          v1 alone included (IR-1214), and beside the owner's
          unsubmitted revision (IR-273). */}
      {latestVersion && (
        <VersionPicker
          unsubmitted={record.manuscript_unsubmitted}
          versions={versions}
          viewing={viewedVersion?.number ?? null}
          onChoose={onChooseVersion}
        />
      )}

      {(section !== "overview" || can.has("edit_details")) && (
        <div className="flex items-center gap-2 flex-wrap">
          {section !== "overview" && viewAction}

          {can.has("edit_details") && (
            <button type="button" onClick={onEditDetails} className={PILL_SECONDARY}>
              <i className="fas fa-pen text-2xs" aria-hidden />
              Edit details
            </button>
          )}

          {section !== "overview" && saveCiteShareActions}
        </div>
      )}
    </header>
  );
}
