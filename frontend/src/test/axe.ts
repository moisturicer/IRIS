/**
 * axe-core against a rendered screen (IR-210).
 *
 * `docs/ui-ux/12-accessibility.md` §6 specifies the tool and the threshold:
 * "axe-core in CI, failing the build on serious/critical". That threshold is
 * why this is a hand-written assertion rather than `jest-axe`'s
 * `toHaveNoViolations`, which fails on **any** violation including `minor`.
 * Matching the documented rule matters more than saving twelve lines.
 *
 * **What this cannot check, stated rather than implied.** jsdom computes no
 * layout, so `color-contrast` cannot run -- it is disabled below instead of
 * being left to report "incomplete", because an incomplete result that nobody
 * reads is indistinguishable from a pass. Contrast stays a manual check, and
 * the same §6 says automated testing "should not be presented as coverage".
 * Everything this catches is real; plenty it does not catch is real too.
 */
import axe, { type AxeResults, type Result } from "axe-core";

/** The impacts that fail a build. `moderate` and `minor` are reported, not fatal. */
const BLOCKING_IMPACTS = new Set(["serious", "critical"]);

function format(violations: Result[]): string {
  return violations
    .map((violation) => {
      const targets = violation.nodes
        .map((node) => `      at ${node.target.join(" ")}`)
        .join("\n");
      return (
        `  [${violation.impact}] ${violation.id}: ${violation.help}\n` +
        `    ${violation.helpUrl}\n${targets}`
      );
    })
    .join("\n\n");
}

/**
 * Throw when `container` has any serious or critical accessibility violation.
 *
 * Takes the container from a render rather than scanning `document.body`, so
 * two screens rendered in one file cannot be attributed to each other.
 */
export async function expectNoBlockingA11yViolations(container: HTMLElement): Promise<void> {
  const results: AxeResults = await axe.run(container, {
    rules: {
      // See the module docstring: jsdom has no layout engine.
      "color-contrast": { enabled: false },
      // A rendered fragment is not a document, so landmark and page-level rules
      // report against the absence of a <main> this container never claimed to
      // have. They belong in an end-to-end test (IR-219), not here.
      region: { enabled: false },
    },
  });

  const blocking = results.violations.filter((v) => BLOCKING_IMPACTS.has(v.impact ?? ""));

  if (blocking.length > 0) {
    throw new Error(
      `axe-core found ${blocking.length} serious/critical accessibility ` +
        `violation(s):\n\n${format(blocking)}`,
    );
  }
}
