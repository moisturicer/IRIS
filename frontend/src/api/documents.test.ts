/**
 * `documentsApi`: method, path, payload and upload mechanics (IR-916). Uploads
 * are multipart `FormData`, so the field names are the contract: the server
 * reads `record`, `slot`, `request_item` and `file`, and a renamed key is a 400
 * that looks like a failed upload.
 */
import { describe, expect, it, vi } from "vitest";

import { documentsApi } from "./documents";
import { installApiStub } from "@/test/apiAdapter";

const stub = installApiStub();
const pdf = () => new File(["%PDF"], "paper.pdf", { type: "application/pdf" });

function fields(body: unknown): Record<string, FormDataEntryValue> {
  expect(body).toBeInstanceOf(FormData);
  return Object.fromEntries((body as FormData).entries());
}

describe("reads", () => {
  type Row = [name: string, call: () => Promise<unknown>, url: string, params?: unknown, responseType?: string];

  const rows: Row[] = [
    ["slots", () => documentsApi.slots(4), "/documents/slots/", { record_type: 4 }],
    ["slots for every type", () => documentsApi.slots(), "/documents/slots/", {}],
    ["slotsForRecord", () => documentsApi.slotsForRecord(9), "/documents/records/9/slots/"],
    ["uploads", () => documentsApi.uploads(9), "/documents/uploads/", { record: 9 }],
    ["files", () => documentsApi.files(9), "/documents/files/", { record: 9 }],
    ["downloadUpload", () => documentsApi.downloadUpload(3), "/documents/uploads/3/download/", undefined, "blob"],
    ["viewUpload", () => documentsApi.viewUpload(3), "/documents/uploads/3/download/?inline=true", undefined, "blob"],
    ["downloadFile", () => documentsApi.downloadFile(3), "/documents/files/3/download/", undefined, "blob"],
    ["viewFile", () => documentsApi.viewFile(3), "/documents/files/3/download/?inline=true", undefined, "blob"],
    ["downloadAll", () => documentsApi.downloadAll(9), "/documents/files/download-all/", { record: 9 }, "blob"],
  ];

  it.each(rows)("%s", async (_name, call, url, params, responseType) => {
    await call();

    const sent = stub.only();
    expect(sent.method).toBe("get");
    expect(sent.url).toBe(url);
    expect(sent.params).toEqual(params);
    expect(sent.responseType).toBe(responseType);
    expect(sent.body).toBeUndefined();
  });

  it("slots answers with the paginated body", async () => {
    stub.reply({ data: { count: 1, results: [{ id: 1 }] } });

    expect((await documentsApi.slots(4)).data).toEqual({ count: 1, results: [{ id: 1 }] });
  });
});

describe("deletes", () => {
  it("deleteUpload removes one version", async () => {
    await documentsApi.deleteUpload(3);

    expect(stub.only()).toMatchObject({ method: "delete", url: "/documents/uploads/3/" });
  });

  it("deleteFile removes one attachment", async () => {
    await documentsApi.deleteFile(8);

    expect(stub.only()).toMatchObject({ method: "delete", url: "/documents/files/8/" });
  });
});

describe("uploads", () => {
  it("upload posts record, slot and file to /documents/submit/", async () => {
    const file = pdf();

    await documentsApi.upload(9, 4, file);

    const sent = stub.only();
    expect(sent).toMatchObject({ method: "post", url: "/documents/submit/" });
    expect(fields(sent.body)).toEqual({ record: "9", slot: "4", file });
  });

  it("uploadForRequestItem sends request_item instead of a slot, and the server takes the slot from the item", async () => {
    const file = pdf();

    await documentsApi.uploadForRequestItem(9, 6, file);

    const sent = stub.only();
    expect(sent).toMatchObject({ method: "post", url: "/documents/submit/" });
    expect(fields(sent.body)).toEqual({ record: "9", request_item: "6", file });
    expect(fields(sent.body)).not.toHaveProperty("slot");
  });

  it("uploadFile, the legacy alias, sends what upload sends", async () => {
    const file = pdf();

    await documentsApi.uploadFile(9, 4, file);

    expect(stub.only()).toMatchObject({ method: "post", url: "/documents/submit/" });
    expect(fields(stub.only().body)).toEqual({ record: "9", slot: "4", file });
  });

  it("uploadRecordFile posts record and file to /documents/files/upload/", async () => {
    const file = pdf();

    await documentsApi.uploadRecordFile(9, file);

    const sent = stub.only();
    expect(sent).toMatchObject({ method: "post", url: "/documents/files/upload/" });
    expect(fields(sent.body)).toEqual({ record: "9", file });
  });

  it.each<[string, (file: File, onProgress: (p: number) => void) => Promise<unknown>]>([
    ["upload", (f, p) => documentsApi.upload(9, 4, f, { onProgress: p })],
    ["uploadForRequestItem", (f, p) => documentsApi.uploadForRequestItem(9, 6, f, { onProgress: p })],
    ["uploadRecordFile", (f, p) => documentsApi.uploadRecordFile(9, f, { onProgress: p })],
  ])("%s reports progress as a percentage", async (_name, call) => {
    const onProgress = vi.fn();

    await call(new File(["0123456789"], "paper.pdf"), onProgress);
    const report = stub.only().config.onUploadProgress as (e: object) => void;
    report({ loaded: 5, total: 20 });
    report({ loaded: 10 });

    expect(onProgress).toHaveBeenNthCalledWith(1, 25);
    // With no total from the browser the file's own size is the denominator.
    expect(onProgress).toHaveBeenNthCalledWith(2, 100);
  });

  it("does not report progress for an empty file, rather than dividing by zero", async () => {
    const onProgress = vi.fn();

    await documentsApi.upload(9, 4, new File([], "empty.pdf"), { onProgress });
    (stub.only().config.onUploadProgress as (e: object) => void)({ loaded: 0 });

    expect(onProgress).not.toHaveBeenCalled();
  });

  it("does not throw on progress when no one is listening", async () => {
    await documentsApi.upload(9, 4, pdf());

    expect(() => (stub.only().config.onUploadProgress as (e: object) => void)({ loaded: 1, total: 2 }))
      .not.toThrow();
  });

  it("sets a multipart content type so the browser adds the boundary", async () => {
    await documentsApi.upload(9, 4, pdf());

    expect(String(stub.only().headers["Content-Type"])).toContain("multipart/form-data");
  });
});

describe("a refusal reaches the caller with its status and body", () => {
  it.each([
    ["404, a record the caller does not own", 404, () => documentsApi.upload(9, 4, pdf())],
    ["403, a download they may not make", 403, () => documentsApi.downloadUpload(3)],
    ["400, a file the server will not take", 400, () => documentsApi.uploadRecordFile(9, pdf())],
    ["403, deleting a first version as an owner", 403, () => documentsApi.deleteUpload(3)],
  ])("%s", async (_label, status, call) => {
    stub.reply({ status, data: { detail: "refused" } });

    await expect(call()).rejects.toMatchObject({ response: { status, data: { detail: "refused" } } });
  });
});
