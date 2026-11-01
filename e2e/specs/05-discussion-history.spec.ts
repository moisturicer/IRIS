// AC5 · Discussion and history: private comments and replies bound to the
// Version they were made on, the owner's next action, the review and version
// history, and RDCO's audit filters with a CSV export of every matching row.
import { expect, test } from "@playwright/test";
import { as, ok, signInBrowser, type Client } from "../support/api";
import { ACCOUNTS, uniqueTitle } from "../support/accounts";
import { expectNoSeriousA11yViolations, expectReflowsAt360 } from "../support/a11y";
import { newStudent } from "../support/people";
import { claimAndOpen, createDraft, newVersion, requestRevision, reviseAbstract, submit, tracker } from "../support/workflow";

test.describe.configure({ mode: "serial" });

let student: Client, adviser: Client, rdco: Client, ktto: Client, stranger: Client;
let recordId: number, firstComment: number;
const title = uniqueTitle("discussion");

test.beforeAll(async () => {
  [student, adviser, rdco, ktto] = await Promise.all(["student", "adviser", "rdco", "ktto"].map((w) => as(w)));
  stranger = await newStudent("reader");
  recordId = await createDraft(student, { title, type: "Thesis / Research", adviserId: adviser.userId });
  await submit(student, recordId);
  await claimAndOpen(adviser, recordId, "adviser");
});

test.afterAll(async () => {
  await Promise.all([student, adviser, rdco, ktto, stranger].map((c) => c?.dispose()));
});

test("a comment and its reply are bound to the Version they were made on", async () => {
  const c = await adviser.act(`/records/${recordId}/review-comments/`, { body: "Chapter 3's sample size needs a justification." });
  firstComment = c.id;
  expect(c.version).toBe(1);
  const reply = await student.act(`/records/${recordId}/review-comments/`, { body: "Added a power analysis.", reply_to: firstComment });
  expect(reply.reply_to).toBe(firstComment);
  expect(reply.version).toBe(1);
});

test("the discussion is private to the Record's participants", async () => {
  expect((await stranger.get(`/records/${recordId}/review-comments/`)).status()).toBe(404);
  const office = await ktto.get(`/records/${recordId}/review-comments/`);
  expect([403, 404], "an office not on this Record").toContain(office.status());
  if (office.ok()) expect(await office.text()).not.toContain("sample size");
});

test("the owner's next action follows a Revision request and the new Version", async ({ page }, testInfo) => {
  await requestRevision(adviser, recordId, "Please justify the sample size in Chapter 3.");
  let detail = await student.json(`/records/${recordId}/`);
  expect(detail.submitter_status.waiting_on_you, "waiting on the owner").toBeTruthy();

  await signInBrowser(page, ACCOUNTS.student, `/records/${recordId}`);
  await expect(page.getByText(detail.submitter_status.line)).toBeVisible();
  await expectNoSeriousA11yViolations(page, testInfo, "owner-next-action");
  await expectReflowsAt360(page, "owner-next-action");

  await reviseAbstract(student, recordId, "power analysis added");
  await newVersion(student, recordId);
  detail = await student.json(`/records/${recordId}/`);
  expect(detail.submitter_status.waiting_on_you, "no longer waiting on the owner").toBeFalsy();
});

test("history keeps both Versions and each comment's Version", async () => {
  await claimAndOpen(adviser, recordId, "adviser");
  const later = await adviser.act(`/records/${recordId}/review-comments/`, { body: "Thank you, resolved." });
  expect(later.version).toBe(2);

  const t = await tracker(student, recordId);
  expect((t.versions as any[]).map((v) => v.number)).toEqual([1, 2]);
  const byId = new Map((t.review_comments as any[]).map((c) => [c.id, c.version]));
  expect(byId.get(firstComment), "the first comment stays on v1").toBe(1);
  expect(byId.get(later.id)).toBe(2);
});

test("RDCO filters the audit log and the CSV export carries every matching row", async () => {
  const filter = { record: recordId, event_type: "RESUBMITTED" };
  const list = await rdco.json("/audit/", filter);
  const rows = Array.isArray(list) ? list : list.results;
  const total = Array.isArray(list) ? list.length : list.count;
  expect(total, "one resubmission on this Record").toBeGreaterThanOrEqual(1);
  expect(rows.every((r: any) => r.event_type === "RESUBMITTED")).toBe(true);

  const all = await rdco.json("/audit/", { record: recordId });
  const allTotal = Array.isArray(all) ? all.length : all.count;
  const csv = await rdco.get("/audit/export/", { record: recordId });
  expect(csv.status()).toBe(200);
  const lines = (await csv.text()).trim().split(/\r?\n/);
  expect(lines[0]).toContain("event_type");
  expect(lines.length - 1, "export rows == filtered list total").toBe(allTotal);

  for (const who of [student, adviser, ktto]) {
    expect((await who.get("/audit/", filter)).status(), `${who.email} may not read the audit log`).toBe(403);
    expect((await who.get("/audit/export/", { record: recordId })).status()).toBe(403);
  }
});

test("the stranger's own history and exports never mention the Record", async () => {
  expect(JSON.stringify(await stranger.json("/notifications/"))).not.toContain(title);
  const mine = await stranger.json("/records/mine/");
  expect(JSON.stringify(mine)).not.toContain(title);
});
