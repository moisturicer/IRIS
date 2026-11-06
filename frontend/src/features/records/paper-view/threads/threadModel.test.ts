import { describe, expect, it } from "vitest";

import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail, ReviewComment } from "@/types/records";

import { comment } from "./threadFixtures";
import { countLabel, filterThreads, groupThreads, threadStatus, verdictOptions, type ThreadViewer, type VerdictFlags } from "./threadModel";

describe("groupThreads", () => {
  it("numbers sent threads 1, 2... and drafts D1, D2..., each with its replies", () => {
    const first = comment({ id: 10 });
    const draft = comment({ id: 11, is_draft: true });
    const second = comment({ id: 12 });
    const reply = comment({ id: 13, reply_to: 10, party: null, severity: null, state: null });
    const { sent, drafts } = groupThreads([first, draft, second, reply]);

    expect(sent.map((t) => [t.pin, t.root.id, t.replies.map((r) => r.id)])).toEqual([
      ["1", 10, [13]],
      ["2", 12, []],
    ]);
    expect(drafts.map((t) => [t.pin, t.root.id])).toEqual([["D1", 11]]);
  });
});

describe("countLabel", () => {
  it("counts open sent threads by severity, as the Threads tab reads", () => {
    const { sent } = groupThreads([
      comment({ severity: "must_fix" }),
      comment({ severity: "must_fix" }),
      comment({ severity: "must_fix", state: "resolved" }),
      comment({ severity: "suggestion" }),
      comment({ party: null, severity: null }),
    ]);
    expect(countLabel(sent)).toBe("2 must fix · 1 suggestion");
  });

  it("leaves out a side with none open", () => {
    expect(countLabel(groupThreads([comment(), comment(), comment()]).sent)).toBe("3 suggestions");
  });

  it("says nothing when no reviewer's thread is open", () => {
    expect(countLabel(groupThreads([comment({ state: "resolved" })]).sent)).toBe("");
  });
});

describe("threadStatus", () => {
  it.each([
    [{ state: "resolved" as const }, "Resolved"],
    [{ state: "closed" as const }, "Closed by Decision"],
    [{ answer: { kind: "addressed" as const, note: "§4", by: "A", at: null } }, "Addressed"],
    [{ answer: { kind: "declined" as const, note: "No", by: "A", at: null } }, "Declined"],
    [{}, "No answer"],
    [{ party: null, severity: null }, null],
  ])("%o reads %s", (over, label) => {
    expect(threadStatus(comment(over))).toBe(label);
  });
});

describe("filterThreads", () => {
  const mine = comment({ author: 5, party: "itso" });
  const partyMate = comment({ author: 6, party: "itso" });
  const other = comment({ author: 7, party: "adviser" });
  const done = comment({ author: 7, party: "adviser", state: "resolved" });
  const closed = comment({ author: 7, party: "adviser", state: "closed" });
  const { sent } = groupThreads([mine, partyMate, other, done, closed]);
  const ids = (f: Parameters<typeof filterThreads>[1], who: ThreadViewer = { userId: 5, party: "itso" }) =>
    filterThreads(sent, f, who).map((t) => t.root.id);

  it("Open is every open thread", () => expect(ids("open")).toEqual([mine.id, partyMate.id, other.id]));
  it("Yours is what you wrote and your party's, open or not", () =>
    expect(ids("yours")).toEqual([mine.id, partyMate.id]));
  it("Yours for someone with no party is only what they wrote", () =>
    expect(ids("yours", { userId: 7, party: null })).toEqual([other.id, done.id, closed.id]));
  it("Resolved includes the ones a Decision closed", () => expect(ids("resolved")).toEqual([done.id, closed.id]));
  it("All is every sent thread", () => expect(ids("all")).toHaveLength(5));
});

describe("verdictOptions", () => {
  const flags = (over: Partial<VerdictFlags> = {}): VerdictFlags => ({
    revision: { blocked: null, decision_blocked: null, label: "ITSO" } as RecordDetail["revision"],
    routing: { send_to_rdco_blocked: null } as RecordDetail["routing"],
    office_review: { label: "ITSO", blocked: null, clear_blocked: null } as RecordDetail["office_review"],
    decision: { blocked: null, blocked_outcomes: {}, reason_required: false } as unknown as RecordDetail["decision"],
    ...over,
  });
  const offered = (caps: Capability[], f = flags(), drafts: ReviewComment[] = []) =>
    verdictOptions(new Set<Capability>(["finish_review", ...caps]), f, drafts);

  it("offers Comment only, then exactly the verdicts the capabilities grant", () => {
    expect(offered(["office_review", "request_revision"]).map((o) => [o.verdict, o.label])).toEqual([
      ["comment_only", "Comment only"],
      ["cleared", "Clear for ITSO"],
      ["finding", "Record a finding"],
      ["request_revision", "Request revision"],
    ]);
  });

  it("offers nothing without finish_review", () => {
    expect(verdictOptions(new Set<Capability>(["reject"]), flags(), [])).toEqual([]);
  });

  it("holds an approval with the server's reason", () => {
    const f = flags({ office_review: { label: "ITSO", blocked: null, clear_blocked: "ITSO has 1 open Must fix thread." } as RecordDetail["office_review"] });
    const byVerdict = Object.fromEntries(offered(["office_review"], f).map((o) => [o.verdict, o.unavailable]));
    expect(byVerdict.cleared).toBe("ITSO has 1 open Must fix thread.");
    expect(byVerdict.finding).toBeNull();
  });

  it("holds an approval that would send the viewer's own Must fix draft", () => {
    const drafts = [comment({ is_draft: true, severity: "must_fix" })];
    const options = offered(["send_to_rdco", "request_revision"], flags(), drafts);
    expect(options.find((o) => o.verdict === "send_to_rdco")?.unavailable).toMatch(/Change it to Suggestion/);
    expect(options.find((o) => o.verdict === "request_revision")?.unavailable).toBeNull();
  });

  it("says a party that already asked for a revision can't ask again", () => {
    const option = offered(["withdraw_revision"]).find((o) => o.verdict === "request_revision");
    expect(option?.unavailable).toMatch(/already open/);
  });

  it("requires a reason for a revision, a finding and a rejection, and for any Decision while Must fix is open", () => {
    const need = (caps: Capability[], f?: VerdictFlags) =>
      offered(caps, f).filter((o) => o.reasonRequired).map((o) => o.verdict);
    expect(need(["request_revision", "office_review", "reject", "accept_publish"])).toEqual(["finding", "request_revision", "reject"]);
    const open = flags({ decision: { blocked: null, blocked_outcomes: {}, reason_required: true } as unknown as RecordDetail["decision"] });
    expect(need(["accept_publish", "keep_unlisted"], open)).toEqual(["publish", "keep_unlisted"]);
  });
});
