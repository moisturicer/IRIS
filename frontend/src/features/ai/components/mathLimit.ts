import { BREAK } from "./runLimit";

/**
 * How much LaTeX the interface will typeset (IR-917).
 *
 * KaTeX cost grows faster than its input: measured in Node, 5,000 terms took
 * about 0.3 s and 20,000 about 5 s, all on the main thread, and an input with
 * ~2,000 nested braces throws a stack overflow that `throwOnError: false` does
 * not cover. Formulas in answers and passages come from manuscripts and a
 * model, so a hostile or merely broken one must not freeze or crash the page.
 * A real formula is a few hundred characters; past this length the source is
 * shown as text instead.
 */
export const MAX_FORMULA_CHARS = 2000;

interface MdastNode {
  type: string;
  value?: string;
  data?: unknown;
  children?: MdastNode[];
}

interface HastNode {
  value?: string;
  children?: HastNode[];
}

/** Removes every {@link BREAK} from the text under `nodes`, in place. */
function stripBreaks(nodes: HastNode[] | undefined): void {
  nodes?.forEach((node) => {
    if (typeof node.value === "string") node.value = node.value.split(BREAK).join("");
    stripBreaks(node.children);
  });
}

/**
 * A remark plugin: replaces a `math` / `inlineMath` node longer than
 * {@link MAX_FORMULA_CHARS} with code, so `rehype-katex` never sees it.
 * Runs after `remark-math`, which creates those nodes.
 */
export function remarkLimitMath() {
  return (tree: MdastNode) => {
    const walk = (node: MdastNode) => {
      if ((node.type === "math" || node.type === "inlineMath") && node.value?.includes(BREAK)) {
        // `breakLongRuns` cut a long run before parsing so the autolink scan
        // stays linear (IR-930); inside a formula the cut would be a stray
        // character in the LaTeX, so it goes back out before anything reads it.
        // `remark-math` keeps its own copy of the text for `rehype-katex`.
        node.value = node.value.split(BREAK).join("");
        stripBreaks((node.data as { hChildren?: HastNode[] } | undefined)?.hChildren);
      }
      if ((node.type === "math" || node.type === "inlineMath") && (node.value?.length ?? 0) > MAX_FORMULA_CHARS) {
        node.type = node.type === "math" ? "code" : "inlineCode";
        // `remark-math` tags the node (`language-math`) so `rehype-katex` finds
        // it; without clearing that, the code would be typeset anyway.
        delete node.data;
        return;
      }
      node.children?.forEach(walk);
    };
    walk(tree);
  };
}
