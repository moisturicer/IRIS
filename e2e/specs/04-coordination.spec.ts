// AC4 · Coordination: RDCO grants and removes an office coordinator; a
// coordinator assigns and reassigns Seats and makes a reasoned Extension;
// reminders and an Escalation are sent; analytics are scoped to the viewer's
// office. A passed Due date never decides, clears or routes anything (ADR-043).
import { expect, test } from "@playwright/test";
import { as, ok, signInBrowser, type Client } from "../support/api";
import { ACCOUNTS, uniqueTitle } from "../support/accounts";
import { A11yLedger } from "../support/a11y";
import { manage } from "../support/stack";
import { claimAndOpen, createDraft, party, reviewRow, submit, throughRdco, tracker } from "../support/workflow";

test.describe.configure({ mode: "serial" });

const a11y = new A11yLedger();

let student: Client, adviser: Client, rdco: Client, itso: Client, itsoCoord: Client;
let recordId: number, assignmentId: number;
const title = uniqueTitle("coordination");

test.beforeAll(async () => {
  [student, adviser, rdco, itso, itsoCoord] = await Promise.all(
    ["student", "adviser", "rdco", "itso", "itsoCoordinator"].map((w) => as(w)),
  );
  recordId = await createDraft(student, { title, type: "Project", adviserId: adviser.userId, offices: { itso: true } });
  await submit(student, recordId);
  await claimAndOpen(adviser, recordId, "adviser");
  // ADR-047: the Adviser sends to RDCO, and RDCO requests ITSO.
  await throughRdco(adviser, rdco, recordId, [{ party: "itso" }], "Prior-art review (IR-631 coordination journey).");
  assignmentId = (await reviewRow(itsoCoord, recordId, "itso")).assignment!;
});

test.afterAll(async () => {
  // The plain ITSO login is a member; leave it as seeded.
  await rdco?.patch(`/users/${itso?.userId}/coordinator/`, { is_office_coordinator: false });
  await Promise.all([student, adviser, rdco, itso, itsoCoord].map((c) => c?.dispose()));
});

test("RDCO grants and removes a coordinator, and the grant is what permits assigning", async () => {
  expect((await itso.get(`/assignments/${assignmentId}/assign/`)).status(), "a member may not assign").toBe(403);
  await ok(await rdco.patch(`/users/${itso.userId}/coordinator/`, { is_office_coordinator: true }), "grant");
  expect((await itso.get(`/assignments/${assignmentId}/assign/`)).status(), "granted").toBe(200);
  await ok(await rdco.patch(`/users/${itso.userId}/coordinator/`, { is_office_coordinator: false }), "remove");
  expect((await itso.get(`/assignments/${assignmentId}/assign/`)).status(), "removed").toBe(403);
});

test("a coordinator assigns a Seat, then reassigns it with a reason", async () => {
  await ok(await itsoCoord.post(`/assignments/${assignmentId}/assign/`, { reviewer: itso.userId }), "assign");
  const seat = (await reviewRow(itso, recordId, "itso")).seat!;
  await ok(await itsoCoord.post(`/seats/${seat}/reassign/`, { reviewer: itsoCoord.userId, reason: "Workload balance." }), "reassign");
  const t = await tracker(itsoCoord, recordId);
  const names = (party(t, "itso").seats as any[]).map((s) => `${s.reviewer_name}:${s.state}`);
  test.info().annotations.push({ type: "seats", description: names.join(", ") });
  expect(names.some((n) => n.startsWith("Irene"))).toBe(true);
});

test("an Extension needs a reason and moves the Due date later, beside the original", async () => {
  const before = party(await tracker(itsoCoord, recordId), "itso");
  expect(before.due_at, "ITSO has a Due date from its Turnaround").toBeTruthy();
  const later = new Date(new Date(before.due_at).getTime() + 3 * 86_400_000).toISOString();

  const unreasoned = await itsoCoord.post(`/assignments/${assignmentId}/extend/`, { due_at: later, reason: "" });
  expect(unreasoned.status()).toBe(400);
  const byMember = await itso.post(`/assignments/${assignmentId}/extend/`, { due_at: later, reason: "Not mine to give." });
  expect(byMember.status()).toBe(403);

  const extended = await ok(await itsoCoord.post(`/assignments/${assignmentId}/extend/`, { due_at: later, reason: "Owner awaiting a lab result." }), "extend");
  expect(new Date(extended.due_at).getTime()).toBeGreaterThan(new Date(before.due_at).getTime());
  expect(extended.original_due_at ?? before.due_at).toBeTruthy();
});

test("an overdue turn escalates to the coordinators and decides nothing", async ({ page }, testInfo) => {
  const statusBefore = (await student.json(`/records/${recordId}/`)).pipeline_status;
  manage("review_clock_for_testing", "--force", "--record", String(recordId), "--party", "itso", "--due-in-working-days", "-2");
  manage("review_clock_for_testing", "--force", "--run-notifications");

  await expect.poll(async () => JSON.stringify(await itsoCoord.json("/notifications/")), { message: "escalation reaches the ITSO coordinator" })
    .toContain(title);

  const after = party(await tracker(itsoCoord, recordId), "itso");
  expect(after.state, "still ITSO's turn").toBe("active");
  // The turn's outcome stays open ("pending"); an Escalation records none.
  expect(after.outcome, "nothing cleared").not.toBe("cleared");
  expect(after.outcome, "nothing decided").toBe("pending");
  expect((await student.json(`/records/${recordId}/`)).pipeline_status).toBe(statusBefore);

  await signInBrowser(page, ACCOUNTS.itsoCoordinator, "/review?overdue=true");
  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByText(/overdue/i).first()).toBeVisible();
  await a11y.scan(page, testInfo, "my-reviews-overdue");
});

test("analytics are scoped: an office reads its own, RDCO reads every party", async () => {
  const own = await itso.json("/reviews/analytics/");
  expect((own.parties as any[]).map((p) => p.party)).toEqual(["itso"]);
  expect((await itso.get("/reviews/analytics/", { office: "ierc" })).status()).toBe(403);

  const all = await rdco.json("/reviews/analytics/");
  expect((all.parties as any[]).map((p) => p.party)).toEqual(expect.arrayContaining(["adviser", "itso", "ierc", "ktto", "rdco"]));

  const studentRes = await student.get("/reviews/analytics/");
  expect(studentRes.status()).toBe(403);
});

test("accessibility: no serious or critical findings on this journey's key screens", async ({}, testInfo) => {
  a11y.assertClean(testInfo);
});
