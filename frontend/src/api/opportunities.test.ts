/**
 * The board reads every page (IR-530). It used to read only the first, so
 * the twenty-first call never appeared and every count was short.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const post = vi.fn();
const patch = vi.fn();
vi.mock("./client", () => ({
  apiClient: {
    get: (...args: unknown[]) => get(...args),
    post: (...args: unknown[]) => post(...args),
    patch: (...args: unknown[]) => patch(...args),
  },
}));

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

  it("lets only RDCO, who reviews requests, feature a new call (IR-764)", async () => {
    get.mockResolvedValueOnce({ data: { count: 0, next: null, results: [], can_post: true, can_review_requests: true } });
    expect((await opportunitiesApi.board()).can_feature).toBe(true);
    get.mockResolvedValueOnce({ data: { count: 0, next: null, results: [], can_post: true, can_review_requests: false } });
    expect((await opportunitiesApi.board()).can_feature).toBe(false);
    get.mockResolvedValueOnce({ data: { count: 0, next: null, results: [], can_post: true } });
    expect((await opportunitiesApi.board()).can_feature).toBe(false);
  });
});

describe("RDCO's acts and a poster's own Calls (IR-765)", () => {
  it("reads every page of the requests queue and of the poster's own Calls", async () => {
    get
      .mockResolvedValueOnce({ data: { count: 2, next: "/opportunities/requests/?page=2", results: [row(1)] } })
      .mockResolvedValueOnce({ data: { count: 2, next: null, results: [row(2)] } })
      .mockResolvedValueOnce({ data: { count: 1, next: null, results: [row(3)] } });

    expect((await opportunitiesApi.requests()).map((o) => o.id)).toEqual([1, 2]);
    expect(get).toHaveBeenNthCalledWith(1, "/opportunities/requests/", { params: { page: 1, page_size: 100 } });
    expect((await opportunitiesApi.mine()).map((o) => o.id)).toEqual([3]);
    expect(get).toHaveBeenLastCalledWith("/opportunities/mine/", { params: { page: 1, page_size: 100 } });
  });

  it("names the version RDCO saw when it decides, and the reason when it rejects or removes", async () => {
    post.mockResolvedValue({ data: {} });
    patch.mockResolvedValue({ data: {} });

    await opportunitiesApi.confirm(4, "2026-11-01T00:00:00Z");
    expect(post).toHaveBeenLastCalledWith("/opportunities/4/confirm/", { updated_at: "2026-11-01T00:00:00Z" });
    await opportunitiesApi.reject(4, "2026-11-01T00:00:00Z", "Broken link.");
    expect(post).toHaveBeenLastCalledWith("/opportunities/4/reject/", { updated_at: "2026-11-01T00:00:00Z", reason: "Broken link." });
    await opportunitiesApi.removeWithReason(5, "Duplicate.");
    expect(post).toHaveBeenLastCalledWith("/opportunities/5/remove/", { reason: "Duplicate." });
    await opportunitiesApi.setFeatured(6, true);
    expect(patch).toHaveBeenLastCalledWith("/opportunities/6/", { is_featured: true });
  });
});
