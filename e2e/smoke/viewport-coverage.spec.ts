// IR-910: the matrix visits one screen per entry in support/screens.ts. The
// screens the application actually routes are listed in
// frontend/src/router/matrixRoutes.json, which the frontend's own test keeps
// equal to the route table. This spec holds the catalogue to that file, so a
// route cannot be added without a row here and a row cannot outlive its route.
// (The e2e suite is the one place allowed to read across stacks: CODING_STANDARDS X1.)
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { SCREENS } from "./support/screens";

const routed: string[] = JSON.parse(
  readFileSync(new URL("../../frontend/src/router/matrixRoutes.json", import.meta.url), "utf8"),
);
const catalogued = SCREENS.map((s) => s.route);

test("the matrix has a row for every routed screen", () => {
  expect(routed.filter((r) => !catalogued.includes(r)), "routes with no row in screens.ts").toEqual([]);
});

test("the matrix has no row for a route that is gone", () => {
  expect(catalogued.filter((r) => !routed.includes(r)), "rows in screens.ts for routes that no longer exist").toEqual([]);
});
