/**
 * The account library store (IR-566, ADR-044 §6; IR-572, ADR-070): one
 * session's saves and folders, optimistic with a visible rollback, and fenced
 * across account switches.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { libraryApi, type FolderEntry, type SavedRecordEntry } from "@/api/library";
import type { User } from "@/types/auth";
import type { RecordListItem } from "@/types/records";

import { useAuthStore } from "./auth.store";
import { useLibraryStore } from "./library.store";

// IR-572 adds the folder calls: the store now reads folders with the saves.
vi.mock("@/api/library", () => ({
  libraryApi: {
    saves: vi.fn(), save: vi.fn(), unsave: vi.fn(),
    folders: vi.fn(), createFolder: vi.fn(), renameFolder: vi.fn(), deleteFolder: vi.fn(),
    fileInFolder: vi.fn(), removeFromFolder: vi.fn(),
  },
}));

type Api = typeof libraryApi;
const answer = <K extends keyof Api>(_: K, data: unknown) =>
  ({ data }) as Awaited<ReturnType<Api[K]>>;

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
  useAuthStore.getState().login({ id, email: `r${id}@cit.edu`, role_name: "Student" } as unknown as User, "a");
}

const folder = (id: number, name: string, record_ids: number[] = []): FolderEntry => ({
  id, name, record_ids, created_at: "2026-11-01T08:00:00Z", updated_at: "2026-11-01T08:00:00Z",
});

/** Load a library holding `saved` and `folders`, as the server lists them. */
async function loaded(saved: SavedRecordEntry[], folders: FolderEntry[]) {
  vi.mocked(libraryApi.saves).mockResolvedValue(answer("saves", { results: saved }));
  vi.mocked(libraryApi.folders).mockResolvedValue(answer("folders", { results: folders, limit: 10 }));
  await useLibraryStore.getState().ensureLoaded(true);
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  vi.mocked(libraryApi.folders).mockResolvedValue(answer("folders", { results: [], limit: 10 }));
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

describe("library store: folders (IR-572)", () => {
  const names = () => useLibraryStore.getState().folders.map((f) => [f.name, f.recordIds]);

  it("loads the account's folders with its saves, and forgets both on sign-out", async () => {
    await loaded([entry()], [folder(3, "Methods", [record.id])]);

    expect(names()).toEqual([["Methods", [record.id]]]);
    expect(useLibraryStore.getState().folderLimit).toBe(10);

    useAuthStore.getState().logout();
    expect(useLibraryStore.getState().folders).toEqual([]);
  });

  it("is not ready when the folders could not be read", async () => {
    vi.mocked(libraryApi.saves).mockResolvedValue(answer("saves", { results: [entry()] }));
    vi.mocked(libraryApi.folders).mockRejectedValue(new Error("offline"));

    await useLibraryStore.getState().ensureLoaded(true);

    expect(useLibraryStore.getState().load).toBe("error");
  });

  it("creates a folder from the server's answer, and says why when it is refused", async () => {
    await loaded([], []);
    vi.mocked(libraryApi.createFolder)
      .mockResolvedValueOnce(answer("createFolder", folder(3, "Methods")))
      .mockRejectedValueOnce({ response: { status: 400, data: { code: "folder_limit", detail: "You have 10 folders. Delete one to make another." } } });

    await expect(useLibraryStore.getState().createFolder("Methods")).resolves.toMatchObject({ id: 3 });
    await expect(useLibraryStore.getState().createFolder("Results")).resolves.toBeNull();

    expect(names()).toEqual([["Methods", []]]);
    expect(useLibraryStore.getState().failure?.message).toBe("You have 10 folders. Delete one to make another.");
  });

  it("creating a name it already has keeps one folder", async () => {
    await loaded([], [folder(3, "Methods")]);
    vi.mocked(libraryApi.createFolder).mockResolvedValue(answer("createFolder", folder(3, "Methods")));

    await useLibraryStore.getState().createFolder("methods");

    expect(names()).toEqual([["Methods", []]]);
  });

  it("renames at once and rolls a refused rename back visibly", async () => {
    await loaded([], [folder(3, "Methods")]);
    vi.mocked(libraryApi.renameFolder).mockRejectedValue(new Error("offline"));

    const pending = useLibraryStore.getState().renameFolder(3, "Method papers");
    expect(names()).toEqual([["Method papers", []]]);
    await pending;

    expect(names()).toEqual([["Methods", []]]);
    expect(useLibraryStore.getState().failure?.message).toMatch(/could not rename/i);
  });

  it("deletes a folder without touching the saves, and brings it back if refused", async () => {
    await loaded([entry("reading")], [folder(3, "Methods", [record.id])]);
    vi.mocked(libraryApi.deleteFolder).mockRejectedValueOnce(new Error("offline"));

    await useLibraryStore.getState().deleteFolder(3);
    expect(names()).toEqual([["Methods", [record.id]]]);
    expect(useLibraryStore.getState().failure?.message).toMatch(/could not delete this folder/i);

    vi.mocked(libraryApi.deleteFolder).mockResolvedValueOnce(answer("deleteFolder", undefined));
    await useLibraryStore.getState().deleteFolder(3);
    expect(names()).toEqual([]);
    expect(useLibraryStore.getState().items[record.id]?.readingStatus).toBe("reading");
  });

  it("filing an unsaved paper shows it saved and filed at once, and rolls both back if refused", async () => {
    await loaded([], [folder(3, "Methods")]);
    const filing = deferred<Awaited<ReturnType<Api["fileInFolder"]>>>();
    vi.mocked(libraryApi.fileInFolder).mockReturnValue(filing.promise);

    const pending = useLibraryStore.getState().fileInFolder(3, record.id, record);
    expect(names()).toEqual([["Methods", [record.id]]]);
    expect(useLibraryStore.getState().items[record.id]).toBeDefined();
    filing.resolve(Promise.reject(new Error("offline")) as never);
    await pending;

    expect(names()).toEqual([["Methods", []]]);
    expect(useLibraryStore.getState().items[record.id]).toBeUndefined();
    expect(useLibraryStore.getState().failure).toEqual({ recordId: record.id, message: expect.stringMatching(/could not add this paper/i) });
  });

  it("keeps the server's folder and save after a filing", async () => {
    await loaded([], [folder(3, "Methods")]);
    vi.mocked(libraryApi.fileInFolder).mockResolvedValue(
      answer("fileInFolder", { folder: folder(3, "Methods", [record.id]), save: entry() }),
    );

    await expect(useLibraryStore.getState().fileInFolder(3, record.id, record)).resolves.toBe(true);

    expect(names()).toEqual([["Methods", [record.id]]]);
    expect(useLibraryStore.getState().items[record.id]?.savedAt).toBe("2026-11-01T08:00:00Z");
  });

  it("taking a paper out of a folder keeps it saved, and a refusal puts it back", async () => {
    await loaded([entry("reading")], [folder(3, "Methods", [record.id])]);
    vi.mocked(libraryApi.removeFromFolder).mockRejectedValueOnce(new Error("offline"));

    await useLibraryStore.getState().removeFromFolder(3, record.id);
    expect(names()).toEqual([["Methods", [record.id]]]);
    expect(useLibraryStore.getState().failure?.message).toMatch(/still in the folder/i);

    vi.mocked(libraryApi.removeFromFolder).mockResolvedValueOnce(answer("removeFromFolder", undefined));
    await useLibraryStore.getState().removeFromFolder(3, record.id);
    expect(names()).toEqual([["Methods", []]]);
    expect(useLibraryStore.getState().items[record.id]?.readingStatus).toBe("reading");
    expect(libraryApi.unsave).not.toHaveBeenCalled();
  });

  it("unsaving takes a paper out of every folder, and a refused unsave puts it back in them", async () => {
    await loaded([entry()], [folder(3, "Methods", [record.id]), folder(4, "Results", [record.id])]);
    vi.mocked(libraryApi.unsave).mockRejectedValueOnce(new Error("offline"));

    const pending = useLibraryStore.getState().unsave(record.id);
    expect(names()).toEqual([["Methods", []], ["Results", []]]);
    await pending;

    expect(names()).toEqual([["Methods", [record.id]], ["Results", [record.id]]]);
  });

  it("a filing answer that lands after the paper was unsaved does not put it back", async () => {
    await loaded([entry()], [folder(3, "Methods")]);
    const filing = deferred<Awaited<ReturnType<Api["fileInFolder"]>>>();
    vi.mocked(libraryApi.fileInFolder).mockReturnValue(filing.promise);
    vi.mocked(libraryApi.unsave).mockResolvedValue(answer("unsave", undefined));

    const pending = useLibraryStore.getState().fileInFolder(3, record.id, record);
    await useLibraryStore.getState().unsave(record.id);
    filing.resolve(answer("fileInFolder", { folder: folder(3, "Methods", [record.id]), save: entry() }));
    await pending;

    expect(useLibraryStore.getState().items[record.id]).toBeUndefined();
    expect(names()).toEqual([["Methods", []]]);
  });

  it("a filing answer that lands after a newer Reading status keeps the newer status", async () => {
    await loaded([entry()], [folder(3, "Methods")]);
    const filing = deferred<Awaited<ReturnType<Api["fileInFolder"]>>>();
    vi.mocked(libraryApi.fileInFolder).mockReturnValue(filing.promise);
    vi.mocked(libraryApi.save).mockResolvedValue(answer("save", entry("reading")));

    const pending = useLibraryStore.getState().fileInFolder(3, record.id, record);
    await useLibraryStore.getState().save(record.id, "reading", record);
    filing.resolve(answer("fileInFolder", { folder: folder(3, "Methods", [record.id]), save: entry(null) }));
    await pending;

    expect(useLibraryStore.getState().items[record.id]?.readingStatus).toBe("reading");
    expect(names()).toEqual([["Methods", [record.id]]]);
  });

  it("a refused take-out puts the paper back where it was in the folder", async () => {
    await loaded([entry()], [folder(3, "Methods", [7, record.id, 8])]);
    vi.mocked(libraryApi.removeFromFolder).mockRejectedValue(new Error("offline"));

    await useLibraryStore.getState().removeFromFolder(3, record.id);

    expect(names()).toEqual([["Methods", [7, record.id, 8]]]);
  });

  it("a refused unsave puts the paper back where it was in each folder", async () => {
    await loaded([entry()], [folder(3, "Methods", [7, record.id]), folder(4, "Results", [record.id, 8])]);
    vi.mocked(libraryApi.unsave).mockRejectedValue(new Error("offline"));

    await useLibraryStore.getState().unsave(record.id);

    expect(names()).toEqual([["Methods", [7, record.id]], ["Results", [record.id, 8]]]);
  });

  it("drops a folder answer that lands after the account changed", async () => {
    await loaded([], []);
    const created = deferred<Awaited<ReturnType<Api["createFolder"]>>>();
    vi.mocked(libraryApi.createFolder).mockReturnValue(created.promise);

    const pending = useLibraryStore.getState().createFolder("Methods");
    signIn(2);
    created.resolve(answer("createFolder", folder(3, "Methods")));
    await pending;

    expect(useLibraryStore.getState().folders).toEqual([]);
  });

  it("never writes a folder to browser storage", async () => {
    await loaded([], []);
    vi.mocked(libraryApi.createFolder).mockResolvedValue(answer("createFolder", folder(3, "Methods")));
    const before = JSON.stringify({ ...localStorage });

    await useLibraryStore.getState().createFolder("Methods");

    expect(JSON.stringify({ ...localStorage })).toBe(before);
  });
});
