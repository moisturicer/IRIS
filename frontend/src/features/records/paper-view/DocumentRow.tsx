/**
 * One document, as one compact row (IR-1203): its name, its latest version,
 * where any request for it stands, and what the viewer may do with it.
 *
 * The Documents tab draws every document filed with a record through this row
 * -- the manuscript, each document slot, an "Other" item a reviewer asked for,
 * a supplementary attachment. IR-971 adds Required/Optional labels and
 * Template links to it, and IR-973's Publish list reuses it, so it takes what
 * it shows from its caller and decides nothing itself.
 *
 * A document with more than one version keeps the rest one click away: the
 * row's versions toggle shows `versions` beneath it.
 */
import { useId, useState, type ReactNode } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

import { CONTROL_SIZE } from "./controls";

export interface DocumentRowProps {
  /** The document's name, which is also the row's accessible name. */
  name: string;
  /** The latest version in words, e.g. "v2 · Ana Cruz · Nov 3, 2026"; null when nothing is uploaded. */
  latest: string | null;
  /** Where a request for it stands, e.g. an `ItemStatusChip`. */
  status?: ReactNode;
  /** A line under the version: who asked, or why the last upload was refused. */
  note?: ReactNode;
  /** The row's controls: Download, Upload, Remove. */
  actions?: ReactNode;
  /** Every version, newest first, behind the row's toggle, and how many there are. */
  versions?: { count: number; list: ReactNode };
}

export function DocumentRow({
  name, latest, status, note, actions, versions,
}: DocumentRowProps) {
  const ids = useId();
  const [open, setOpen] = useState(false);
  const hasVersions = versions != null && versions.count > 0;
  const countWords = hasVersions ? `${versions.count} version${versions.count === 1 ? "" : "s"}` : "";
  return (
    <li>
      <div role="group" aria-labelledby={`${ids}-name`} className="space-y-1.5 px-card-compact py-3">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <div className="min-w-0">
            <h3 id={`${ids}-name`} className="break-words text-body font-semibold text-stone-900">{name}</h3>
            <p className="text-small text-stone-600">{latest ?? "Not uploaded yet"}</p>
          </div>
          {status}
        </div>
        {note && <div className="text-small text-stone-600">{note}</div>}
        {(actions || hasVersions) && (
          <div className="flex flex-wrap items-start gap-2">
            {actions}
            {hasVersions && (
              // The drawn words lead the name (WCAG 2.5.3), the document's name tells rows apart.
              <button type="button" aria-expanded={open} aria-controls={`${ids}-versions`}
                aria-label={`${countWords} of ${name}`} onClick={() => setOpen((o) => !o)}
                className={cn(CONTROL_SIZE, "inline-flex items-center gap-1.5 rounded-control px-2 text-small font-semibold text-stone-700 hover:text-brand", FOCUS_RING)}>
                <i className={cn("fas text-2xs", open ? "fa-chevron-up" : "fa-chevron-down")} aria-hidden />
                {countWords}
              </button>
            )}
          </div>
        )}
        {hasVersions && open && <div id={`${ids}-versions`}>{versions.list}</div>}
      </div>
    </li>
  );
}
