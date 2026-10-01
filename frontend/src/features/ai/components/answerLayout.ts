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
 * The AI Overview sits in a panel that can be wider than is comfortable to
 * read, so it takes a measure instead of `ANSWER_MARKDOWN`'s unbounded width.
 */
export const OVERVIEW_MARKDOWN = `${ANSWER_MARKDOWN.replace("max-w-none", "max-w-[70ch]")}`;

/**
 * The chat column, shared by the transcript and the composer below it so the
 * two cannot drift apart (IR-451).
 *
 * Viewport-relative with a cap, never a fixed pixel width: `92vw` keeps a
 * narrow screen usable without a horizontal scrollbar, and the 60rem cap is
 * the old `max-w-3xl` (48rem) plus two inches at 96px/in.
 */
export const CHAT_COLUMN = "w-full max-w-[min(92vw,60rem)] mx-auto";
