// Workflow steps through the same endpoints the review screens call
// (ADR-032). Each helper asserts the request succeeded, so a journey that
// fails names the step and the server's own message.
import { expect } from "@playwright/test";
import { Client, ok } from "./api";
import { manuscriptPdf } from "./pdf";

export type RecordTypeName = "Thesis / Research" | "Project" | "Proposal";

export async function recordTypeId(client: Client, name: RecordTypeName): Promise<number> {
  const body = await client.json("/records/record-types/");
  const list: { id: number; name: string }[] = Array.isArray(body) ? body : body.results;
  const found = list.find((t) => t.name === name);
  expect(found, `record type ${name}`).toBeTruthy();
  return found!.id;
}

export type DraftOptions = {
  title: string;
  type: RecordTypeName;
  adviserId: number;
  offices?: { itso?: boolean; ierc?: boolean; ktto?: boolean };
  withManuscript?: boolean;
  /** The manuscript's bytes, in place of the one-page default (IR-902). */
  manuscript?: Buffer;
  /** Year completed; the current year when absent. */
  yearAccomplished?: number;
};

/** A draft owned by `owner`, created through POST /records/ as Publish does. */
export async function createDraft(owner: Client, opts: DraftOptions): Promise<number> {
  const typeId = await recordTypeId(owner, opts.type);
  const fields: Record<string, string | { name: string; mimeType: string; buffer: Buffer }> = {
    title: opts.title,
    abstract: `Synthetic abstract for ${opts.title}. Written by the IR-631 core-journey run; not a real disclosure.`,
    record_type: String(typeId),
    adviser: String(opts.adviserId),
    origin: "synthetic",
    year_accomplished: String(opts.yearAccomplished ?? new Date().getFullYear()),
    requested_itso: String(Boolean(opts.offices?.itso)),
    requested_ierc: String(Boolean(opts.offices?.ierc)),
    requested_ktto: String(Boolean(opts.offices?.ktto)),
  };
  if (opts.withManuscript !== false) {
    fields.abstract_file = { name: "manuscript.pdf", mimeType: "application/pdf", buffer: opts.manuscript ?? manuscriptPdf(opts.title) };
  }
  const created = await ok(await owner.multipart("post", "/records/", fields), `create draft ${opts.title}`);
  return created.id as number;
}

export async function submit(owner: Client, recordId: number) {
  // No embargo question: every paper starts embargoed (ADR-052, IR-882).
  return owner.act(`/records/${recordId}/submit/`, { dpa_accepted: true });
}

export async function tracker(client: Client, recordId: number) {
  return client.json(`/records/${recordId}/tracker/`);
}

export function party(trackerBody: any, name: string) {
  const row = (trackerBody.parties as any[]).find((p) => p.party === name);
  expect(row, `tracker row for ${name}`).toBeTruthy();
  return row;
}

type ReviewRow = { record: number; seat: number | null; assignment: number | null; party: string; can_claim: boolean; kind: string };

/** The My Reviews row for this record and party, across every tab, waiting for it to appear. */
export async function reviewRow(client: Client, recordId: number, partyName: string, opts: { office?: string } = {}): Promise<ReviewRow> {
  let found: ReviewRow | undefined;
  await expect
    .poll(async () => {
      for (const tab of ["to_review", "in_review"]) {
        const params: Record<string, string> = { tab };
        if (opts.office) params.office = opts.office;
        const res = await client.get("/reviews/mine/", params);
        // A refusal is not "not there yet": fail with it rather than poll it away.
        if (!res.ok()) throw new Error(`GET /reviews/mine/?tab=${tab} as ${client.email} -> ${res.status()} ${(await res.text()).slice(0, 200)}`);
        const body = await res.json();
        found = (body.rows as ReviewRow[]).find((r) => r.record === recordId && r.party === partyName);
        if (found) return true;
      }
      return false;
    }, { message: `${client.email} sees ${partyName} work on record ${recordId} in My Reviews`, timeout: 20_000 })
    .toBe(true);
  return found!;
}

/** Claim from the pool when the row is unclaimed, then open the seat. Returns the seat id. */
export async function claimAndOpen(client: Client, recordId: number, partyName: string): Promise<number> {
  let row = await reviewRow(client, recordId, partyName);
  if (row.can_claim && row.assignment) {
    await client.act(`/assignments/${row.assignment}/claim/`);
    row = await reviewRow(client, recordId, partyName);
  }
  expect(row.seat, `${client.email} holds a ${partyName} seat on ${recordId}`).toBeTruthy();
  await client.act(`/seats/${row.seat}/open/`);
  return row.seat!;
}

