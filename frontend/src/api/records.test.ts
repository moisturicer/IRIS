/**
 * `recordsApi`: method, path and payload for every call, and what a refusal
 * looks like (IR-916). The server decides who may do any of these (a 404 is a
 * record the caller cannot see, a 403 an act they may not do), so what this
 * file protects is the request being the one the server expects: a wrong verb
 * or a renamed body key is refused there as a 405 or a 400 and reads as a
 * broken button here.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "./records";
import { useAuthStore } from "@/store/auth.store";
import type { RouteRequest } from "@/types/records";
import { installApiStub } from "@/test/apiAdapter";

const stub = installApiStub();

type Row = [name: string, call: () => Promise<unknown>, method: string, url: string, body?: unknown, params?: unknown];

const none = undefined;

const routeBody: RouteRequest = { to: [{ party: "itso" }], reason: "Needs ITSO review" };

const rows: Row[] = [
  // Discover
  ["list", () => recordsApi.list({ page: 2, search: "ai" }), "get", "/records/", none, { page: 2, search: "ai" }],
  ["list with no params", () => recordsApi.list(), "get", "/records/", none, undefined],
  ["facets", () => recordsApi.facets(), "get", "/records/facets/"],
  ["interests", () => recordsApi.interests(), "get", "/records/interests/"],
  ["updateInterests", () => recordsApi.updateInterests({ classification_ids: [1], psced_ids: [2] }),
    "put", "/records/interests/", { classification_ids: [1], psced_ids: [2] }],
  ["resetInterests", () => recordsApi.resetInterests(), "delete", "/records/interests/"],
  ["notInterested", () => recordsApi.notInterested(5), "post", "/records/5/not-interested/"],
  ["undoNotInterested", () => recordsApi.undoNotInterested(5), "delete", "/records/5/not-interested/"],
  ["mine", () => recordsApi.mine({ status: "draft" }), "get", "/records/mine/", none, { status: "draft" }],

  // One record
  ["detail", () => recordsApi.detail(9), "get", "/records/9/"],
  ["continueAs", () => recordsApi.continueAs(9, 4), "post", "/records/9/continue-as/", { record_type: 4 }],
  ["tracker", () => recordsApi.tracker(9), "get", "/records/9/tracker/"],
  ["similar", () => recordsApi.similar(9), "get", "/records/9/similar/"],
  ["create", () => recordsApi.create({ title: "T" }), "post", "/records/", { title: "T" }],
  ["update", () => recordsApi.update(9, { title: "New" }), "patch", "/records/9/", { title: "New" }],
  ["delete", () => recordsApi.delete(9), "delete", "/records/9/"],
  ["submit", () => recordsApi.submit(9), "post", "/records/9/submit/"],
  ["incrementAccess", () => recordsApi.incrementAccess(9), "post", "/records/9/increment_access/"],
  ["updateTags", () => recordsApi.updateTags(9, { is_ip: true, ip_type: "patent" }),
    "patch", "/records/9/tags/", { is_ip: true, ip_type: "patent" }],
  ["duplicateMatches", () => recordsApi.duplicateMatches(9), "get", "/records/9/duplicate-matches/"],
  ["acknowledgeDuplicates", () => recordsApi.acknowledgeDuplicates(9, [3, 4]),
    "post", "/records/9/acknowledge-duplicates/", { candidate_ids: [3, 4] }],
  ["metadataSuggestions", () => recordsApi.metadataSuggestions(9), "get", "/records/9/metadata-suggestions/"],
  ["retryExtraction", () => recordsApi.retryExtraction(9, "rev-1"),
    "post", "/records/9/retry-extraction/", { manuscript_revision: "rev-1" }],
  ["retryExtraction with no revision", () => recordsApi.retryExtraction(9, null),
    "post", "/records/9/retry-extraction/", { manuscript_revision: null }],
  ["relatedResearch", () => recordsApi.relatedResearch(9), "get", "/records/9/related-research/"],

  // Embargo and IP release
  ["setEmbargo", () => recordsApi.setEmbargo(9, "2027-01-01"),
    "post", "/records/9/embargo-set/", { embargoed_until: "2027-01-01" }],
  ["releaseEmbargo", () => recordsApi.releaseEmbargo(9), "post", "/records/9/embargo-release/"],
  ["releaseIp", () => recordsApi.releaseIp(9), "post", "/records/9/ip-release/"],

  // Review discussion, revision and routing
  ["postReviewComment", () => recordsApi.postReviewComment(9, { body: "Hi", reply_to: 2 }),
    "post", "/records/9/review-comments/", { body: "Hi", reply_to: 2 }],
  ["editReviewComment", () => recordsApi.editReviewComment(9, 2, { body: "Edited" }),
    "patch", "/records/9/review-comments/2/", { body: "Edited" }],
  // Review threads (IR-874, IR-875)
  ["postReviewComment anchored", () => recordsApi.postReviewComment(9, {
    body: "Why?", severity: "must_fix", anchor: { version: 2, page: 3, quote: "94%" } }),
    "post", "/records/9/review-comments/", { body: "Why?", severity: "must_fix", anchor: { version: 2, page: 3, quote: "94%" } }],
  ["reviewComments", () => recordsApi.reviewComments(9), "get", "/records/9/review-comments/"],
  ["deleteReviewComment", () => recordsApi.deleteReviewComment(9, 2), "delete", "/records/9/review-comments/2/"],
  ["changeThreadSeverity", () => recordsApi.changeThreadSeverity(9, 2, "suggestion"),
    "post", "/records/9/review-comments/2/severity/", { severity: "suggestion" }],
  ["resolveThread", () => recordsApi.resolveThread(9, 2), "post", "/records/9/review-comments/2/resolve/", {}],
  ["reopenThread", () => recordsApi.reopenThread(9, 2), "post", "/records/9/review-comments/2/reopen/", {}],
  ["answerThread", () => recordsApi.answerThread(9, 2, { answer: "declined", note: "Out of scope" }),
    "post", "/records/9/review-comments/2/answer/", { answer: "declined", note: "Out of scope" }],
  ["finishReview", () => recordsApi.finishReview(9, { verdict: "comment_only", summary: "Fine" }),
    "post", "/records/9/finish-review/", { verdict: "comment_only", summary: "Fine" }],
  ["publicComments", () => recordsApi.publicComments(9), "get", "/records/9/comments/"],
  ["postPublicComment", () => recordsApi.postPublicComment(9, { body: "Hello", reply_to: 2 }),
    "post", "/records/9/comments/", { body: "Hello", reply_to: 2 }],
  ["editPublicComment", () => recordsApi.editPublicComment(9, 2, { body: "Edited" }),
    "patch", "/records/9/comments/2/", { body: "Edited" }],
  ["deletePublicComment", () => recordsApi.deletePublicComment(9, 2), "delete", "/records/9/comments/2/"],
  ["reportPublicComment", () => recordsApi.reportPublicComment(9, 2, { reason: "other", note: "Off-topic" }),
    "post", "/records/9/comments/2/reports/", { reason: "other", note: "Off-topic" }],
  ["routeOptions", () => recordsApi.routeOptions(9), "get", "/records/9/route-options/"],
  ["acceptAndRoute", () => recordsApi.acceptAndRoute(9, routeBody), "post", "/records/9/accept-and-route/", routeBody],
  ["route", () => recordsApi.route(9, routeBody), "post", "/records/9/route/", routeBody],
  ["officeReview clearing", () => recordsApi.officeReview(9, { outcome: "cleared", comment: "" }),
    "post", "/records/9/office-review/", { outcome: "cleared", comment: "" }],
  ["decide", () => recordsApi.decide(9, { outcome: "reject", comment: "No", token: "tok" }),
    "post", "/records/9/decide/", { outcome: "reject", comment: "No", token: "tok" }],
  ["requestRevision", () => recordsApi.requestRevision(9, { reason: "Fix section 2" }),
    "post", "/records/9/request-revision/", { reason: "Fix section 2" }],
  ["withdrawRevisionRequest", () => recordsApi.withdrawRevisionRequest(9, 6),
    "post", "/records/9/revision-requests/6/withdraw/"],
  ["submitNewVersion", () => recordsApi.submitNewVersion(9), "post", "/records/9/new-version/"],

  // Document requests
  ["documentRequests", () => recordsApi.documentRequests(9), "get", "/records/9/document-requests/"],
  ["createDocumentRequest",
    () => recordsApi.createDocumentRequest(9, { message: "Please", items: [{ slot: 2 }, { label: "Other" }], party: "itso" }),
    "post", "/records/9/document-requests/", { message: "Please", items: [{ slot: 2 }, { label: "Other" }], party: "itso" }],
  ["decideDocumentRequestItem", () => recordsApi.decideDocumentRequestItem(4, { action: "reject", reason: "Wrong file" }),
    "patch", "/document-request-items/4/", { action: "reject", reason: "Wrong file" }],
  ["withdrawDocumentRequest", () => recordsApi.withdrawDocumentRequest(4),
    "patch", "/document-requests/4/", { action: "withdraw" }],
  ["documentRequestSlots", () => recordsApi.documentRequestSlots(9), "get", "/records/9/document-requests/slots/"],

  // Reference data
  ["classifications", () => recordsApi.classifications(), "get", "/records/classifications/", none, undefined],
  ["classifications page", () => recordsApi.classifications({ page: 2 }),
    "get", "/records/classifications/", none, { page: 2 }],
  ["pscedList", () => recordsApi.pscedList(), "get", "/records/psced-classifications/"],
  ["recordTypes", () => recordsApi.recordTypes(), "get", "/records/record-types/"],
  ["downloadTemplate", () => recordsApi.downloadTemplate(), "get", "/records/download_template/"],

  // Download requests
  ["requestDownload", () => recordsApi.requestDownload(9, "for my thesis"),
    "post", "/records/download-requests/", { record: 9, note: "for my thesis" }],
  ["listDownloadRequests", () => recordsApi.listDownloadRequests({ status: "pending" }),
    "get", "/records/download-requests/", none, { status: "pending" }],
  ["approveDownloadRequest", () => recordsApi.approveDownloadRequest(3), "post", "/records/download-requests/3/approve/"],
  ["declineDownloadRequest", () => recordsApi.declineDownloadRequest(3, "no"),
    "post", "/records/download-requests/3/decline/", { note: "no" }],
  ["revokeDownloadRequest", () => recordsApi.revokeDownloadRequest(3, "changed"),
    "post", "/records/download-requests/3/revoke/", { note: "changed" }],
  ["cancelDownloadRequest", () => recordsApi.cancelDownloadRequest(3), "post", "/records/download-requests/3/cancel/"],
  ["myDownloadRequests", () => recordsApi.myDownloadRequests(), "get", "/records/download-requests/mine/"],

  // Delete requests
  ["listDeleteRequests", () => recordsApi.listDeleteRequests({ page: 1 }),
    "get", "/records/delete-requests/", none, { page: 1 }],
  ["approveDeleteRequest", () => recordsApi.approveDeleteRequest(8), "post", "/records/delete-requests/8/approve/"],
  ["declineDeleteRequest", () => recordsApi.declineDeleteRequest(8), "post", "/records/delete-requests/8/decline/"],
];

afterEach(() => useAuthStore.setState({ accessToken: null }));

describe("recordsApi: every call sends the request the server expects", () => {
  it.each(rows)("%s", async (_name, call, method, url, body, params) => {
    await call();

    const sent = stub.only();
    expect(sent.method).toBe(method);
    expect(sent.url).toBe(url);
    expect(sent.body).toEqual(body);
    expect(sent.params).toEqual(params);
  });

  it("answers with the server's body, typed by the call", async () => {
    stub.reply({ data: { id: 9, title: "A paper" } });

    const res = await recordsApi.detail(9);

    expect(res.data).toEqual({ id: 9, title: "A paper" });
  });
});

describe("recordsApi: calls with a shape of their own", () => {
  it("forYou sends the cursor only when there is one, and keeps the other params", async () => {
    await recordsApi.forYou(undefined, { page_size: 10 });
    expect(stub.calls[0]).toMatchObject({ url: "/records/for-you/", params: { page_size: 10 } });
    expect(stub.calls[0].params).not.toHaveProperty("cursor");

    await recordsApi.forYou("abc", { page_size: 10 });
    expect(stub.calls[1].params).toEqual({ page_size: 10, cursor: "abc" });
  });

  it("importExcel posts the file as multipart form data under the key `file`", async () => {
    const file = new File(["x"], "records.xlsx");

    await recordsApi.importExcel(file);

    const sent = stub.only();
    expect(sent).toMatchObject({ method: "post", url: "/records/import_excel/" });
    expect((sent.body as FormData).get("file")).toBe(file);
  });

  describe("uploadManuscript", () => {
    it("patches the record with the file under `abstract_file`", async () => {
      const file = new File(["pdf"], "paper.pdf", { type: "application/pdf" });

      await recordsApi.uploadManuscript(9, file);

      const sent = stub.only();
      expect(sent).toMatchObject({ method: "patch", url: "/records/9/" });
      expect(sent.body).toBeInstanceOf(FormData);
      expect((sent.body as FormData).get("abstract_file")).toBe(file);
    });

    it("reports progress as a percentage, using the file size when the browser gives no total", async () => {
      const file = new File(["0123456789"], "paper.pdf");
      const onProgress = vi.fn();

      await recordsApi.uploadManuscript(9, file, { onProgress });
      stub.only().progress({ loaded: 5, total: 20 });
      stub.only().progress({ loaded: 5 });

      expect(onProgress).toHaveBeenNthCalledWith(1, 25);
      expect(onProgress).toHaveBeenNthCalledWith(2, 50);
    });

    it("does not divide by zero for an empty file", async () => {
      const onProgress = vi.fn();

      await recordsApi.uploadManuscript(9, new File([], "empty.pdf"), { onProgress });
      stub.only().progress({ loaded: 0 });

      expect(onProgress).not.toHaveBeenCalled();
    });

    it("passes the abort signal on, so Publish can stop the upload", async () => {
      const controller = new AbortController();

      await recordsApi.uploadManuscript(9, new File(["x"], "p.pdf"), { signal: controller.signal });

      expect(stub.only().config.signal).toBe(controller.signal);
    });
  });

  describe("the manuscript's bytes", () => {
    it.each<[string, () => Promise<unknown>, string]>([
      ["manuscriptBlob", () => recordsApi.manuscriptBlob(9), "/records/9/manuscript/"],
      ["versionManuscriptBlob", () => recordsApi.versionManuscriptBlob(9, 2), "/records/9/versions/2/manuscript/"],
      ["downloadCopy", () => recordsApi.downloadCopy(9), "/records/9/download/"],
    ])("%s is read as a blob through the authenticated client", async (_name, call, url) => {
      await call();

      const sent = stub.only();
      expect(sent).toMatchObject({ method: "get", url, responseType: "blob" });
    });

    it("manuscriptBlob passes an abort signal on", async () => {
      const controller = new AbortController();

      await recordsApi.manuscriptBlob(9, { signal: controller.signal });

      expect(stub.only().config.signal).toBe(controller.signal);
    });

    it("downloadTemplate is read as a blob", async () => {
      await recordsApi.downloadTemplate();

      expect(stub.only().responseType).toBe("blob");
    });
  });

  it("carries a bearer token from the auth store on every call", async () => {
    useAuthStore.setState({ accessToken: "tok-1" });

    await recordsApi.facets();

    expect(stub.only().headers).toMatchObject({ Authorization: "Bearer tok-1" });
  });
});

describe("recordsApi: a refusal reaches the caller with its status and body", () => {
  it.each([
    ["404, a record the caller cannot see", 404, { detail: "Not found." }, () => recordsApi.detail(9)],
    ["403, an act they may not do", 403, { detail: "No." }, () => recordsApi.releaseEmbargo(9)],
    ["400, an act that is not possible now", 400, { detail: "Not now." }, () => recordsApi.submit(9)],
    ["409, a record that changed since the decision token", 409, { decision: { token: "fresh" } },
      () => recordsApi.decide(9, { outcome: "reject", comment: "No", token: "stale" })],
    ["403 with a code, a download without a grant", 403, { code: "download_grant_required" },
      () => recordsApi.downloadCopy(9)],
  ])("%s", async (_label, status, data, call) => {
    stub.reply({ status, data });

    await expect(call()).rejects.toMatchObject({ response: { status, data } });
  });
});
