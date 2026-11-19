/**
 * Saved Calls (IR-766, ADR-050 decision 13): the account's saves, with the
 * paper library's behaviour (IR-566): one session's, cleared on every session
 * change, fenced against a late answer, optimistic with a rollback that says so.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { opportunitiesApi } from "@/api/opportunities";
import { RequestTimeoutError } from "@/api/requestPolicy";
import type { User } from "@/types/auth";
import type { Opportunity, SavedCallEntry } from "@/types/opportunities";

import { useAuthStore } from "./auth.store";
import { savedInOrder, useSavedCallsStore } from "./savedCalls.store";
import { useUIStore } from "./ui.store";

vi.mock("@/api/opportunities", () => ({
  opportunitiesApi: { saved: vi.fn(), save: vi.fn(), unsave: vi.fn() },
}));

const call = (id: number) => ({ id, title: `Call ${id}` }) as Opportunity;
const entry = (id: number, saved_at = "2026-11-10T08:00:00Z"): SavedCallEntry =>
  ({ call_id: id, available: true, saved_at, call: call(id) });

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function signIn(id: number) {
  useAuthStore.getState().login({ id, email: `r${id}@cit.edu`, role_name: "Student" } as unknown as User, "a");
}

const isSaved = (id: number) => useSavedCallsStore.getState().items[id] !== undefined;
const ordered = () => {
  const { items, order } = useSavedCallsStore.getState();
  return savedInOrder(items, order).map((i) => i.callId);
};

async function loaded(entries: SavedCallEntry[]) {
  vi.mocked(opportunitiesApi.saved).mockResolvedValue({ data: { results: entries } } as never);
  await useSavedCallsStore.getState().ensureLoaded(true);
}

beforeEach(() => {
  vi.clearAllMocks();
  signIn(1);
});

afterEach(() => useUIStore.setState({ toasts: [] }));

describe("saved Calls", () => {
  it("loads the account's saves, an unavailable one included, newest first as the server orders them", async () => {
    await loaded([entry(2, "2026-11-12T08:00:00Z"), { call_id: 9, available: false }, entry(3, "2026-11-11T08:00:00Z")]);
    expect(useSavedCallsStore.getState().load).toBe("ready");
    expect(isSaved(2)).toBe(true);
    expect(isSaved(9)).toBe(true);
    // Newest first, as ADR-050 decision 13 says: an unavailable Call keeps its place.
    expect(ordered()).toEqual([2, 9, 3]);
  });

  it("puts a new save first", async () => {
    await loaded([entry(2)]);
    vi.mocked(opportunitiesApi.save).mockResolvedValue({ data: entry(4, "2026-11-16T08:00:00Z") } as never);
    await useSavedCallsStore.getState().save(call(4));
    expect(ordered()).toEqual([4, 2]);
  });

  it("says a read that timed out was interrupted, not refused", async () => {
    vi.mocked(opportunitiesApi.saved).mockRejectedValueOnce(new RequestTimeoutError(30_000, "get", "/opportunities/saved/"));
    await useSavedCallsStore.getState().ensureLoaded(true);
    expect(useSavedCallsStore.getState()).toMatchObject({ load: "error", interrupted: true });

    vi.mocked(opportunitiesApi.saved).mockRejectedValueOnce({ response: { status: 500 } });
    await useSavedCallsStore.getState().ensureLoaded(true);
    expect(useSavedCallsStore.getState()).toMatchObject({ load: "error", interrupted: false });
  });

  it("ignores a toast's Try again once the session changed", async () => {
    await loaded([]);
    vi.mocked(opportunitiesApi.save).mockRejectedValueOnce(new Error("Network Error"));
    await useSavedCallsStore.getState().save(call(4));
    const retry = useUIStore.getState().toasts[0].action!.onClick;

    useAuthStore.getState().logout();
    signIn(2);
    retry();
    expect(opportunitiesApi.save).toHaveBeenCalledTimes(1);
    expect(isSaved(4)).toBe(false);
  });

  it("shows a save at once, and keeps the server's copy when it answers", async () => {
    await loaded([]);
    const answer = deferred<{ data: SavedCallEntry }>();
    vi.mocked(opportunitiesApi.save).mockReturnValue(answer.promise as never);

    const saving = useSavedCallsStore.getState().save(call(4));
    expect(isSaved(4)).toBe(true);
    answer.resolve({ data: entry(4, "2026-11-16T08:00:00Z") });
    expect(await saving).toBe(true);
    expect(useSavedCallsStore.getState().items[4]).toMatchObject({ available: true, savedAt: "2026-11-16T08:00:00Z" });
  });

  it("rolls a failed save back and says so in a toast with Try again", async () => {
    await loaded([]);
    vi.mocked(opportunitiesApi.save).mockRejectedValueOnce(new Error("Network Error"));

    expect(await useSavedCallsStore.getState().save(call(4))).toBe(false);
    expect(isSaved(4)).toBe(false);
    const [toast] = useUIStore.getState().toasts;
    expect(toast).toMatchObject({ type: "error", message: "Could not save Call 4. Nothing was changed." });
    expect(toast.action?.label).toBe("Try again");
  });

  it("rolls a failed removal back, still saved, and says so", async () => {
    await loaded([entry(5)]);
    vi.mocked(opportunitiesApi.unsave).mockRejectedValueOnce(new Error("Network Error"));

    expect(await useSavedCallsStore.getState().unsave(call(5))).toBe(false);
    expect(isSaved(5)).toBe(true);
    expect(useUIStore.getState().toasts[0]).toMatchObject({ type: "error", message: "Could not remove Call 5. It is still saved." });
  });

  it("lets only the newest write to a Call decide", async () => {
    await loaded([]);
    const first = deferred<{ data: SavedCallEntry }>();
    vi.mocked(opportunitiesApi.save).mockReturnValueOnce(first.promise as never);
    vi.mocked(opportunitiesApi.unsave).mockResolvedValueOnce({} as never);

    const saving = useSavedCallsStore.getState().save(call(6));
    await useSavedCallsStore.getState().unsave(call(6));
    first.resolve({ data: entry(6) });
    await saving;
    expect(isSaved(6)).toBe(false);
  });

  it("starts empty for the next account, and drops an answer from the last one", async () => {
    await loaded([entry(7)]);
    const late = deferred<{ data: { results: SavedCallEntry[] } }>();
    vi.mocked(opportunitiesApi.saved).mockReturnValueOnce(late.promise as never);
    const loading = useSavedCallsStore.getState().ensureLoaded(true);

    useAuthStore.getState().logout();
    signIn(2);
    expect(useSavedCallsStore.getState().items).toEqual({});
    expect(useSavedCallsStore.getState().load).toBe("idle");

    late.resolve({ data: { results: [entry(8)] } });
    await loading;
    expect(useSavedCallsStore.getState().items).toEqual({});
  });

  it("never touches the browser's storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    vi.mocked(opportunitiesApi.save).mockResolvedValue({ data: entry(4) } as never);
    await loaded([]);
    await useSavedCallsStore.getState().save(call(4));
    expect(setItem.mock.calls.filter(([key]) => String(key).includes("opportunit"))).toEqual([]);
    setItem.mockRestore();
  });
});
