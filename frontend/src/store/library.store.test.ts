/**
 * The account library store (IR-566, ADR-044 §6): one session's saves,
 * optimistic with a visible rollback, and fenced across account switches.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { libraryApi, type SavedRecordEntry } from "@/api/library";
import type { User } from "@/types/auth";
import type { RecordListItem } from "@/types/records";

import { useAuthStore } from "./auth.store";
import { useLibraryStore } from "./library.store";

vi.mock("@/api/library", () => ({
  libraryApi: { saves: vi.fn(), save: vi.fn(), unsave: vi.fn() },
}));

const record = { id: 5, title: "Rainwater Harvesting Survey" } as RecordListItem;

const entry = (reading_status: "reading" | null = null): SavedRecordEntry => ({
  record_id: record.id, available: true, reading_status,
  saved_at: "2026-11-01T08:00:00Z", updated_at: "2026-11-01T08:00:00Z", record,
});

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
  localStorage.clear();
  sessionStorage.clear();
  signIn(1);
});

describe("library store", () => {
  it("shows a save at once and keeps the server's answer", async () => {
    vi.mocked(libraryApi.save).mockResolvedValue({ data: entry("reading") } as Awaited<ReturnType<typeof libraryApi.save>>);

    const pending = useLibraryStore.getState().save(record.id, "reading", record);
    expect(useLibraryStore.getState().items[record.id]?.readingStatus).toBe("reading");

    await expect(pending).resolves.toBe(true);
    expect(useLibraryStore.getState().items[record.id]?.savedAt).toBe("2026-11-01T08:00:00Z");
  });

  it("rolls a refused save back and says so", async () => {
    vi.mocked(libraryApi.save).mockRejectedValue(new Error("offline"));

    await useLibraryStore.getState().save(record.id, "reading", record);

    expect(useLibraryStore.getState().items[record.id]).toBeUndefined();
    expect(useLibraryStore.getState().failure).toEqual({ recordId: record.id, message: expect.stringMatching(/could not save/i) });
  });

  it("never writes a save to browser storage", async () => {
    vi.mocked(libraryApi.save).mockResolvedValue({ data: entry() } as Awaited<ReturnType<typeof libraryApi.save>>);
    const before = JSON.stringify({ ...localStorage });

    await useLibraryStore.getState().save(record.id, undefined, record);

    expect(JSON.stringify({ ...localStorage })).toBe(before);
  });

  it("drops a write that answers after the account changed", async () => {
    const answer = deferred<Awaited<ReturnType<typeof libraryApi.save>>>();
    vi.mocked(libraryApi.save).mockReturnValue(answer.promise);

    const pending = useLibraryStore.getState().save(record.id, "reading", record);
    signIn(2);
    answer.resolve({ data: entry("reading") } as Awaited<ReturnType<typeof libraryApi.save>>);
    await pending;

    expect(useLibraryStore.getState().items).toEqual({});
  });

  it("drops a list that answers after sign-out", async () => {
    const answer = deferred<Awaited<ReturnType<typeof libraryApi.saves>>>();
    vi.mocked(libraryApi.saves).mockReturnValue(answer.promise);

    const loading = useLibraryStore.getState().ensureLoaded();
    useAuthStore.getState().logout();
    answer.resolve({ data: { results: [entry()] } } as Awaited<ReturnType<typeof libraryApi.saves>>);
    await loading;

    expect(useLibraryStore.getState().items).toEqual({});
    expect(useLibraryStore.getState().load).toBe("idle");
  });

  it("applies only the newest of two quick writes to one paper", async () => {
    const first = deferred<Awaited<ReturnType<typeof libraryApi.save>>>();
    vi.mocked(libraryApi.save)
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({ data: entry(null) } as Awaited<ReturnType<typeof libraryApi.save>>);

    const a = useLibraryStore.getState().save(record.id, "reading", record);
    await useLibraryStore.getState().save(record.id, null, record);
    first.resolve({ data: entry("reading") } as Awaited<ReturnType<typeof libraryApi.save>>);
    await a;

    expect(useLibraryStore.getState().items[record.id]?.readingStatus).toBeNull();
  });
});
