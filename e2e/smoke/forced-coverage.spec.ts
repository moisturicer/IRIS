// IR-907: the forced-state tests cannot fall behind docs/ui-ux/17-ui-states-matrix.md.
//
// The matrix is a document, and (IR-906 said so) nothing failed when a surface
// dropped a state. This reads it: every cell that is not marked N/A needs a test
// that forces that state (support/matrix-proofs.ts says which), a cell marked N/A
// has none, and a row or column the table gains that the proofs do not know fails
// here instead of going unproved. The e2e suite is the one place allowed to read
// across stacks (CODING_STANDARDS X1), as dialog-coverage.spec.ts does.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { PROOFS, SURFACE_ROWS, type Proof, type Surface } from "./support/matrix-proofs";
import { STATES, type MatrixState } from "./support/states";

const MATRIX = fileURLToPath(new URL("../../docs/ui-ux/17-ui-states-matrix.md", import.meta.url));
const COLUMNS: MatrixState[] = ["loading", "empty", "error", "interrupted", "revoked"];

/** Each surface's cells, as the document marks them: `true` where it is N/A. */
function readMatrix(): Map<Surface, Record<MatrixState, boolean>> {
  const lines = readFileSync(MATRIX, "utf8").split(/\r?\n/);
  const header = lines.findIndex((l) => /^\|\s*Surface\s*\|\s*Loading\s*\|\s*Empty\s*\|\s*Error\s*\|\s*Interrupted\s*\|\s*Access revoked\s*\|/.test(l));
  if (header < 0) throw new Error("the matrix table's header row is not where this guard expects it");
  const rows = new Map<Surface, Record<MatrixState, boolean>>();
  for (const line of lines.slice(header + 2)) {
    if (!line.startsWith("|")) break;
    const cells = line.split("|").slice(1, -1).map((c) => c.trim());
    if (cells.length !== 6) throw new Error(`a matrix row does not have six cells: ${line.slice(0, 80)}`);
    const found = SURFACE_ROWS.find((r) => r.matches.test(cells[0]));
    if (!found) throw new Error(`the matrix has a surface the proofs do not know: ${cells[0]}`);
    if (rows.has(found.surface)) throw new Error(`two matrix rows read as the same surface: ${found.surface}`);
    rows.set(found.surface, Object.fromEntries(COLUMNS.map((state, i) => [state, /^N\/A/.test(cells[i + 1])])) as Record<MatrixState, boolean>);
  }
  return rows;
}

const matrix = readMatrix();

test("every surface in the matrix has proofs, and every surface with proofs is in the matrix", () => {
  expect([...matrix.keys()].sort()).toEqual(SURFACE_ROWS.map((r) => r.surface).sort());
  expect(Object.keys(PROOFS).sort()).toEqual([...matrix.keys()].sort());
});

const exists = (proof: Proof): boolean => {
  if ("catalogue" in proof) {
    const { screen, variant, read } = proof.catalogue;
    return STATES.some((s) => s.screen === screen && (variant === undefined || s.variant?.startsWith(variant)) && (read === undefined || s.read.path === read));
  }
  // A `test(` line that carries the title: a skipped, fixme'd or commented-out test is not one.
  return readFileSync(fileURLToPath(new URL(`./${proof.test.file}`, import.meta.url)), "utf8")
    .split(/\r?\n/).some((line) => /^\s*test\(/.test(line) && line.includes(proof.test.title));
};

for (const [surface, cells] of matrix) {
  for (const state of COLUMNS) {
    const proofs = PROOFS[surface][state] ?? [];
    if (cells[state]) {
      test(`${surface} · ${state}: marked N/A in the matrix, so nothing forces it`, () => {
        expect(proofs, `${surface} ${state} is N/A in the matrix but has proofs`).toEqual([]);
      });
      continue;
    }
    test(`${surface} · ${state}: has a forced-state test that exists`, () => {
      expect(proofs.length, `${surface} ${state} is a cell of the matrix with no forced-state test`).toBeGreaterThan(0);
      for (const proof of proofs) {
        expect(exists(proof), `no such state or test: ${JSON.stringify(proof)}`).toBe(true);
      }
      // A catalogue proof must reach THIS state, not only the screen.
      for (const proof of proofs.filter((p): p is Extract<Proof, { catalogue: unknown }> => "catalogue" in p)) {
        const { screen, variant, read } = proof.catalogue;
        expect(
          STATES.some((s) => s.state === state && s.screen === screen && (variant === undefined || s.variant?.startsWith(variant)) && (read === undefined || s.read.path === read)),
          `${JSON.stringify(proof.catalogue)} has no ${state} state in states.ts`,
        ).toBe(true);
      }
    });
  }
}
