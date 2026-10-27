import { useId } from "react";

import { cn } from "@/lib/utils";

import { CONTROL_BASE, CONTROL_FILLED, CONTROL_SHAPE } from "./controls";
import { SectionHeading } from "./headings";

/**
 * Public discussion on a paper: the page's place for it, before it works
 * (IR-569; spec §8, IR-420).
 *
 * The surface is drawn so the layout is settled when the feature lands, and it
 * is plainly closed: the field and Post are disabled, the count is zero, and
 * a line says so. No comment is shown that nobody wrote (PRODUCT.md: do not
 * show unbuilt work as working).
 */
export function CommentsSection({ viewerName }: { viewerName: string | null }) {
  const id = useId();
  const initials = viewerName
    ?.split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <section aria-labelledby={`${id}-heading`}>
      <div className="flex items-baseline justify-between gap-3">
        <SectionHeading id={`${id}-heading`}>
          <span className="inline-flex items-baseline gap-2">
            Comments
            <span className="font-sans text-small font-semibold tabular-nums text-stone-500">0</span>
          </span>
        </SectionHeading>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-stone-100 px-2.5 py-1 text-xs font-semibold text-stone-600">
          <i className="fas fa-lock text-3xs" aria-hidden />
          Not open yet
        </span>
      </div>

      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 w-9 h-9 shrink-0 rounded-full bg-stone-200 text-stone-600 text-xs font-bold flex items-center justify-center"
          aria-hidden
        >
          {initials || <i className="fas fa-user text-2xs" />}
        </span>
        <div className="min-w-0 flex-1">
          <div className={cn("border border-stone-200 bg-stone-50", CONTROL_SHAPE)}>
            <label htmlFor={`${id}-field`} className="sr-only">
              Add a comment
            </label>
            <textarea
              id={`${id}-field`}
              disabled
              rows={2}
              placeholder="Add a comment…"
              aria-describedby={`${id}-note`}
              className="block w-full resize-none bg-transparent px-3.5 pt-3 text-sm text-stone-800 placeholder:text-stone-400 disabled:cursor-not-allowed focus:outline-none"
            />
            <div className="flex items-center justify-between gap-3 px-2 pb-2 pl-3.5">
              <p id={`${id}-note`} className="text-xs text-stone-500">
                Commenting is not open yet. Signed-in readers will post here.
              </p>
              <button type="button" disabled className={cn(CONTROL_BASE, CONTROL_FILLED, "px-4")}>
                Post
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 flex flex-col items-center gap-2 py-6 text-center">
        <i className="far fa-comments text-xl text-stone-300" aria-hidden />
        <p className="text-sm font-semibold text-stone-700">No comments yet</p>
        <p className="max-w-xs text-xs leading-relaxed text-stone-500">
          A discussion of this paper, one thread, newest last. Owners can hide a comment.
        </p>
      </div>
    </section>
  );
}
