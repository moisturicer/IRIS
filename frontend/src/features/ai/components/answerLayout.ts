/**
 * The one Markdown style for a model's answer (IR-450), and the one width the
 * chat column uses (IR-451). Ask IRIS chat, its streaming bubble and the AI
 * Overview all render through `ANSWER_MARKDOWN`, so a heading, list or table
 * cannot be styled on one surface and flattened on another. Colours, heading
 * rules and table structure live in `tailwind.config.js` under `typography`.
 *
 * `prose-base` rather than `prose-sm`: an answer is a reading surface, and
 * reads at 16px while the interface around it stays on the 13/14px scale --
 * the same split IR-356 made for titles on reading surfaces.
 */
export const ANSWER_MARKDOWN =
  "chat-markdown prose prose-base max-w-none prose-pre:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100";

/**
 * The AI Overview is an article, not a chat bubble (IR-569): a rhythm made for
 * reading it top to bottom. It fills its column; the Overview page sets that
 * column's width, so the text reaches the panel beside it without running long.
 *
 * - The first paragraph is the lead -- larger and darker, the plain-language
 *   account before the sections.
 * - A section heading is near-black Garamond with room above it and no rule
 *   under it (the answer style's rule and maroon are for a short reply).
 * - Lists take maroon markers and a looser line, so a list of claims reads as
 *   claims rather than a block of grey.
 */
export const OVERVIEW_MARKDOWN = [
  ANSWER_MARKDOWN,
  "prose-headings:text-stone-900 prose-h2:border-b-0 prose-h2:pb-0 prose-h2:mt-[2em] prose-h2:mb-[0.45em]",
  "prose-h3:mt-[1.5em] prose-h3:mb-[0.3em]",
  "prose-p:leading-[1.8] prose-li:leading-[1.75] prose-li:my-[0.35em] prose-li:marker:text-brand",
  "[&>p:first-child]:text-lg [&>p:first-child]:leading-[1.7] [&>p:first-child]:text-stone-800",
].join(" ");

/**
 * The chat column, shared by the transcript and the composer below it so the
 * two cannot drift apart (IR-451).
 *
 * Viewport-relative with a cap, never a fixed pixel width: `92vw` keeps a
 * narrow screen usable without a horizontal scrollbar, and the 60rem cap is
 * the old `max-w-3xl` (48rem) plus two inches at 96px/in.
 */
export const CHAT_COLUMN = "w-full max-w-[min(92vw,60rem)] mx-auto";

/**
 * Ask IRIS's history and sources sit beside the answer from this page width,
 * and open as drawers over it below (IR-570). It is the width at which the
 * answer column keeps 640px -- the reading minimum IR-569 holds the paper to
 * -- with the 260px history beside it. Read off the page's own measured width,
 * not the window's, so the app sidebar's state counts.
 */
export const ASK_PANELS_INLINE_PX = 900;