/** Where a routing act sends the record: an office's pool, or the named officers in it. */
export type RouteTarget = { party: "itso" | "ierc" | "ktto"; nominees?: number[] };

/**
 * *Accept & send to RDCO*, the Adviser's only accept on a Thesis/Research or
 * Project (ADR-047 §1). It opens RDCO's assignment in its pool and routes no
 * office: only RDCO requests ITSO, IERC or KTTO (§2).
 */
export async function sendToRdco(adviser: Client, recordId: number, reason: string) {
  return adviser.act(`/records/${recordId}/accept-and-route/`, { to: [{ party: "rdco" }], reason });
}

/** A seated RDCO officer, or an office, requests review from `to`; their own turn stays active (ADR-047 §2). */
export async function route(router: Client, recordId: number, to: RouteTarget[], reason: string) {
  return router.act(`/records/${recordId}/route/`, { to, reason });
}

/**
 * The ADR-047 path to the specialist offices: the Adviser sends to RDCO, an
 * RDCO officer claims and opens RDCO's turn, and routes to `to`.
 */
export async function throughRdco(adviser: Client, rdco: Client, recordId: number, to: RouteTarget[], reason: string) {
  await sendToRdco(adviser, recordId, reason);
  await claimAndOpen(rdco, recordId, "rdco");
  return route(rdco, recordId, to, reason);
}

/**
 * What Publish asks before a submit the server finds likely duplicates for
 * (IR-832): the owner acknowledges every likely match it shows. Nothing to
 * acknowledge is not an error. Exact matches are refused, not acknowledged.
 */
export async function acknowledgeLikelyMatches(owner: Client, recordId: number) {
  const found = await owner.json(`/records/${recordId}/duplicate-matches/`);
  const ids = ((found.likely ?? []) as { id: number }[]).map((m) => m.id);
  if (ids.length === 0) return [];
  await owner.act(`/records/${recordId}/acknowledge-duplicates/`, { candidate_ids: ids });
  return ids;
}

export async function clear(reviewer: Client, recordId: number, comment: string) {
  return reviewer.act(`/records/${recordId}/office-review/`, { outcome: "cleared", comment });
}

export async function requestRevision(reviewer: Client, recordId: number, reason: string) {
  return reviewer.act(`/records/${recordId}/request-revision/`, { reason });
}

/**
 * A seated reviewer's comments are drafts until they finish their review
 * (IR-874). *Comment only* sends them and leaves the Seat open.
 */
export async function sendComments(reviewer: Client, recordId: number, summary: string) {
  return reviewer.act(`/records/${recordId}/finish-review/`, { verdict: "comment_only", summary });
}

/** Change a detail, which is what a new Version answers a revision with when no file changed (IR-273). */
export async function reviseAbstract(owner: Client, recordId: number, note: string) {
  const detail = await owner.json(`/records/${recordId}/`);
  return ok(
    await owner.patch(`/records/${recordId}/`, { abstract: `${detail.abstract} Revised: ${note}` }),
    `revise record ${recordId}`,
  );
}

export async function newVersion(owner: Client, recordId: number) {
  return owner.act(`/records/${recordId}/new-version/`);
}

/** The Adviser or RDCO releases the embargo, which publishing needs (ADR-052 §6, §14; IR-882). */
export async function releaseEmbargo(releaser: Client, recordId: number) {
  return releaser.act(`/records/${recordId}/embargo-release/`);
}

export async function decide(decider: Client, recordId: number, outcome: "accept" | "publish" | "keep_unlisted" | "reject", comment = "") {
  const detail = await decider.json(`/records/${recordId}/`);
  const token = detail.decision?.token;
  expect(token, `decision token for ${decider.email} on ${recordId}`).toBeTruthy();
  return decider.act(`/records/${recordId}/decide/`, { outcome, comment, token });
}

/**
 * Publish a submitted Thesis/Research or Project the shortest way ADR-047
 * allows: the Adviser sends it to RDCO, RDCO releases the embargo and
 * publishes. No office is requested, so no Clearance is exercised; journeys
 * that need a published paper to read or search for use this, and spec 01
 * covers the full routing (IR-902).
 */
export async function publishViaRdco(owner: Client, adviser: Client, rdco: Client, recordId: number) {
  await acknowledgeLikelyMatches(owner, recordId);
  await submit(owner, recordId);
  await claimAndOpen(adviser, recordId, "adviser");
  await sendToRdco(adviser, recordId, "Ready to publish (IR-902 journey).");
  await claimAndOpen(rdco, recordId, "rdco");
  await releaseEmbargo(rdco, recordId);
  await decide(rdco, recordId, "publish");
}
