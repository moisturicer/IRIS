/**
 * The board reads every page (IR-530). It used to read only the first, so
 * the twenty-first call never appeared and every count was short.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
vi.mock("./client", () => ({ apiClient: { get: (...args: unknown[]) => get(...args) } }));

const { opportunitiesApi } = await import("./opportunities");

const row = (id: number) => ({ id, title: `Call ${id}` });

afterEach(() => vi.clearAllMocks());

describe("opportunitiesApi.board", () => {
  it("follows the pages until the server says there are no more", async () => {
    get
      .mockResolvedValueOnce({ data: { count: 3, next: "/opportunities/?page=2", results: [row(1), row(2)], can_post: true } })
      .mockResolvedValueOnce({ data: { count: 3, next: null, results: [row(3)], can_post: true } });

    const board = await opportunitiesApi.board();

    expect(board.items.map((o) => o.id)).toEqual([1, 2, 3]);
    expect(board.can_post).toBe(true);
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenNthCalledWith(1, "/opportunities/", { params: { page: 1, page_size: 100 } });
    expect(get).toHaveBeenNthCalledWith(2, "/opportunities/", { params: { page: 2, page_size: 100 } });
  });

  it("takes can_post from the server, never assuming it", async () => {
    get.mockResolvedValueOnce({ data: { count: 0, next: null, results: [], can_post: false } });
    expect((await opportunitiesApi.board()).can_post).toBe(false);
  });
});
