/**
 * The reader's saved custom feeds (IR-577): one session's list, written only
 * with the server's say-so, and fenced across account switches so the next
 * person on a shared PC never sees the last one's feeds.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { libraryApi, type SavedFeed } from "@/api/library";
import type { User } from "@/types/auth";

import { useAuthStore } from "./auth.store";
import { useFeedsStore } from "./feeds.store";

vi.mock("@/api/library", () => ({
  libraryApi: { feeds: vi.fn(), createFeed: vi.fn(), updateFeed: vi.fn(), deleteFeed: vi.fn() },
}));

const feed = (id: number, name: string, extra: Partial<SavedFeed> = {}): SavedFeed => ({
  id, name, query: { q: "flood" }, stale: {},
  created_at: "2026-11-07T00:00:00Z", updated_at: "2026-11-07T00:00:00Z", ...extra,
});

const answer = <T,>(data: T) => ({ data }) as never;
const refused = (data: unknown, status = 400) => Object.assign(new Error("refused"), { response: { status, data } });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

function signIn(id: number) {
  useAuthStore.getState().login({ id, email: `r${id}@cit.edu`, role_name: "Student" } as unknown as User, "a", "r");
}

beforeEach(() => {
  vi.clearAllMocks();
  signIn(1);
  useFeedsStore.setState({ load: "idle", feeds: [], limit: 10, interrupted: false });
});

describe("feeds store", () => {
  it("loads the reader's feeds and the account limit", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ results: [feed(1, "Coastal")], limit: 10 }));

    await useFeedsStore.getState().ensureLoaded();

    expect(useFeedsStore.getState().load).toBe("ready");
    expect(useFeedsStore.getState().feeds.map((f) => f.name)).toEqual(["Coastal"]);
    expect(useFeedsStore.getState().limit).toBe(10);
  });

  it("reads once, however many surfaces ask", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ results: [], limit: 10 }));

    await Promise.all([useFeedsStore.getState().ensureLoaded(), useFeedsStore.getState().ensureLoaded()]);

    expect(libraryApi.feeds).toHaveBeenCalledTimes(1);
  });

  it("marks a failed read as an error, and as interrupted only when it timed out", async () => {
    vi.mocked(libraryApi.feeds).mockRejectedValue(new Error("offline"));

    await useFeedsStore.getState().ensureLoaded();

    expect(useFeedsStore.getState().load).toBe("error");
    expect(useFeedsStore.getState().interrupted).toBe(false);
  });

  // CODING_STANDARDS F1: a response that is not the shape the screens read is
  // the failed-read state, never a crash in Discover.
  it("treats a list that is not a list as a failed read", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ count: 0, results: { not: "a list" }, limit: 10 }));

    await useFeedsStore.getState().ensureLoaded();

    expect(useFeedsStore.getState().load).toBe("error");
    expect(useFeedsStore.getState().feeds).toEqual([]);
  });

  it("treats a feed with no query or stale map as a failed read, keeping none of the list", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({
      results: [feed(1, "Fine"), { id: 2, name: "Broken" }], limit: 10,
    }));

    await useFeedsStore.getState().ensureLoaded();

    expect(useFeedsStore.getState().load).toBe("error");
    expect(useFeedsStore.getState().feeds).toEqual([]);
  });

  it("accepts the router tests' generic answer as a list with no feeds", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ count: 0, results: [] }));

    await useFeedsStore.getState().ensureLoaded();

    expect(useFeedsStore.getState().load).toBe("ready");
    expect(useFeedsStore.getState().limit).toBe(10);
  });

  it("does not add a saved feed whose answer is not a feed", async () => {
    vi.mocked(libraryApi.createFeed).mockResolvedValue(answer({ id: 7 }));

    const result = await useFeedsStore.getState().create("Coastal", { q: "flood" });

    expect(result.ok).toBe(false);
    expect(useFeedsStore.getState().feeds).toEqual([]);
  });

  it("adds a saved feed only once the server has accepted it", async () => {
    const pending = deferred<ReturnType<typeof answer>>();
    vi.mocked(libraryApi.createFeed).mockReturnValue(pending.promise as never);

    const saving = useFeedsStore.getState().create("Coastal", { q: "flood" });
    expect(useFeedsStore.getState().feeds).toEqual([]);
    pending.resolve(answer(feed(7, "Coastal")));

    await expect(saving).resolves.toEqual({ ok: true, feed: feed(7, "Coastal") });
    expect(useFeedsStore.getState().feeds.map((f) => f.id)).toEqual([7]);
  });

  it("hands back the server's reason for a refusal and changes nothing", async () => {
    vi.mocked(libraryApi.createFeed).mockRejectedValue(
      refused({ code: "feed_limit", detail: "You have 10 saved feeds. Delete one to save another." }),
    );

    const result = await useFeedsStore.getState().create("Eleventh", { q: "flood" });

    expect(result).toEqual({ ok: false, message: "You have 10 saved feeds. Delete one to save another." });
    expect(useFeedsStore.getState().feeds).toEqual([]);
  });

  it("reads a field error out of the answer, naming the field's own message", async () => {
    vi.mocked(libraryApi.createFeed).mockRejectedValueOnce(refused({ name: ["You already have a saved feed with that name."] }));
    vi.mocked(libraryApi.createFeed).mockRejectedValueOnce(refused({ query: ["Add at least one Area, keyword, college, type, year or IP filter."] }));

    const duplicate = await useFeedsStore.getState().create("Coastal", { q: "flood" });
    const empty = await useFeedsStore.getState().create("Empty", { sort: "viewed" });

    expect(duplicate).toEqual({ ok: false, message: "You already have a saved feed with that name." });
    expect(empty).toEqual({ ok: false, message: "Add at least one Area, keyword, college, type, year or IP filter." });
  });

  it("says it could not save when the answer carries no reason", async () => {
    vi.mocked(libraryApi.createFeed).mockRejectedValue(new Error("offline"));

    const result = await useFeedsStore.getState().create("Coastal", { q: "flood" });

    expect(result).toEqual({ ok: false, message: expect.stringMatching(/could not save/i) });
  });

  it("replaces a feed with the server's answer after a rename or a correction", async () => {
    useFeedsStore.setState({ feeds: [feed(1, "Old", { stale: { classification: [7] } })], load: "ready" });
    vi.mocked(libraryApi.updateFeed).mockResolvedValue(answer(feed(1, "New", { query: { classification: "4" } })));

    const result = await useFeedsStore.getState().update(1, { name: "New", query: { classification: "4" } });

    expect(result.ok).toBe(true);
    expect(useFeedsStore.getState().feeds).toEqual([feed(1, "New", { query: { classification: "4" } })]);
    expect(libraryApi.updateFeed).toHaveBeenCalledWith(1, { name: "New", query: { classification: "4" } });
  });

  it("removes a feed only when the server has", async () => {
    useFeedsStore.setState({ feeds: [feed(1, "A"), feed(2, "B")], load: "ready" });
    vi.mocked(libraryApi.deleteFeed).mockRejectedValueOnce(new Error("offline"));

    expect((await useFeedsStore.getState().remove(1)).ok).toBe(false);
    expect(useFeedsStore.getState().feeds.map((f) => f.id)).toEqual([1, 2]);

    vi.mocked(libraryApi.deleteFeed).mockResolvedValueOnce(answer(undefined));
    expect((await useFeedsStore.getState().remove(1)).ok).toBe(true);
    expect(useFeedsStore.getState().feeds.map((f) => f.id)).toEqual([2]);
  });

  it("drops a read that lands after the account changed", async () => {
    const pending = deferred<ReturnType<typeof answer>>();
    vi.mocked(libraryApi.feeds).mockReturnValue(pending.promise as never);

    const loading = useFeedsStore.getState().ensureLoaded();
    signIn(2);
    pending.resolve(answer({ results: [feed(1, "First reader's")], limit: 10 }));
    await loading;

    expect(useFeedsStore.getState().feeds).toEqual([]);
  });

  it("drops a save that lands after the account changed", async () => {
    const pending = deferred<ReturnType<typeof answer>>();
    vi.mocked(libraryApi.createFeed).mockReturnValue(pending.promise as never);

    const saving = useFeedsStore.getState().create("Coastal", { q: "flood" });
    signIn(2);
    pending.resolve(answer(feed(7, "Coastal")));
    await saving;

    expect(useFeedsStore.getState().feeds).toEqual([]);
  });

  it("is emptied the moment another account signs in", async () => {
    useFeedsStore.setState({ feeds: [feed(1, "Mine")], load: "ready" });

    signIn(2);
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ results: [], limit: 10 }));
    await useFeedsStore.getState().ensureLoaded();

    expect(useFeedsStore.getState().feeds).toEqual([]);
  });
});
