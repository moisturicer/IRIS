// IR-908: a dialog cannot ship unscanned. Every source file that is a dialog
// (named *Dialog or *Modal, drawing role="dialog" / "alertdialog", or a page that
// mounts a <Modal> or <ConfirmDialog> of its own) is either
// opened by a case in support/dialogs.ts or named in UNSCANNED with the reason.
// The e2e suite is the one place allowed to read across stacks (CODING_STANDARDS X1).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, test } from "@playwright/test";
import { DIALOGS, UNSCANNED } from "./support/dialogs";
import { SCREENS } from "./support/screens";

const SRC = new URL("../../frontend/src/", import.meta.url);

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx$/.test(name) && !/\.(test|stories)\.tsx$/.test(name) ? [path] : [];
  });
}

const root = decodeURIComponent(SRC.pathname).replace(/^\/([A-Za-z]:)/, "$1");
const isDialog = (path: string) =>
  /(Dialog|Modal)\.tsx$/.test(path) ||
  /(?<!\[)\brole=(\{[^}]*"(alert)?dialog"|"(alert)?dialog")|<(Modal|ConfirmDialog)\b/.test(readFileSync(path, "utf8"));
const dialogs = sources(root)
  .filter(isDialog)
  .map((path) => relative(root, path).replaceAll("\\", "/"))
  .sort();
const scanned = new Set(DIALOGS.flatMap((d) => d.sources));

test("every dialog source file is scanned or has a recorded reason it is not", () => {
  const undecided = dialogs.filter((f) => !scanned.has(f) && !(f in UNSCANNED));
  expect(undecided, "dialog files with no case in dialogs.ts and no entry in UNSCANNED").toEqual([]);
});

test("nothing is listed as both scanned and unscanned, and every entry names a real file", () => {
  expect(dialogs.filter((f) => scanned.has(f) && f in UNSCANNED), "listed both ways").toEqual([]);
  const known = new Set(dialogs);
  expect(
    [...scanned, ...Object.keys(UNSCANNED)].filter((f) => !known.has(f)),
    "named in dialogs.ts but not a dialog source file (renamed, deleted, or not a dialog)",
  ).toEqual([]);
});

test("every case opens from a screen that exists", () => {
  const ids = new Set(SCREENS.map((s) => s.id));
  expect(DIALOGS.filter((d) => !ids.has(d.screen)).map((d) => d.id)).toEqual([]);
});
