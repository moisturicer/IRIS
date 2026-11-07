// IR-910: the matrix is only worth its green if its two measurements can fail.
// These run the helpers against pages built here, so a regression in the
// measuring (not in the application) shows up as this file going red.
import { expect, test } from "@playwright/test";
import { checkReachable, measureOverflow } from "../support/viewport";

test.use({ viewport: { width: 360, height: 740 } });

test("measureOverflow reports a page that scrolls sideways and names the element", async ({ page }) => {
  await page.setContent(`<body style="margin:0"><div id="wide" class="box" style="width:600px;height:20px"></div></body>`);
  const { overflow, culprits } = await measureOverflow(page);
  expect(overflow).toBe(240);
  expect(culprits[0]).toContain("div#wide.box");
});

test("measureOverflow does not count a scroll container's own overflow", async ({ page }) => {
  await page.setContent(
    `<body style="margin:0"><div style="overflow-x:auto;width:100%"><table style="width:900px"><tr><td>wide</td></tr></table></div></body>`,
  );
  expect((await measureOverflow(page)).overflow).toBe(0);
});

test("checkReachable accepts a control inside the window, even below the fold", async ({ page }) => {
  await page.setContent(`<body style="margin:0"><div style="height:2000px"></div><button id="go">Go</button></body>`);
  expect(await checkReachable(page.getByRole("button", { name: "Go" }))).toEqual({ reachable: true, reason: "" });
});

test("checkReachable rejects a control past the right edge", async ({ page }) => {
  await page.setContent(`<body style="margin:0"><button style="margin-left:340px;width:80px">Go</button></body>`);
  const result = await checkReachable(page.getByRole("button", { name: "Go" }));
  expect(result.reachable).toBe(false);
  expect(result.reason).toContain("sticks out sideways");
});

test("checkReachable rejects a control something else is covering", async ({ page }) => {
  await page.setContent(
    `<body style="margin:0"><button style="width:100px;height:40px">Go</button>` +
    `<div id="scrim" style="position:fixed;inset:0"></div></body>`,
  );
  const result = await checkReachable(page.getByRole("button", { name: "Go" }));
  expect(result.reachable).toBe(false);
  expect(result.reason).toContain("covered by div#scrim");
});

test("checkReachable says so when the control is not on the screen", async ({ page }) => {
  await page.setContent(`<body></body>`);
  expect((await checkReachable(page.getByRole("button", { name: "Go" }))).reason).toBe("not found on the screen");
});
