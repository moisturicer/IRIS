// AC2 · Thesis/Project: the thesis contribution, end to end on one build.
//
// Adviser-first review, the Adviser's send to RDCO and RDCO's routing to
// parallel office pools (ADR-047), claim and coordinator assignment, a
// document request and its fulfilment, a Revision request from one office, a
// new Version that resets only that office's Clearance while the others are
// preserved, and RDCO's Decision once every office has finished.
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
  claimAndOpen, clear, createDraft, decide, newVersion, party, releaseEmbargo,
  requestRevision, reviewRow, reviseAbstract, route, sendToRdco, submit, tracker,
} from "../support/workflow";

test.describe.configure({ mode: "serial" });

const a11y = new A11yLedger();

let student: Client, adviser: Client, itso: Client, ierc: Client, ktto: Client, kttoCoordinator: Client, rdco: Client;
let recordId: number;
const title = uniqueTitle("thesis");
const OFFICES = ["itso", "ierc", "ktto"] as const;

/** How many of `client`'s notifications name this journey's record. */
async function mentions(client: Client): Promise<number> {
  const body = await client.json("/notifications/");
  const list: unknown[] = Array.isArray(body) ? body : body.results;
  return list.filter((n) => JSON.stringify(n).includes(title)).length;
}

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
  for (const office of OFFICES) expect(party(t, office).state).not.toBe("active");
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

test("the Adviser sends to RDCO, and RDCO routes to three offices in parallel pools", async () => {
  // ADR-047 §1-2: the Adviser's only accept is the send to RDCO, which opens no
  // office. Only RDCO requests ITSO, IERC or KTTO.
  await sendToRdco(adviser, recordId, "Ready for the offices (IR-631 journey).");
  let t = await tracker(student, recordId);
  expect(party(t, "adviser").state, "the Adviser's turn completes on the send").toBe("completed");
  expect(party(t, "rdco").state, "RDCO's pool opens on the send").toBe("active");
  expect(party(t, "rdco").in_pool, "nobody named, so it waits in RDCO's pool").toBe(true);
  for (const office of OFFICES) expect(party(t, office).state, `${office} not yet requested`).not.toBe("active");

  await claimAndOpen(rdco, recordId, "rdco");
  await route(rdco, recordId, [
    { party: "itso" },                               // pool: a member claims it
    { party: "ierc", nominees: [ierc.userId] },      // nominated reviewer
    { party: "ktto" },                               // pool: the coordinator assigns it
  ], "Prior-art, ethics and commercialisation review (IR-631 journey).");

  t = await tracker(student, recordId);
  for (const office of OFFICES) expect(party(t, office).state, office).toBe("active");
  expect(party(t, "itso").in_pool).toBe(true);
  expect(party(t, "rdco").state, "routing keeps RDCO's own turn active").toBe("active");
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

test("IERC clears, RDCO still holds the record, and RDCO decides", async () => {
  await claimAndOpen(ierc, recordId, "ierc");
  const toldBefore = await mentions(rdco);
  await clear(ierc, recordId, "Consent form received.");

  // ADR-047 §4: RDCO holds the record from the Adviser's send onward. An office
  // finishing notifies RDCO and opens nothing, so there is no Hand-back and
  // RDCO decides from the seat it opened when it routed.
  await expect.poll(() => mentions(rdco), { message: "IERC finishing notifies RDCO" }).toBeGreaterThan(toldBefore);
  let t = await tracker(student, recordId);
  expect(party(t, "rdco").state, "RDCO's turn is still active").toBe("active");
  for (const office of OFFICES) expect(party(t, office).outcome, office).toBe("cleared");

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
