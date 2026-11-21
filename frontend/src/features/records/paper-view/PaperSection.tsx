import { Suspense, type ComponentProps, type ReactNode } from "react";

import { Skeleton } from "@/components/ui";
import { cn } from "@/lib/utils";
import type { RecordDetail, RecordVersion } from "@/types/records";
import { PaperDownloadControl } from "./PaperDownloadControl";
import { PaperPdfReader } from "./lazyReader";
import type { useReadingHighlights } from "./useReadingHighlights";
import { VersionBanner } from "./VersionPicker";

type ReaderProps = ComponentProps<typeof PaperPdfReader>;

interface PaperSectionProps {
  record: Pick<RecordDetail, "id" | "title" | "download" | "manuscript_unsubmitted">;
  /** The earlier version open in the reader, null for the current paper. */
  viewedVersion: RecordVersion | null;
  latestVersion: RecordVersion | null;
  /** Back from an earlier version to the current paper. */
  onShowCurrentVersion: () => void;
  /** Where a citation landed, when it is not simply the passage (citationLandingNotice). */
  landingNotice: string | null;
  highlightsNotice: ReturnType<typeof useReadingHighlights>["notice"];
  /** On the Paper tab, whose notices sit inset over the reader. */
  onPaperTab: boolean;
  /** The reader fills a full-height workspace: Paper, or Review. */
  workspace: boolean;
  contained: boolean;
  /** The version, at the start of the reader's toolbar where the bar has no room for it. */
  toolbarStart: ReactNode;
  /** A pending download request is shown in the record bar instead of here. */
  pendingInBar: boolean;
  onDownloadChanged: () => void;
  reader: Pick<
    ReaderProps,
    | "scrollToPage"
    | "keepPlace"
    | "highlightRegions"
    | "landingLook"
    | "navKey"
    | "highlights"
    | "selectionActions"
    | "highlightsShown"
    | "onHighlightsShownChange"
  >;
}

/**
 * The one reader (IR-352), for the Paper tab and the Review section alike:
 * a citation lands the same way in either (IR-354). Moved out of the page
 * unchanged (IR-1271): the version banner, the owner's unsubmitted-upload
 * notice, where a citation or highlight landed, and the lazy PDF reader.
 */
export function PaperSection({
  record,
  viewedVersion,
  latestVersion,
  onShowCurrentVersion,
  landingNotice,
  highlightsNotice,
  onPaperTab,
  workspace,
  contained,
  toolbarStart,
  pendingInBar,
  onDownloadChanged,
  reader,
}: PaperSectionProps) {
  return (
    <>
      {(viewedVersion || record.manuscript_unsubmitted) && (
      <div className={cn("space-y-3", onPaperTab && "px-4 pt-3")}>
      {viewedVersion && latestVersion && (
        <VersionBanner
          viewing={viewedVersion.number}
          latest={latestVersion.number}
          onBack={onShowCurrentVersion}
        />
      )}
      {/* The owner reads their own unsubmitted upload; nobody else is served
          it (IR-273), so only they are told. */}
      {!viewedVersion && record.manuscript_unsubmitted && (
        <div className="rounded-card border border-stone-300 bg-surface px-4 py-3 flex items-start gap-3">
          <i className="fas fa-file-pen text-sm text-brand mt-0.5" aria-hidden />
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-semibold text-stone-900">Your revised manuscript, not yet submitted</p>
            <p className="text-stone-700 mt-0.5">
              Reviewers still read {latestVersion ? `v${latestVersion.number}` : "the submitted version"} until
              you submit the new version.
            </p>
            <p className="text-stone-700 mt-0.5">
              Ask IRIS answers about the submitted version
              {latestVersion ? ` (v${latestVersion.number})` : ""} until you submit.
            </p>
          </div>
        </div>
      )}
      </div>
      )}
      {landingNotice && (
        <p role="status" className={cn("text-small text-stone-600", onPaperTab ? "px-4 pt-3" : "mb-3")}>
          {landingNotice}
        </p>
      )}
      {highlightsNotice && (
        <p role="status" className={cn("text-small", highlightsNotice.kind === "saved" ? "text-stone-600" : "font-semibold text-brand", onPaperTab ? "px-4 pt-3" : "mb-3")}>
          {highlightsNotice.text}
        </p>
      )}
      <Suspense fallback={<Skeleton rows={8} label="Loading the reader…" />}>
        <PaperPdfReader
          recordId={record.id}
          version={viewedVersion?.number ?? null}
          {...reader}
          contained={contained}
          fill={workspace}
          // Notes and Ask IRIS float over the Paper tab's bottom-right (IR-1079).
          clearCorner={onPaperTab}
          toolbarStart={toolbarStart}
          downloadControl={
            // An earlier version is not offered as a copy: the download route
            // serves only the current paper, and every copy must be marked.
            viewedVersion ? undefined : (
              <PaperDownloadControl
                recordId={record.id}
                recordTitle={record.title}
                download={record.download}
                fill={workspace}
                onChanged={onDownloadChanged}
                pending={pendingInBar ? "elsewhere" : "here"}
              />
            )
          }
        />
      </Suspense>
    </>
  );
}
