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

/**
 * A remark plugin: replaces a `math` / `inlineMath` node longer than
 * {@link MAX_FORMULA_CHARS} with code, so `rehype-katex` never sees it.
 * Runs after `remark-math`, which creates those nodes.
 */
export function remarkLimitMath() {
  return (tree: MdastNode) => {
    const walk = (node: MdastNode) => {
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
