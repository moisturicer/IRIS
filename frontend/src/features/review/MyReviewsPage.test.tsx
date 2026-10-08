/**
 * My Reviews (IR-268; ADR-032 §9 and its 2026-10-08 Amendment, ui-ux/16 §5).
 * Every query goes through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { User } from "@/types/auth";
import type { MyReviewsPage as Page, MyReviewsRow } from "@/types/reviews";

import MyReviewsPage from "./MyReviewsPage";

const mine = vi.fn();
const claim = vi.fn();
const assignOptions = vi.fn();
const assign = vi.fn();

vi.mock("@/api/reviews", () => ({
  reviewsApi: { mine: (query: unknown) => mine(query) },
  seatsApi: {
    claim: (id: number) => claim(id),
    assignOptions: (id: number) => assignOptions(id),
    assign: (id: number, reviewer: number) => assign(id, reviewer),
  },
}));

function row(overrides: Partial<MyReviewsRow> = {}): MyReviewsRow {
  return {
    key: "seat:1", kind: "seat", record: 7, title: "Smart Campus Energy Monitor",
    record_type_name: "Thesis / Research", party: "itso", party_label: "ITSO",
    stage_label: null, seat: 1, assignment: 3, holder: 5, holder_name: "Ana Reyes",
    is_mine: true, routed_by: "Prof. Santos", routed_reason: "Potential IP concern",
    submitted_by: null, waiting_since: "2026-10-01T00:00:00Z", waiting_days: 2,
    waiting_on: null, outcome: null, outcome_label: null, decided_at: null,
    can_claim: false, can_assign: false,
    ...overrides,
  };
}

const POOL = row({
  key: "pool:3", kind: "pool", record: 8, title: "AI-Based Medical Imaging",
  seat: null, holder: null, holder_name: null, is_mine: false, can_claim: true,
  routed_by: "Prof. Lim", routed_reason: "Ethics question",
});

function page(rows: MyReviewsRow[], overrides: Partial<Page> = {}): { data: Page } {
  return { data: { rows, counts: { to_review: 2, in_review: 1, done: 4 }, next: null, ...overrides } };
}

function signIn(isCoordinator = false) {
  useAuthStore.setState({
    user: {
      id: 5, email: "ana@cit.edu", first_name: "Ana", middle_initial: "", last_name: "Reyes",
      role: 3, role_name: "ITSO", is_staff: false, is_superuser: false, is_verified: true,
      is_locked: false, consent_given: true, date_joined: "2026-01-01", college_name: "",
      department_name: "", course_name: "",
      review_access: { my_reviews: true, offices: ["itso"], is_coordinator: isCoordinator },
    } as User,
  });
}

function Where() {
  const { pathname, search } = useLocation();
  return <input readOnly aria-label="Location" value={pathname + search} />;
}

function show(route = "/review") {
  return renderScreen(
    <Routes>
      <Route path="/review" element={<><MyReviewsPage /><Where /></>} />
    </Routes>,
    { route },
  );
}

beforeEach(() => {
  signIn();
  mine.mockReset().mockResolvedValue(page([row(), POOL]));
  claim.mockReset().mockResolvedValue({ data: {} });
  assignOptions.mockReset().mockResolvedValue({
    data: {
      assignment: 3, party: "itso", party_label: "ITSO",
      members: [{ id: 5, name: "Ana Reyes", seated: false }, { id: 6, name: "Ben Cruz", seated: false }],
    },
  });
  assign.mockReset().mockResolvedValue({ data: {} });
});

afterEach(() => useAuthStore.setState({ user: null }));

describe("MyReviewsPage", () => {
  it("shows three tabs with their counts and the rows of To review", async () => {
    const { container } = show();

    expect(await screen.findByRole("heading", { level: 1, name: "My Reviews" })).toBeInTheDocument();
    const tabs = screen.getByRole("tablist", { name: "My Reviews" });
    expect(within(tabs).getByRole("tab", { name: /To review 2/ })).toHaveAttribute("aria-selected", "true");
    expect(within(tabs).getByRole("tab", { name: /In review 1/ })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: /Done 4/ })).toBeInTheDocument();

    expect(await screen.findByRole("link", { name: "Smart Campus Energy Monitor" }))
      .toHaveAttribute("href", "/records/7?section=review");
    expect(screen.getByText("ITSO · You")).toBeInTheDocument();
    expect(screen.getByText("ITSO · Unassigned")).toBeInTheDocument();
    expect(screen.getByText("Routed by Prof. Santos · “Potential IP concern”", { exact: false })).toBeInTheDocument();
    expect(mine).toHaveBeenCalledWith({ tab: "to_review", outcome: null, office: null, cursor: null });
    await expectNoBlockingA11yViolations(container);
  });

  it("opens a review in Paper View, never on the old decision form", async () => {
    show();
    const open = await screen.findByRole("link", { name: "Open review: Smart Campus Energy Monitor" });
    expect(open).toHaveAttribute("href", "/records/7?section=review");
    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("href")).not.toContain("/evaluate");
    }
  });

  it("claims an unassigned record, refetches, and says where it went", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Claim review: AI-Based Medical Imaging" }));

    expect(claim).toHaveBeenCalledWith(3);
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Claimed. It's in To review as yours."),
    );
    expect(mine).toHaveBeenCalledTimes(2);
  });

  it("reports a refused claim on its row and announces nothing", async () => {
    claim.mockRejectedValue({ response: { data: { detail: "Someone at ITSO has already taken this review." } } });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Claim review: AI-Based Medical Imaging" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already taken this review");
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("offers Assign only where the server allows it, and assigns the member picked", async () => {
    mine.mockResolvedValue(page([{ ...POOL, can_assign: true }]));
    signIn(true);
    show();

    await userEvent.click(await screen.findByRole("button", { name: "Assign reviewer: AI-Based Medical Imaging" }));
    const picker = await screen.findByRole("combobox", { name: "Reviewer at ITSO" });
    await userEvent.selectOptions(picker, "6");
    await userEvent.click(screen.getByRole("button", { name: "Assign" }));

    expect(assign).toHaveBeenCalledWith(3, 6);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Assigned to Ben Cruz. It's in their To review."));
  });

  it("offers no Assign to a member who is not a coordinator", async () => {
    show();
    await screen.findByRole("button", { name: "Claim review: AI-Based Medical Imaging" });
    expect(screen.queryByRole("button", { name: /Assign reviewer/ })).not.toBeInTheDocument();
  });

  it("marks a record waiting on its author in place of the action", async () => {
    mine.mockResolvedValue(page([row({ waiting_on: "author" })]));
    show("/review?tab=in_review");

    expect(await screen.findByText("Waiting on author")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Continue review/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Smart Campus Energy Monitor" })).toBeInTheDocument();
  });

  it("filters Done by outcome, keeps the filter in the URL, and pages with Show more", async () => {
    const done = row({ key: "seat:9", outcome: "cleared", outcome_label: "Cleared", decided_at: "2026-10-05T00:00:00Z" });
    mine.mockResolvedValue(page([done], { next: "cursor-2" }));
    show("/review?tab=done");

    expect(await screen.findByText("Cleared", { selector: "span" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Finding recorded" }));
    await waitFor(() =>
      expect(mine).toHaveBeenLastCalledWith({ tab: "done", outcome: "finding", office: null, cursor: null }),
    );
    expect(screen.getByLabelText("Location")).toHaveValue("/review?tab=done&outcome=finding");
    expect(screen.getByRole("button", { name: "Finding recorded" })).toHaveAttribute("aria-pressed", "true");

    mine.mockResolvedValueOnce(page([row({ key: "seat:10", record: 11, title: "Older paper", outcome: "finding", outcome_label: "Finding recorded" })]));
    await userEvent.click(await screen.findByRole("button", { name: "Show more" }));
    expect(await screen.findByRole("link", { name: "Older paper" })).toBeInTheDocument();
    expect(mine).toHaveBeenLastCalledWith({ tab: "done", outcome: "finding", office: null, cursor: "cursor-2" });
  });

  it("gives a coordinator, and only a coordinator, a view of their whole office", async () => {
    show();
    await screen.findByRole("tablist", { name: "My Reviews" });
    expect(screen.queryByRole("button", { name: "All of ITSO" })).not.toBeInTheDocument();
  });

  it("lists the coordinator's whole office, with each seat's holder", async () => {
    signIn(true);
    mine.mockResolvedValue(page([row({ is_mine: false, holder_name: "Ben Cruz" })]));
    show();

    await userEvent.click(await screen.findByRole("button", { name: "All of ITSO" }));
    await waitFor(() =>
      expect(mine).toHaveBeenLastCalledWith({ tab: "to_review", outcome: null, office: "itso", cursor: null }),
    );
    expect(await screen.findByText("ITSO · Ben Cruz")).toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toHaveValue("/review?office=itso");
  });

  it("translates an old Review Queue bookmark once", async () => {
    show("/review?status=declined");
    await waitFor(() => expect(screen.getByLabelText("Location")).toHaveValue("/review?tab=done"));
    expect(mine).toHaveBeenCalledWith({ tab: "done", outcome: null, office: null, cursor: null });
  });

  it("says what arrives in an empty tab", async () => {
    mine.mockResolvedValue(page([], { counts: { to_review: 0, in_review: 0, done: 0 } }));
    show();
    expect(await screen.findByText("Nothing to review")).toBeInTheDocument();
    expect(screen.getByText(/Records routed to ITSO appear here until someone claims them/)).toBeInTheDocument();
  });
});
