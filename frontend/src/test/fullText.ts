/**
 * What counts as a cut in the Full Text Rule (IR-1218, IR-1219; DESIGN.md).
 *
 * A cut is a class that ends text in an ellipsis: `truncate`, `text-ellipsis`
 * and any `line-clamp-*`, with or without a variant (`md:truncate`). Width caps,
 * fixed heights and `whitespace-nowrap` are judgement calls a reviewer makes
 * (CODING_STANDARDS F2), so they are not counted here. `line-clamp-none`
 * removes a clamp and passes.
 */
import { withoutComments } from "./radius";

const CUT = /(?<![\w-])(?:truncate|text-ellipsis|line-clamp-(?!none(?![\w-]))[\w[\]-]+)(?![\w-])/g;

/** Every cut class in `source`, in order of appearance, comments not read. */
export function cutClasses(source: string): string[] {
  return withoutComments(source).match(CUT) ?? [];
}
