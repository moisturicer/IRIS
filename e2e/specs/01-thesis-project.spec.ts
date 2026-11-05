// AC2 · Thesis/Project: the thesis contribution, end to end on one build.
//
// Adviser-first review, parallel office pools, claim and coordinator
// assignment, a document request and its fulfilment, a Revision request from
// one office, a new Version that resets only that office's Clearance while
// the others are preserved, the Hand-back to RDCO and RDCO's Decision.
//
// Workflow acts go through the API the review screens call; what a reader of
// the record is shown about them is checked in the browser.
import { expect, test } from "@playwright/test";
import { as, anonymous, ok, signInBrowser, type Client } from "../support/api";
import { newStudent } from "../support/people";
import { manuscriptPdf } from "../support/pdf";
import { ACCOUNTS, uniqueTitle } from "../support/accounts";
import { A11yLedger } from "../support/a11y";
import {
  acceptAndRoute, claimAndOpen, clear, createDraft, decide, newVersion, party, releaseEmbargo,
  requestRevision, reviewRow, reviseAbstract, submit, tracker,
} from "../support/workflow";

test.describe.configure({ mode: "serial" });

const a11y = new A11yLedger();

let student: Client, adviser: Client, itso: Client, ierc: Client, ktto: Client, kttoCoordinator: Client, rdco: Client;
let recordId: number;
const title = uniqueTitle("thesis");

test.beforeAll(async () => {
  [student, adviser, itso, ierc, ktto, kttoCoordinator, rdco] = await Promise.all(
    ["student", "adviser", "itso", "ierc", "ktto", "kttoCoordinator", "rdco"].map((who) => as(who)),
  );
});

test.afterAll(async () => {
  await Promise.all([student, adviser, itso, ierc, ktto, kttoCoordinator, rdco].map((c) => c?.dispose()));
});

test("draft, edit, upload and submit enter adviser-first review", async () => {
  recordId = await createDraft(student, {
    title, type: "Project", adviserId: adviser.userId, offices: { itso: true, ierc: true, ktto: true },
  });
  await reviseAbstract(student, recordId, "edited while still a draft");
  await submit(student, recordId);

  const t = await tracker(student, recordId);
  expect(party(t, "adviser").state).toBe("active");
  for (const office of ["itso", "ierc", "ktto"]) expect(party(t, office).state).not.toBe("active");
});

test("the Adviser requests a document and the owner fulfils it", async () => {
  await claimAndOpen(adviser, recordId, "adviser");
  const created = await adviser.act(`/records/${recordId}/document-requests/`, {
    party: "adviser",
    message: "Please attach the signed adviser endorsement.",
    items: [{ label: "Signed adviser endorsement" }],
  });
  expect(created).toBeTruthy();
  let t = await tracker(student, recordId);
  expect(party(t, "adviser").awaiting_document).toBe(true);

  // Fulfilment is the owner's upload against the request's item (ADR-022
  // §3.2); the party that asked then accepts it (§3.4).
  const requests = (await student.json(`/records/${recordId}/document-requests/`)) as any[];
  const item = requests[0]?.items?.[0];
  expect(item, "the owner can read the open request and its item").toBeTruthy();
  await ok(await student.multipart("post", "/documents/submit/", {
    record: String(recordId),
    request_item: String(item.id),
    file: { name: "endorsement.pdf", mimeType: "application/pdf", buffer: manuscriptPdf("Signed adviser endorsement") },
  }), "owner fulfils the document request");
  await ok(await adviser.patch(`/document-request-items/${item.id}/`, { action: "accept" }), "adviser accepts the document");

  t = await tracker(student, recordId);
  expect(party(t, "adviser").awaiting_document).toBe(false);
});

