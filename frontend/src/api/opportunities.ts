import { apiClient } from "./client";
import type { Opportunity, OpportunityBoard, OpportunityInput, SavedCallEntry } from "@/types/opportunities";

interface OpportunityPage {
  count:    number;
  next:     string | null;
  results:  Opportunity[];
  /** Whether this viewer may post (IR-530), sent beside every board page. */
  can_post?: boolean;
  /** Whether this viewer works RDCO's Call Requests queue (IR-762). */
  can_review_requests?: boolean;
}

/**
 * The most the server hands out per page (`StandardResultsPagination`).
 * Asking for it keeps a normal list to one request.
 */
const PAGE_SIZE = 100;

/** A runaway guard, not a limit anyone should reach: 50 pages is 5,000 calls. */
const MAX_PAGES = 50;

/**
 * Every page of a Call list, and the last page's flags. The screens group,
 * count and filter in the browser, so they need the whole list: reading only
 * the first page silently dropped everything past the twentieth call (IR-530).
 */
async function allPages(path: string): Promise<{ items: Opportunity[]; last: OpportunityPage }> {
  const items: Opportunity[] = [];
  let last!: OpportunityPage;
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const { data } = await apiClient.get<OpportunityPage>(path, { params: { page, page_size: PAGE_SIZE } });
    items.push(...data.results);
    last = data;
    if (!data.next) break;
  }
  return { items, last };
}

export const opportunitiesApi = {
  /** Every call on the board, across all pages, and what this viewer may do. */
  board: async (): Promise<OpportunityBoard> => {
    const { items, last } = await allPages("/opportunities/");
    return {
      items,
      can_post: last.can_post === true,
      // RDCO, who works the Call Requests queue, is who may feature (IR-762).
      can_feature: last.can_review_requests === true,
    };
  },

  /** RDCO's queue: Adviser's Calls waiting for confirmation, oldest first (IR-765). */
  requests: async (): Promise<Opportunity[]> => (await allPages("/opportunities/requests/")).items,

  /** The viewer's own Calls in every status, so a poster sees where each stands (IR-765). */
  mine: async (): Promise<Opportunity[]> => (await allPages("/opportunities/mine/")).items,

  create: (input: OpportunityInput) =>
    apiClient.post<Opportunity>("/opportunities/", input),

  update: (id: number, input: OpportunityInput) =>
    apiClient.patch<Opportunity>(`/opportunities/${id}/`, input),

  /** RDCO sets or clears Featured (ADR-050 decision 12). */
  setFeatured: (id: number, featured: boolean) =>
    apiClient.patch<Opportunity>(`/opportunities/${id}/`, { is_featured: featured }),

  /**
   * RDCO's decision on a request. It names the version RDCO saw (`updated_at`
   * as served), so a Call changed or decided since answers 409 (IR-762).
   */
  confirm: (id: number, seen: string) =>
    apiClient.post<Opportunity>(`/opportunities/${id}/confirm/`, { updated_at: seen }),

  reject: (id: number, seen: string, reason: string) =>
    apiClient.post<Opportunity>(`/opportunities/${id}/reject/`, { updated_at: seen, reason }),

  /** Plain delete: a poster's own Call, or RDCO's of a Call that needs no reason. */
  remove: (id: number) => apiClient.delete(`/opportunities/${id}/`),

  /** RDCO deletes an Adviser's Call with a reason the Adviser receives (decision 11). */
  removeWithReason: (id: number, reason: string) =>
    apiClient.post(`/opportunities/${id}/remove/`, { reason }),

  /** The reader's saved Calls, newest first (IR-649). */
  saved: () => apiClient.get<{ results: SavedCallEntry[] }>("/opportunities/saved/"),

  /** Save a confirmed Call; idempotent. A Call that isn't confirmed answers 404. */
  save: (id: number) => apiClient.put<SavedCallEntry>(`/opportunities/${id}/save/`),

  /** Unsave; idempotent, and works for a Call that became unavailable. */
  unsave: (id: number) => apiClient.delete(`/opportunities/${id}/save/`),

  /**
   * The deadline as a calendar file.
   *
   * Fetched through `apiClient` rather than pointed at by a plain link so the
   * Authorization header goes with it -- a bare <a href> would hit the endpoint
   * unauthenticated and get a 401 instead of a file.
   */
  calendar: (id: number) =>
    apiClient.get<Blob>(`/opportunities/${id}/calendar/`, { responseType: "blob" }),
};
