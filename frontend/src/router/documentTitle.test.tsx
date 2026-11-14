/**
 * Every routed page names its browser tab (IR-1073, audit NAV-01, WCAG 2.4.2).
 *
 * The title comes from the route table (`handle.title`, else `handle.crumb`),
 * and a page that knows more -- a paper, a conversation, a count -- refines it
 * through `usePageTitle`. These tests go through the real route table, so a new
 * route added without a name fails here rather than shipping as "IRIS".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";

import { apiClient } from "@/api/client";
import { READER_PROTOCOL } from "@/api/runtimeReader";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { makeUser, validToken } from "@/test/authFixtures";
import type { RouteHandle } from "@/components/layout/Breadcrumbs";
import { routes, router as browserRouter } from "./index";
import { REDIRECTS } from "./redirects";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
vi.mock("@/config/institution", () => ({
  INSTITUTION: { name: "Example Research University", shortName: "ERU", logo: "example.png", emailDomain: "example.edu" },
}));

/** The first visit to a record loads the heaviest page in the app (IR-749). */
const LAZY_PAGE = { timeout: 8000 };

const CONVERSATION = "11111111-2222-4333-8444-555555555555";

/** A published paper, as the record endpoint returns it. */
const PAPER = {
  id: 7, title: "Flood Prediction in the Mananga Catchment",
  abstract: "A study of rainfall-driven flood prediction.",
  year_accomplished: 2026, year_completed: null, abstract_file: null,
  classification_name: "Applied Research", classification: "Applied Research", psced: null,
  record_type_name: "Thesis/Research", record_type: "Thesis/Research",
  pipeline_status: "published", is_ip: false, ip_type: "", for_commercialization: false,
  community_extension: false, access_count: 0, file_count: 0, created_at: "2026-09-01T08:00:00Z",
  authors: [{ id: 1, name: "R. Dela Cruz", role: null }], adviser: null, adviser_name: null, added_by: null,
  requires_ethics_review: false, requested_itso: false, requested_ierc: false, requested_ktto: false,
  owners: [], is_deleted: false, reviews: [], clearances: [],
  resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
  stage_label: "Published", files: [], workflow_state: "published", workflow_state_label: "Published",
  current_holders: [], capabilities: ["cite"], can_request_document: [], my_seats: [], is_participant: false,
  routing: { send_to_rdco: false, route_as: null, targets: [] },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
  versions: null, manuscript_unsubmitted: false, submitter_status: null,
};

function answer(url: string) {
  if (url === "/reviews/mine/") {
    return { data: { rows: [], counts: { to_review: 3, in_review: 1, done: 4 }, next: null } };
  }
  if (url === "/records/7/") return { data: PAPER };
  if (url === `/ai/runtime/conversations/${CONVERSATION}`) {
    return { data: { protocol: READER_PROTOCOL, id: CONVERSATION, revision: 0, runs: [], turns: [] } };
  }
  if (url === "/ai/conversations/") return { data: [] };
  if (url === "/ai/runtime/conversations") {
    return {
      data: {
        protocol: READER_PROTOCOL,
        conversations: [{ id: CONVERSATION, title: "Which flood models fit Mananga?", record_id: null, updated_at: "2026-11-01T00:00:00Z" }],
      },
    };
  }
  return { data: { count: 0, results: [] } };
}

beforeEach(() => {
  browserRouter.dispose();
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => answer(url) as never);
  for (const verb of ["post", "put", "patch", "delete"] as const) {
    vi.mocked(apiClient[verb]).mockResolvedValue({ data: {} } as never);
  }
  document.title = "IRIS";
});
afterEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false });
});

function visit(path: string) {
  useAuthStore.setState({
    user: makeUser({
      role_name: ROLES.ITSO,
      review_access: { my_reviews: true, offices: ["itso"], is_coordinator: false },
    }),
    accessToken: validToken(), authReady: true, isAuthenticated: true,
  });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

describe("browser tab titles", () => {
  it("names Discover", async () => {
    visit("/");
    await waitFor(() => expect(document.title).toBe("Discover · IRIS"));
  });

  it("names a record by its paper's title", async () => {
    visit("/records/7");
    await waitFor(() => expect(document.title).toBe("Flood Prediction in the Mananga Catchment · IRIS"), LAZY_PAGE);
  });

  it("names My Reviews with the work waiting on the reader", async () => {
    visit("/review");
    await waitFor(() => expect(document.title).toBe("My Reviews (3) · IRIS"));
  });

  it("names a public page, which has no shell", async () => {
    useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false, authReady: true });
    const router = createMemoryRouter(routes, { initialEntries: ["/login"] });
    render(<RouterProvider router={router} />);
    await waitFor(() => expect(document.title).toBe("Sign in · IRIS"));
  });

  it("names an address that is not a page", async () => {
    visit("/no/such/page");
    await waitFor(() => expect(document.title).toBe("Page not found · IRIS"));
  });

  it("changes with the route and does not keep a paper's title", async () => {
    const router = visit("/records/7");
    await waitFor(() => expect(document.title).toBe("Flood Prediction in the Mananga Catchment · IRIS"), LAZY_PAGE);
    await router.navigate("/opportunities");
    await waitFor(() => expect(document.title).toBe("Calls & Conferences · IRIS"));
  });

  it("does not keep the last paper's title while the next paper loads", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/records/8/") return new Promise<never>(() => {});
      return answer(url) as never;
    });
    const router = visit("/records/7");
    await waitFor(() => expect(document.title).toBe("Flood Prediction in the Mananga Catchment · IRIS"), LAZY_PAGE);
    await router.navigate("/records/8");
    await waitFor(() => expect(document.title).toBe("Paper · IRIS"));
  });

  it("names a conversation by its own title", async () => {
    visit(`/ai/conversations/${CONVERSATION}`);
    await waitFor(() => expect(document.title).toBe("Which flood models fit Mananga? · IRIS"), LAZY_PAGE);
  });

  it("names a new chat for the page, since it has no title yet", async () => {
    visit("/ai");
    await waitFor(() => expect(document.title).toBe("Ask IRIS · IRIS"), LAZY_PAGE);
  });
});

/** Every page in the table: a route that renders something and is not a redirect. */
function pages(list: RouteObject[], inherited: string | undefined, redirected: Set<string>): string[] {
  return list.flatMap((route) => {
    const handle = route.handle as RouteHandle | undefined;
    const named = handle?.title ?? handle?.crumb ?? inherited;
    if (route.children) return pages(route.children, named, redirected);
    if (!route.element || (route.path && redirected.has(route.path))) return [];
    return named ? [] : [route.path ?? "(index)"];
  });
}

describe("the route table", () => {
  it("leaves no page unnamed", () => {
    const unnamed = pages(routes, undefined, new Set(REDIRECTS.map((r) => r.path)));
    expect(unnamed).toEqual([]);
  });
});
