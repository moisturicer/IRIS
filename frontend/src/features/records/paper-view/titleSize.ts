/**
 * The Overview title's size, from its length (IR-1264).
 *
 * A short title keeps the page's large Garamond; a long one steps down so it
 * does not fill the first screen. Each step is smaller again while the
 * Overview is phone-width (the `overview-roomy` container variant, never the
 * window). The title is never cut (the Full Text Rule): only its size changes.
 *
 * | Characters | Overview from 40rem | Narrower |
 * |---|---|---|
 * | up to 80   | 48 px | 36 px |
 * | up to 160  | 36 px | 28 px |
 * | longer     | 30 px | 24 px |
 */
export const TITLE_SHORT_MAX = 80;
export const TITLE_LONG_MAX = 160;

export type TitleSize = "short" | "long" | "very-long";

export function titleSize(title: string): TitleSize {
  const length = title.trim().length;
  if (length <= TITLE_SHORT_MAX) return "short";
  if (length <= TITLE_LONG_MAX) return "long";
  return "very-long";
}

const SIZE_CLASSES: Record<TitleSize, string> = {
  short: "text-4xl leading-[1.08] overview-roomy:text-5xl",
  long: "text-display leading-[1.18] overview-roomy:text-4xl overview-roomy:leading-[1.12]",
  "very-long": "text-2xl leading-[1.25] overview-roomy:text-3xl overview-roomy:leading-[1.18]",
};

export function titleSizeClasses(title: string): string {
  return SIZE_CLASSES[titleSize(title)];
}
