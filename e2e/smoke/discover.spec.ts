// IR-904 smoke: the catalogue a signed-in reader lands on, with the network mocked.
import { expect, test } from "./support/mock-api";
import { PAPER, discover, signedIn } from "./support/fixtures";

test("Discover lists the papers the catalogue returns and opens one", async ({ page, api }) => {
  await signedIn(page, api);
  discover(api);
  await page.goto("/");
  const link = page.getByRole("link", { name: new RegExp(PAPER.title) }).first();
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", `/records/${PAPER.id}`);
});

test("Discover says so when the catalogue is empty", async ({ page, api }) => {
  await signedIn(page, api);
  discover(api, []);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discover", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(PAPER.title) })).toHaveCount(0);
});

test("a path that does not exist shows the not-found screen inside the app", async ({ page, api }) => {
  await signedIn(page, api);
  discover(api);
  await page.goto("/this-page-does-not-exist");
  await expect(page.getByRole("heading", { name: /not found|can.t find|doesn.t exist/i }).first()).toBeVisible();
});
