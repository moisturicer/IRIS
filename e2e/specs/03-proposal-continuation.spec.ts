// AC3 · Proposal: the Adviser accepts it, exactly one authorised Continuation
// is started even under simultaneous requests, the Continuation needs its own
// manuscript before it can be submitted, and the lineage reads both ways.
import { expect, test } from "@playwright/test";
import { as, ok, signInBrowser, type Client } from "../support/api";
import { ACCOUNTS, uniqueTitle } from "../support/accounts";
import { A11yLedger } from "../support/a11y";
import { manuscriptPdf } from "../support/pdf";
import { claimAndOpen, createDraft, decide, recordTypeId, submit, tracker, party } from "../support/workflow";

test.describe.configure({ mode: "serial" });

const a11y = new A11yLedger();

let student: Client, adviser: Client;
let proposalId: number, childId: number;
const title = uniqueTitle("proposal");

test.beforeAll(async () => {
  [student, adviser] = await Promise.all([as("student"), as("adviser")]);
});
test.afterAll(async () => {
  await Promise.all([student, adviser].map((c) => c?.dispose()));
});

test("the Adviser accepts the Proposal, and it rests as Accepted", async () => {
  proposalId = await createDraft(student, { title, type: "Proposal", adviserId: adviser.userId, withManuscript: false });
  await submit(student, proposalId);
  await claimAndOpen(adviser, proposalId, "adviser");
  await decide(adviser, proposalId, "accept");
  const t = await tracker(student, proposalId);
  expect(party(t, "adviser").state).toBe("completed");
  const detail = await student.json(`/records/${proposalId}/`);
  expect(detail.lineage.continued_as).toBeNull();
});

test("only an owner may start the Continuation", async () => {
  const thesis = await recordTypeId(student, "Thesis / Research");
  const res = await adviser.post(`/records/${proposalId}/continue-as/`, { record_type: thesis });
  expect([403, 404]).toContain(res.status());
});

test("two simultaneous requests start exactly one Continuation", async () => {
  const thesis = await recordTypeId(student, "Thesis / Research");
  const [a, b] = await Promise.all([
    student.post(`/records/${proposalId}/continue-as/`, { record_type: thesis }),
    student.post(`/records/${proposalId}/continue-as/`, { record_type: thesis }),
  ]);
  const statuses = [a.status(), b.status()].sort();
  expect(statuses, "one created, one refused as already continued").toEqual([201, 409]);
  const created = a.status() === 201 ? a : b;
  childId = (await created.json()).id;

  const again = await student.post(`/records/${proposalId}/continue-as/`, { record_type: thesis });
  expect(again.status(), "a third attempt is refused too").toBe(409);
});

test("the Continuation cannot be submitted without its own manuscript", async () => {
  await student.act(`/records/${childId}/embargo-answer/`, { embargoed: false });
  const refused = await student.post(`/records/${childId}/submit/`, { dpa_accepted: true });
  expect(refused.status()).toBe(400);
  expect(await refused.text()).toContain("manuscript");

  await ok(await student.multipart("patch", `/records/${childId}/`, {
    abstract_file: { name: "manuscript.pdf", mimeType: "application/pdf", buffer: manuscriptPdf(`${title} — full manuscript`) },
  }), "upload the Continuation's manuscript");
  await submit(student, childId);
  expect(party(await tracker(student, childId), "adviser").state).toBe("active");
});

test("lineage reads both ways, in the API and on the page", async ({ page }, testInfo) => {
  const child = await student.json(`/records/${childId}/`);
  const parent = await student.json(`/records/${proposalId}/`);
  expect(child.lineage.derived_from?.id).toBe(proposalId);
  expect(parent.lineage.continued_as?.id).toBe(childId);

  // The Paper View names the other record by type and id, not by title.
  await signInBrowser(page, ACCOUNTS.student, `/records/${proposalId}`);
  const forward = page.getByRole("link", { name: new RegExp(`^Continued as .+ #${childId}$`) });
  await expect(forward).toBeVisible();
  await a11y.scan(page, testInfo, "proposal-with-continuation");

  await forward.click();
  await expect(page).toHaveURL(new RegExp(`/records/${childId}$`));
  await expect(page.getByRole("link", { name: `Developed from Proposal #${proposalId} — View proposal` })).toBeVisible();
});

test("accessibility: no serious or critical findings on this journey's key screens", async ({}, testInfo) => {
  a11y.assertClean(testInfo);
});
