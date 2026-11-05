/**
 * `seatsApi` and `reviewsApi`: method, path and payload, and the filters that
 * are left off when empty (IR-916). The server re-checks every act, so a 404 is
 * a record the caller cannot see, a 403 an act they may not do and a 400 one
 * that is not possible now; each must reach the screen with its status.
 */
import { describe, expect, it } from "vitest";

import { reviewsApi, seatsApi } from "./reviews";
import { installApiStub } from "@/test/apiAdapter";

const stub = installApiStub();

type Row = [name: string, call: () => Promise<unknown>, method: string, url: string, body?: unknown];

const rows: Row[] = [
  ["claim", () => seatsApi.claim(11), "post", "/assignments/11/claim/"],
  ["assignOptions", () => seatsApi.assignOptions(11), "get", "/assignments/11/assign/"],
  ["assign", () => seatsApi.assign(11, 5), "post", "/assignments/11/assign/", { reviewer: 5 }],
  ["addReviewerOptions", () => seatsApi.addReviewerOptions(11), "get", "/assignments/11/add-reviewer/"],
  ["addReviewer", () => seatsApi.addReviewer(11, 5), "post", "/assignments/11/add-reviewer/", { reviewer: 5 }],
  ["open", () => seatsApi.open(21), "post", "/seats/21/open/"],
  ["reassign", () => seatsApi.reassign(21, 5, "on leave"),
    "post", "/seats/21/reassign/", { reviewer: 5, reason: "on leave" }],
  ["extend", () => seatsApi.extend(11, "2026-12-01T23:59:00+08:00", "needs more time"),
    "post", "/assignments/11/extend/", { due_at: "2026-12-01T23:59:00+08:00", reason: "needs more time" }],
  ["withdraw", () => seatsApi.withdraw(21), "post", "/seats/21/withdraw/"],
];

describe("seatsApi", () => {
  it.each(rows)("%s", async (_name, call, method, url, body) => {
    await call();

    expect(stub.only()).toMatchObject({ method, url });
    expect(stub.only().body).toEqual(body);
  });

  it.each([
    ["404, a record the caller cannot see", 404],
    ["403, an act they may not do", 403],
    ["400, an act that is not possible now", 400],
  ])("%s reaches the caller with its body", async (_label, status) => {
    stub.reply({ status, data: { detail: "refused" } });

    await expect(seatsApi.claim(11)).rejects.toMatchObject({
      response: { status, data: { detail: "refused" } },
    });
  });
});

describe("reviewsApi.mine", () => {
  it("sends the tab and nothing else when no filter is set", async () => {
    await reviewsApi.mine({ tab: "to_review" });

    expect(stub.only()).toMatchObject({ method: "get", url: "/reviews/mine/", params: { tab: "to_review" } });
    expect(Object.keys(stub.only().params as object)).toEqual(["tab"]);
  });

  it("sends every filter that is set, with overdue as the string 1", async () => {
    await reviewsApi.mine({
      tab: "done", outcome: "cleared", office: "ITSO", cursor: "c1", sort: "due", overdue: true,
    });

    expect(stub.only().params).toEqual({
      tab: "done", outcome: "cleared", office: "ITSO", cursor: "c1", sort: "due", overdue: "1",
    });
  });

  it("leaves a filter off when it is empty, null or false", async () => {
    await reviewsApi.mine({
      tab: "to_review", outcome: null, office: null, cursor: undefined, sort: null, overdue: false,
    });

    expect(stub.only().params).toEqual({ tab: "to_review" });
  });

  it("answers with the page the server sent", async () => {
    stub.reply({ data: { counts: { active: 1 }, results: [] } });

    expect((await reviewsApi.mine({ tab: "to_review" })).data).toEqual({ counts: { active: 1 }, results: [] });
  });

  it("rejects with the status when a reviewer is refused", async () => {
    stub.reply({ status: 403, data: { detail: "No." } });

    await expect(reviewsApi.mine({ tab: "to_review" })).rejects.toMatchObject({ response: { status: 403 } });
  });
});

describe("reviewsApi.analytics", () => {
  it("sends no filter when none is set, so the server applies none", async () => {
    await reviewsApi.analytics({ office: "", from: "", to: "" });

    expect(stub.only()).toMatchObject({ method: "get", url: "/reviews/analytics/", params: {} });
  });

  it("sends the filters that are set under the names the server reads", async () => {
    await reviewsApi.analytics({ office: "KTTO", from: "2026-01-01", to: "2026-06-30" });

    expect(stub.only().params).toEqual({ office: "KTTO", from: "2026-01-01", to: "2026-06-30" });
  });

  it("sends only a lower bound when that is all there is", async () => {
    await reviewsApi.analytics({ office: "", from: "2026-01-01", to: "" });

    expect(stub.only().params).toEqual({ from: "2026-01-01" });
  });

  it("rejects with the status when the caller may not see analytics", async () => {
    stub.reply({ status: 403 });

    await expect(reviewsApi.analytics({ office: "", from: "", to: "" })).rejects.toMatchObject({ response: { status: 403 } });
  });
});

describe("reviewsApi.office", () => {
  it("sends the office when one is chosen", async () => {
    await reviewsApi.office("ITSO");

    expect(stub.only()).toMatchObject({ method: "get", url: "/reviews/office/", params: { office: "ITSO" } });
  });

  it("sends no office for a coordinator's own console", async () => {
    await reviewsApi.office(null);

    expect(stub.only().params).toEqual({});
  });

  it("is refused with a 403 for anyone but a coordinator", async () => {
    stub.reply({ status: 403, data: { detail: "Coordinators only." } });

    await expect(reviewsApi.office(null)).rejects.toMatchObject({
      response: { status: 403, data: { detail: "Coordinators only." } },
    });
  });
});