test("the Adviser accepts and routes to three offices in parallel pools", async () => {
  await acceptAndRoute(adviser, recordId, [
    { party: "itso" },                               // pool: a member claims it
    { party: "ierc", nominee: ierc.userId },          // nominated reviewer
    { party: "ktto" },                               // pool: the coordinator assigns it
  ], "Prior-art, ethics and commercialisation review (IR-631 journey).");

  const t = await tracker(student, recordId);
  for (const office of ["itso", "ierc", "ktto"]) expect(party(t, office).state, office).toBe("active");
  expect(party(t, "itso").in_pool).toBe(true);
});

test("a member claims from the pool and a coordinator assigns a seat", async () => {
  await claimAndOpen(itso, recordId, "itso");

  const pooled = await reviewRow(kttoCoordinator, recordId, "ktto");
  expect(pooled.assignment).toBeTruthy();
  await kttoCoordinator.act(`/assignments/${pooled.assignment}/assign/`, { reviewer: ktto.userId });
  await claimAndOpen(ktto, recordId, "ktto");
  await claimAndOpen(ierc, recordId, "ierc");
});

test("two offices clear and IERC asks for a revision", async () => {
  await clear(itso, recordId, "Prior-art search complete; no conflict.");
  await clear(ktto, recordId, "Commercialisation potential noted.");
  await requestRevision(ierc, recordId, "Consent form for human participants is missing.");

  const t = await tracker(student, recordId);
  expect(party(t, "ierc").changes_requested).toBe(true);
  expect(party(t, "itso").outcome).toBe("cleared");
  expect(party(t, "ktto").outcome).toBe("cleared");
});

test("a new Version resets only IERC; ITSO and KTTO are preserved", async ({ page }, testInfo) => {
  await reviseAbstract(student, recordId, "consent form attached");
  await newVersion(student, recordId);

  const t = await tracker(student, recordId);
  expect(party(t, "itso").preserved, "ITSO kept").toBe(true);
  expect(party(t, "ktto").preserved, "KTTO kept").toBe(true);
  expect(party(t, "ierc").preserved, "IERC reset").toBe(false);
  expect(party(t, "ierc").state).toBe("active");

  // What the owner is shown: the Review timeline on the paper's own page.
  await signInBrowser(page, ACCOUNTS.student, `/records/${recordId}`);
  const row = (label: RegExp) => page.getByRole("row").filter({ has: page.getByRole("rowheader", { name: label }) });
  await expect(row(/ITSO/)).toContainText("Preserved");
  await expect(row(/KTTO/)).toContainText("Preserved");
  await expect(row(/IERC/)).not.toContainText("Preserved");
  await a11y.scan(page, testInfo, "paper-view-after-new-version");
  await a11y.reflow360(page, "paper-view-after-new-version");
});

test("IERC clears, the record is handed back to RDCO, and RDCO decides", async () => {
  await claimAndOpen(ierc, recordId, "ierc");
  await clear(ierc, recordId, "Consent form received.");

  let t = await tracker(student, recordId);
  expect(party(t, "rdco").state, "RDCO's pool opens on the Hand-back").toBe("active");

  await claimAndOpen(rdco, recordId, "rdco");
  // Every paper starts embargoed and an embargoed paper is never published.
  await releaseEmbargo(rdco, recordId);
  await decide(rdco, recordId, "publish");

  t = await tracker(student, recordId);
  expect(party(t, "rdco").state).toBe("completed");

  // Published means readable by any signed-in reader with no tie to the
  // record. The catalogue is not anonymous: the API's default permission is
  // IsAuthenticated, so a signed-out request is 401 whatever it asks for.
  const reader = await newStudent("reader");
  expect((await reader.get(`/records/${recordId}/`)).status(), "an unrelated reader reads it").toBe(200);
  await reader.dispose();
  const anon = await anonymous();
  expect((await anon.get(`/api/v1/records/${recordId}/`)).status(), "signed out").toBe(401);
  await anon.dispose();
});

test("accessibility: no serious or critical findings on this journey's key screens", async ({}, testInfo) => {
  a11y.assertClean(testInfo);
});
