import { apiClient } from "./client";
import type { Opportunity, OpportunityBoard, OpportunityInput } from "@/types/opportunities";

interface OpportunityPage {
  count:    number;
  next:     string | null;
  results:  Opportunity[];
  /** Whether this viewer may post (IR-530), sent beside every page. */
  can_post: boolean;
}

/**
 * The most the server hands out per page (`StandardResultsPagination`).
 * Asking for it keeps a normal board to one request.
 */
const PAGE_SIZE = 100;

/** A runaway guard, not a limit anyone should reach: 50 pages is 5,000 calls. */
const MAX_PAGES = 50;

export const opportunitiesApi = {
  /**
   * Every call on the board, across all pages.
   *
   * The board groups, counts and filters in the browser, so it needs the whole
   * list. Reading only the first page silently dropped everything past the
   * twentieth call and made every count wrong (IR-530).
   */
  board: async (): Promise<OpportunityBoard> => {
    const items: Opportunity[] = [];
    let canPost = false;
    for (let page = 1; page <= MAX_PAGES; page += 1) {
      const { data } = await apiClient.get<OpportunityPage>("/opportunities/", {
        params: { page, page_size: PAGE_SIZE },
      });
      items.push(...data.results);
      canPost = data.can_post;
      if (!data.next) break;
    }
    return { items, can_post: canPost };
  },

  create: (input: OpportunityInput) =>
    apiClient.post<Opportunity>("/opportunities/", input),

  update: (id: number, input: OpportunityInput) =>
    apiClient.patch<Opportunity>(`/opportunities/${id}/`, input),

  remove: (id: number) => apiClient.delete(`/opportunities/${id}/`),

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
