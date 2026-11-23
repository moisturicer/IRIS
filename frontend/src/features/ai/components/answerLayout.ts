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
export const ANSWER_MARKDOWN = [
  "chat-markdown prose prose-base max-w-none prose-pre:my-2 prose-pre:bg-stone-900 prose-pre:text-stone-100",
  // One reading type for every model answer (IR-1306): Ask IRIS and the AI
  // Overview set the same size, leading, headings and list markers, so the two
  // read as one voice. 16 px Inter at 1.75; any heading the model writes is a
  // 17 px ink Garamond line with room above it and no rule under it.
  "text-md prose-p:leading-[1.75] prose-li:leading-[1.75] prose-li:my-[0.3em] prose-li:marker:text-brand",
  "prose-headings:text-stone-900 prose-h1:border-b-0 prose-h2:border-b-0 prose-h1:pb-0 prose-h2:pb-0",
  "prose-h1:text-[1.0625em] prose-h2:text-[1.0625em] prose-h3:text-[1.0625em] prose-h4:text-[1.0625em]",
  "prose-h1:mt-[1.6em] prose-h2:mt-[1.6em] prose-h3:mt-[1.3em] prose-h1:mb-[0.35em] prose-h2:mb-[0.35em] prose-h3:mb-[0.3em]",
].join(" ");

/**
 * The AI Overview reads in the same type as an Ask IRIS answer (IR-1306,
 * replacing IR-569's larger lead paragraph and looser leading). It differs only
 * in that its paragraphs are justified, like the abstract (IR-1221), since it
 * is read top to bottom as an article.
 */
export const OVERVIEW_MARKDOWN = [
  ANSWER_MARKDOWN,
  // The same 17 px, pinned under the Overview's own 22 px heading (IR-1089).
  "prose-h1:text-lg prose-h2:text-lg prose-h3:text-lg prose-h4:text-lg",
  "[&_p]:text-justified",
].join(" ");

// The thread's width: one literal, so Tailwind sees the whole class.
const CHAT_MEASURE = "max-w-[min(92vw,136ch)]";

/**
 * The chat column, shared by the transcript and the composer below it so the
 * two cannot drift apart (IR-451).
 *
 * Viewport-relative with a cap, never a fixed pixel width: `92vw` keeps a
 * narrow screen usable without a horizontal scrollbar, and the cap is a
 * measure of 136 characters: twice IR-1090's 68, at the owner's request.
 */
export const CHAT_COLUMN = `w-full ${CHAT_MEASURE} mx-auto`;

/**
 * Up to this page width, and only here, Ask IRIS's conversations open as a
 * dialog over the chat (IR-1233, replacing IR-570's 900px rule for history).
 * A phone has no room to push the chat over; a tablet does. Read off the
 * page's own measured width, not the window's, so the app sidebar's state
 * counts.
 */
export const ASK_PHONE_MAX_PX = 640;

// Auto margins center the opening content and collapse when it needs to scroll.
export const CHAT_OPENING = "overflow-y-auto before:my-auto before:content-[''] after:my-auto after:content-['']";

export const CHAT_COMPOSER_SURFACE =
  "rounded-card border border-field bg-surface transition-[border-color,box-shadow] duration-150 hover:border-brand/50 hover:ring-4 hover:ring-brand/15 focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20 motion-reduce:transition-none";

// Grows with the question up to a cap; browsers without field-sizing keep `rows`.
export const CHAT_COMPOSER_FIELD =
  "resize-none caret-brand [field-sizing:content] max-h-40 overflow-y-auto scrollbar-thin";

// The opening's text, starter questions and composer share this width, which is
// the thread's own (IR-1090), so the page does not widen when the first answer lands.
// A new chat's prompt and its opening sit at IR-1090's narrower measure.
export const CHAT_OPENING_COLUMN = "mx-auto w-full max-w-[min(92vw,68ch)]";

// A round composer control: 44 px on touch, 36 px beside a pointer.
export const CHAT_COMPOSER_ICON =
  "inline-flex size-11 shrink-0 items-center justify-center rounded-full [@media(pointer:fine)]:size-9";

// Defined in index.css: it has to reach the end of a list as well as a paragraph.
export const CHAT_STREAM_CARET = "answer-caret";
