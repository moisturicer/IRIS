// AC8 · Integrity under duplicate, concurrent, stale and retried requests.
//
// Judged on consistency only (IR-631 Q9): after the race, exactly one
// transition, one Seat, one Version, one notification. Latency is recorded
// as an annotation with no verdict -- no application target is agreed (IR-95).
import { expect, test } from "@playwright/test";
import { as, type Client } from "../support/api";
import { uniqueTitle } from "../support/accounts";
import { manage } from "../support/stack";
import {
  acceptAndRoute, claimAndOpen, createDraft, party, requestRevision,
  reviewRow, reviseAbstract, submit, tracker,
} from "../support/workflow";

let student: Client, adviser: Client, itso: Client, itsoCoord: Client, rdco: Client;

test.beforeAll(async () => {
  [student, adviser, itso, itsoCoord, rdco] = await Promise.all(
    ["student", "adviser", "itso", "itsoCoordinator", "rdco"].map((w) => as(w)),
  );
});
test.afterAll(async () => {
  await Promise.all([student, adviser, itso, itsoCoord, rdco].map((c) => c?.dispose()));
});

async function timed<T>(label: string, run: () => Promise<T>): Promise<T> {
  const start = performance.now();
  const out = await run();
  test.info().annotations.push({ type: "latency-ms (no target agreed)", description: `${label}: ${Math.round(performance.now() - start)}` });
  return out;
}

async function auditCount(recordId: number, eventType: string): Promise<number> {
  const body = await rdco.json("/audit/", { record: recordId, event_type: eventType });
  return Array.isArray(body) ? body.length : body.count;
}

test("a double submit makes one submission", async () => {
  const id = await createDraft(student, { title: uniqueTitle("double-submit"), type: "Thesis / Research", adviserId: adviser.userId });
  await student.act(`/records/${id}/embargo-answer/`, { embargoed: false });
  const [a, b] = await timed("2x submit", () => Promise.all([
    student.post(`/records/${id}/submit/`, { dpa_accepted: true }),
    student.post(`/records/${id}/submit/`, { dpa_accepted: true }),
  ]));
  expect([a.status(), b.status()].sort()).toEqual([200, 400]);
  expect(await auditCount(id, "SUBMITTED")).toBe(1);
  const t = await tracker(student, id);
  expect((t.versions as any[]).length, "one v1").toBe(1);
});

test("simultaneous claims of one pool make one Seat per reviewer", async () => {
  const id = await createDraft(student, { title: uniqueTitle("claims"), type: "Project", adviserId: adviser.userId, offices: { itso: true } });
  await submit(student, id);
  await claimAndOpen(adviser, id, "adviser");
  await acceptAndRoute(adviser, id, [{ party: "itso" }], "Integrity: concurrent claims.");
  const pool = await reviewRow(itso, id, "itso");

  const results = await timed("4x claim", () => Promise.all([
    itso.post(`/assignments/${pool.assignment}/claim/`),
    itso.post(`/assignments/${pool.assignment}/claim/`),
    itsoCoord.post(`/assignments/${pool.assignment}/claim/`),
    itsoCoord.post(`/assignments/${pool.assignment}/claim/`),
  ]));
  test.info().annotations.push({ type: "claim statuses", description: results.map((r) => r.status()).join(",") });
  const seats = party(await tracker(itsoCoord, id), "itso").seats as any[];
  const perReviewer = new Map<number, number>();
  for (const s of seats) perReviewer.set(s.reviewer, (perReviewer.get(s.reviewer) ?? 0) + 1);
  for (const [reviewer, n] of perReviewer) expect(n, `seats held by user ${reviewer}`).toBe(1);
  expect(await auditCount(id, "SEAT_CLAIMED")).toBe(seats.length);
});

test("a stale decision form is refused and changes nothing", async () => {
  const id = await createDraft(student, { title: uniqueTitle("stale"), type: "Proposal", adviserId: adviser.userId, withManuscript: false });
  await submit(student, id);
  await claimAndOpen(adviser, id, "adviser");
  const staleToken = (await adviser.json(`/records/${id}/`)).decision.token;

  // The record changes under the open dialog: a document request is opened.
  await adviser.act(`/records/${id}/document-requests/`, { message: "One more page, please.", items: [{ label: "Signed endorsement" }] });

  const res = await adviser.post(`/records/${id}/decide/`, { outcome: "accept", comment: "", token: staleToken });
  expect(res.status()).toBe(409);
  expect(party(await tracker(student, id), "adviser").state, "still the Adviser's turn").toBe("active");
  expect(await auditCount(id, "DECISION_RECORDED")).toBe(0);
});

test("a double new Version makes one Version", async () => {
  const id = await createDraft(student, { title: uniqueTitle("double-version"), type: "Thesis / Research", adviserId: adviser.userId });
  await submit(student, id);
  await claimAndOpen(adviser, id, "adviser");
  await requestRevision(adviser, id, "Integrity: please revise.");
  await reviseAbstract(student, id, "revised once");
  const [a, b] = await timed("2x new-version", () => Promise.all([
    student.post(`/records/${id}/new-version/`),
    student.post(`/records/${id}/new-version/`),
  ]));
  expect([a.status(), b.status()].sort()).toEqual([200, 400]);
  expect(((await tracker(student, id)).versions as any[]).map((v) => v.number)).toEqual([1, 2]);
  expect(await auditCount(id, "RESUBMITTED")).toBe(1);
});

test("a retried reminder job sends each notification once", async () => {
  const title = uniqueTitle("retried-job");
  const id = await createDraft(student, { title, type: "Project", adviserId: adviser.userId, offices: { itso: true } });
  await submit(student, id);
  await claimAndOpen(adviser, id, "adviser");
  await acceptAndRoute(adviser, id, [{ party: "itso" }], "Integrity: retried job.");
  manage("review_clock_for_testing", "--force", "--record", String(id), "--party", "itso", "--due-in-working-days", "-2");

  const mentions = async () => ((await itsoCoord.json("/notifications/")).results ?? (await itsoCoord.json("/notifications/")))
    .filter((n: any) => JSON.stringify(n).includes(title)).length;

  manage("review_clock_for_testing", "--force", "--run-notifications");
  await expect.poll(mentions).toBeGreaterThan(0);
  const once = await mentions();
  manage("review_clock_for_testing", "--force", "--run-notifications");
  manage("review_clock_for_testing", "--force", "--run-notifications");
  expect(await mentions(), "re-running the job sends nothing new").toBe(once);
  expect(await auditCount(id, "ASSIGNMENT_ESCALATED")).toBe(1);
});
