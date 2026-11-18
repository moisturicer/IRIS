/**
 * The reading-history store (IR-756, ADR-044 §Amendment 2026-11-01): one
 * session's history, read from the account, paused on the reader's word, and
 * fenced across account switches.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { libraryApi, type ReadingHistoryEntry } from "@/api/library";
import type { User } from "@/types/auth";
import type { RecordListItem } from "@/types/records";

import { useAuthStore } from "./auth.store";
import { useHistoryStore } from "./history.store";

vi.mock("@/api/library", () => ({
  libraryApi: {
    history: vi.fn(),
    visit: vi.fn(),
    clearHistory: vi.fn(),
    preferences: vi.fn(),
    updatePreferences: vi.fn(),
  },
}));

const record = { id: 5, title: "Rainwater Harvesting Survey" } as RecordListItem;
const visited: ReadingHistoryEntry = { record_id: record.id, available: true, viewed_at: "2026-11-01T08:00:00Z", record };

type Answer<F extends (...args: never[]) => unknown> = Awaited<ReturnType<F>>;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

function signIn(id: number) {
  useAuthStore.getState().login({ id, email: `r${id}@cit.edu`, role_name: "Student" } as unknown as User, "a");
}

const keeping = (keep_history: boolean) =>
  vi.mocked(libraryApi.preferences).mockResolvedValue({ data: { keep_history } } as Answer<typeof libraryApi.preferences>);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  signIn(1);
  vi.mocked(libraryApi.history).mockResolvedValue({ data: { results: [visited] } } as Answer<typeof libraryApi.history>);
  vi.mocked(libraryApi.visit).mockResolvedValue({} as Answer<typeof libraryApi.visit>);
  keeping(true);
});

describe("history store", () => {
  it("lists the account's history, unavailable entries by id only", async () => {
    vi.mocked(libraryApi.history).mockResolvedValue({
      data: { results: [visited, { record_id: 9, available: false }] },
    } as Answer<typeof libraryApi.history>);

    await useHistoryStore.getState().refresh();

    const { items, load, keepHistory } = useHistoryStore.getState();
    expect(load).toBe("ready");
    expect(keepHistory).toBe(true);
    expect(items).toEqual([
      { recordId: 5, available: true, viewedAt: "2026-11-01T08:00:00Z", record },
      { recordId: 9, available: false, viewedAt: null },
    ]);
  });

  it("records a visit on the account while history is kept", async () => {
    await useHistoryStore.getState().recordVisit(record.id);

    expect(libraryApi.visit).toHaveBeenCalledWith(record.id);
  });

  it("sends nothing while history is paused", async () => {
    keeping(false);

    await useHistoryStore.getState().recordVisit(record.id);
    await useHistoryStore.getState().recordVisit(record.id);

    expect(libraryApi.visit).not.toHaveBeenCalled();
  });

  it("asks again while paused, so resuming on another device reaches this one", async () => {
    keeping(false);
    await useHistoryStore.getState().recordVisit(record.id);

    keeping(true); // resumed on the laptop
    await useHistoryStore.getState().recordVisit(record.id);

    expect(libraryApi.visit).toHaveBeenCalledTimes(1);
  });

  it("asks for the setting once while history is kept", async () => {
    await useHistoryStore.getState().recordVisit(record.id);
    await useHistoryStore.getState().recordVisit(record.id);

    expect(libraryApi.preferences).toHaveBeenCalledTimes(1);
    expect(libraryApi.visit).toHaveBeenCalledTimes(2);
  });

  it("pausing stops the next visit, and resuming sends it again", async () => {
    // The server remembers the setting, as the real one does.
    vi.mocked(libraryApi.updatePreferences).mockImplementation(async (body) => {
      keeping(body.keep_history);
      return { data: body } as Answer<typeof libraryApi.updatePreferences>;
    });
    await useHistoryStore.getState().refresh();

    await useHistoryStore.getState().setKeepHistory(false);
    await useHistoryStore.getState().recordVisit(record.id);
    expect(libraryApi.visit).not.toHaveBeenCalled();
    expect(useHistoryStore.getState().items).toHaveLength(1);

    await useHistoryStore.getState().setKeepHistory(true);
    await useHistoryStore.getState().recordVisit(record.id);
    expect(libraryApi.visit).toHaveBeenCalledWith(record.id);
  });

  it("puts a refused pause back and says so", async () => {
    await useHistoryStore.getState().refresh();
    vi.mocked(libraryApi.updatePreferences).mockRejectedValue(new Error("offline"));

    await useHistoryStore.getState().setKeepHistory(false);

    expect(useHistoryStore.getState().keepHistory).toBe(true);
    expect(useHistoryStore.getState().failure).toMatch(/could not pause/i);
  });

  it("clears the account's history, and puts it back if the server refuses", async () => {
    await useHistoryStore.getState().refresh();
    vi.mocked(libraryApi.clearHistory).mockRejectedValueOnce(new Error("offline"));

    await useHistoryStore.getState().clear();
    expect(useHistoryStore.getState().items).toHaveLength(1);
    expect(useHistoryStore.getState().failure).toMatch(/could not clear/i);

    vi.mocked(libraryApi.clearHistory).mockResolvedValueOnce({} as Answer<typeof libraryApi.clearHistory>);
    await useHistoryStore.getState().clear();
    expect(libraryApi.clearHistory).toHaveBeenCalledTimes(2);
    expect(useHistoryStore.getState().items).toEqual([]);
  });

  it("never writes history to browser storage", async () => {
    const before = JSON.stringify({ ...localStorage });

    await useHistoryStore.getState().refresh();
    await useHistoryStore.getState().recordVisit(record.id);

    expect(JSON.stringify({ ...localStorage })).toBe(before);
  });

  it("starts the next account on this browser empty and drops the last one's late answer", async () => {
    const answer = deferred<Answer<typeof libraryApi.history>>();
    vi.mocked(libraryApi.history).mockReturnValue(answer.promise);

    const pending = useHistoryStore.getState().refresh();
    signIn(2);
    answer.resolve({ data: { results: [visited] } } as Answer<typeof libraryApi.history>);
    await pending;

    expect(useHistoryStore.getState().items).toEqual([]);
    expect(useHistoryStore.getState().keepHistory).toBeNull();
  });

  it("asks the next account's own setting rather than reusing the last one's pause", async () => {
    keeping(false);
    await useHistoryStore.getState().recordVisit(record.id);

    signIn(2);
    keeping(true);
    await useHistoryStore.getState().recordVisit(record.id);

    expect(libraryApi.visit).toHaveBeenCalledTimes(1);
  });
});
