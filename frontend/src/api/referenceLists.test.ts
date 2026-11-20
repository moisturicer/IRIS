/**
 * Reference lists are fetched once per session (IR-1249).
 *
 * Classifications, PSCED codes, record types and colleges change only when an
 * administrator edits them, yet Discover asked for them on every visit, and
 * for classifications twice. Each is now one request per session, shared by
 * every caller and dropped on sign-out. Setup cannot change any of them: the
 * public record-type list is id and name, and Setup edits descriptions,
 * templates and requirements through its own endpoint.
 */
import { afterEach, describe, expect, it } from "vitest";

import { accountsApi } from "./accounts";
import { forgetReferenceLists } from "./referenceLists";
import { recordsApi } from "./records";
import { useAuthStore } from "@/store/auth.store";
import { installApiStub } from "@/test/apiAdapter";

const stub = installApiStub();
const gets = (url: string) => stub.calls.filter((c) => c.method === "get" && c.url === url).length;

afterEach(() => forgetReferenceLists());

describe("reference lists (IR-1249)", () => {
  it.each([
    ["classifications", () => recordsApi.classifications(), "/records/classifications/"],
    ["PSCED codes", () => recordsApi.pscedList(), "/records/psced-classifications/"],
    ["record types", () => recordsApi.recordTypes(), "/records/record-types/"],
    ["colleges", () => accountsApi.colleges(), "/colleges/"],
  ])("asks for %s once, however many screens want them", async (_name, call, url) => {
    stub.reply({ data: { count: 1, next: null, previous: null, results: [{ id: 1, name: "One" }] } });

    const [a, b] = await Promise.all([call(), call()]);
    const c = await call();

    expect(gets(url)).toBe(1);
    expect(a.data).toEqual({ count: 1, next: null, previous: null, results: [{ id: 1, name: "One" }] });
    expect(c.data).toEqual(a.data);
    expect(b.data).toEqual(a.data);
  });

  it("gives each caller its own copy, so one screen's sort cannot reorder another's", async () => {
    stub.reply({ data: { count: 2, next: null, previous: null, results: [{ id: 2, name: "B" }, { id: 1, name: "A" }] } });

    const first = await recordsApi.classifications();
    first.data.results.reverse();
    const second = await recordsApi.classifications();

    expect(second.data.results.map((r) => r.id)).toEqual([2, 1]);
  });

  it("does not keep a failure: the next caller asks again", async () => {
    stub.reply({ status: 503 });
    await expect(recordsApi.classifications()).rejects.toThrow();

    stub.reply({ data: { count: 0, next: null, previous: null, results: [] } });
    await recordsApi.classifications();

    expect(gets("/records/classifications/")).toBe(2);
  });

  it("asks a paged request every time: only the whole list is kept", async () => {
    await recordsApi.classifications({ page: 2 });
    await recordsApi.classifications({ page: 2 });

    expect(gets("/records/classifications/")).toBe(2);
  });

  it("forgets every list on sign-out, so the next account asks afresh", async () => {
    await recordsApi.classifications();
    await accountsApi.colleges();

    useAuthStore.getState().logout();
    await recordsApi.classifications();
    await accountsApi.colleges();

    expect(gets("/records/classifications/")).toBe(2);
    expect(gets("/colleges/")).toBe(2);
  });
});
