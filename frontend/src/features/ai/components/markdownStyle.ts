/**
 * The one Markdown style for a model's answer (IR-450): Ask IRIS chat, its
 * streaming bubble and the AI Overview all render through it, so a heading,
 * list or table cannot be styled on one surface and flattened on another.
 * Colours and table structure live in `tailwind.config.js` under `typography`.
 */
export const ANSWER_MARKDOWN =
  "chat-markdown prose prose-sm max-w-none prose-pre:my-2 prose-pre:bg-gray-900 prose-pre:text-gray-100";
