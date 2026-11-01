// AC7 · Adversarial access: anonymous, another user, cross-office, guessed
// file ids and revoked permission fail safely, through the API and the UI,
// and a private Record never reaches search, history or an export.
//
// "Fail safely" has a precise meaning here (IR-153, IR-627): a Record the
// caller may not see answers exactly as a Record that does not exist, so no
// response confirms that someone's draft is there.
import { expect, test } from "@playwright/test";
import { anonymous, as, ok, signInBrowser, type Client } from "../support/api";
import { uniqueTitle } from "../support/accounts";
import { manuscriptPdf } from "../support/pdf";
import { NEW_PASSWORD, newStudent } from "../support/people";
import { claimAndOpen, createDraft, reviewRow, submit, acceptAndRoute } from "../support/workflow";

test.describe.configure({ mode: "serial" });

const MISSING = 2_000_000_000;
const title = uniqueTitle("access");
let owner: Client, adviser: Client, stranger: Client, itso: Client, ierc: Client;
let draftId: number, uploadId: number;

test.beforeAll(async () => {
  [owner, adviser, itso, ierc] = await Promise.all(["student", "adviser", "itso", "ierc"].map((w) => as(w)));
  stranger = await newStudent("stranger");
  draftId = await createDraft(owner, { title, type: "Thesis / Research", adviserId: adviser.userId });
  // The manuscript sits on the Record itself, so give the draft a slot upload
  // whose id a stranger could guess.
  const slots = await owner.json(`/documents/records/${draftId}/slots/`);
  expect(slots.length, "the record type has an upload slot").toBeGreaterThan(0);
  const upload = await ok(await owner.multipart("post", "/documents/uploads/create/", {
    record: String(draftId),
    slot: String(slots[0].id),
    file: { name: "supporting.pdf", mimeType: "application/pdf", buffer: manuscriptPdf(`${title} — supporting document`) },
  }), "owner uploads into a slot");
  uploadId = upload.id;
});

test.afterAll(async () => {
  await Promise.all([owner, adviser, stranger, itso, ierc].map((c) => c?.dispose()));
});

/** Status and body of a request, for comparing a hidden id against a missing one. */
async function probe(client: Client | null, path: string) {
  const ctx = client ?? null;
  if (ctx) {
    const res = await ctx.get(path);
    return { status: res.status(), body: await res.text() };
  }
  const anon = await anonymous();
  const res = await anon.get(`/api/v1${path}`);
  const out = { status: res.status(), body: await res.text() };
  await anon.dispose();
  return out;
}

const RECORD_PATHS = (id: number) => [
  `/records/${id}/`,
  `/records/${id}/tracker/`,
  `/records/${id}/manuscript/`,
  `/records/${id}/review-comments/`,
  `/records/${id}/document-requests/`,
];

test("anonymous: a draft answers as if it did not exist", async () => {
  for (const path of RECORD_PATHS(draftId)) {
    const hidden = await probe(null, path);
    const missing = await probe(null, path.replace(String(draftId), String(MISSING)));
    expect([401, 404], `${path} anonymous`).toContain(hidden.status);
    expect(hidden.status, `${path}: hidden == missing`).toBe(missing.status);
  }
});

test("another student: the same draft is a 404 like a missing id, and never listed", async () => {
  for (const path of RECORD_PATHS(draftId)) {
    const hidden = await probe(stranger, path);
    const missing = await probe(stranger, path.replace(String(draftId), String(MISSING)));
    expect(hidden.status, `${path} as a stranger`).toBe(404);
    expect(hidden.status, `${path}: hidden == missing`).toBe(missing.status);
  }
  const search = await stranger.json("/records/", { search: title });
  const rows = Array.isArray(search) ? search : search.results;
  expect(rows.map((r: any) => r.id)).not.toContain(draftId);
});

test("guessed file ids: a hidden Record's upload answers as a missing one", async () => {
  const hidden = await probe(stranger, `/documents/uploads/${uploadId}/download/`);
  const missing = await probe(stranger, `/documents/uploads/${MISSING}/download/`);
  expect(hidden.status).toBe(404);
  expect(hidden.status).toBe(missing.status);
  for (const path of [`/documents/uploads/?record=${draftId}`, `/documents/files/?record=${draftId}`, `/documents/files/download-all/?record=${draftId}`]) {
    expect((await stranger.get(path)).status(), path).toBeGreaterThanOrEqual(403);
  }
});

test("cross-office: ITSO cannot act on IERC's turn", async () => {
  await submit(owner, draftId);
  await claimAndOpen(adviser, draftId, "adviser");
  await acceptAndRoute(adviser, draftId, [{ party: "ierc", nominee: ierc.userId }], "Ethics review only (IR-631 access journey).");
  const res = await itso.post(`/records/${draftId}/office-review/`, { outcome: "cleared", comment: "Not my office." });
  expect([403, 404]).toContain(res.status());
  const t = await ierc.json(`/records/${draftId}/tracker/`);
  const row = (t.parties as any[]).find((p) => p.party === "ierc");
  expect(row.outcome, "IERC's clearance untouched").not.toBe("cleared");
});

test("revoked permission: a withdrawn seat can no longer act", async () => {
  const seatRow = await reviewRow(ierc, draftId, "ierc");
  const ierCoord = await as("iercCoordinator");
  const withdrawn = await ierCoord.post(`/seats/${seatRow.seat}/withdraw/`, { reason: "Reassigning (IR-631 access journey)." });
  test.info().annotations.push({ type: "withdraw", description: `HTTP ${withdrawn.status()}` });
  await ok(withdrawn, "coordinator withdraws IERC's seat");
  const res = await ierc.post(`/records/${draftId}/office-review/`, { outcome: "cleared", comment: "After withdrawal." });
  expect([403, 404, 400]).toContain(res.status());
  await ierCoord.dispose();
});

test("UI: a stranger opening the Record's address sees no part of it", async ({ page }) => {
  await signInBrowser(page, stranger.email, `/records/${draftId}`, NEW_PASSWORD);
  await expect(page.getByText(title)).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("exports: the stranger's audit and notification history never names the Record", async () => {
  const notes = await stranger.get("/notifications/");
  expect(await notes.text()).not.toContain(title);
  const audit = await stranger.get("/audit/");
  expect([401, 403]).toContain(audit.status());
});
