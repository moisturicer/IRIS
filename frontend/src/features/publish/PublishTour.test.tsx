/**
 * The Publish tour (IR-1342, AC 2): a new student's first Publish runs a tour
 * over the dialog, drawn inside its panel so it is part of the aria-modal
 * tree. Closing the tour leaves the dialog and its draft as they were, and
 * never asks "Leave this submission?".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTourSession } from "@/features/onboarding/tourSession";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { act, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import { PublishDialog } from "./PublishDialog";

vi.mock("@/api/records", () => ({
  recordsApi: {
    recordTypes: vi.fn(),
    classifications: vi.fn(),
    pscedList: vi.fn(),
    create: vi.fn(),
    detail: vi.fn(),
    duplicateMatches: vi.fn(),
  },
}));
vi.mock("@/api/accounts", () => ({
  accountsApi: { listAdvisers: vi.fn(), markTourSeen: vi.fn() },
}));
vi.mock("@/api/guidelines", () => ({
  guidelinesApi: { list: vi.fn(), advisersTemplates: vi.fn() },
}));

const { recordsApi } = await import("@/api/records");
const { accountsApi } = await import("@/api/accounts");
const { guidelinesApi } = await import("@/api/guidelines");

function page<T>(results: T[]) {
  return { data: { count: results.length, next: null, previous: null, results } };
}

function signIn(toursSeen: string[]) {
  useAuthStore.setState({ user: { ...makeUser({ role_name: ROLES.STUDENT, can_author: true }), tours_seen: toursSeen } });
}

beforeEach(() => {
  useTourSession.getState().reset();
  vi.mocked(recordsApi.recordTypes).mockResolvedValue(page([{ id: 1, name: "Proposal" }, { id: 2, name: "Thesis / Research" }]) as never);
  vi.mocked(recordsApi.classifications).mockResolvedValue(page([]) as never);
  vi.mocked(recordsApi.pscedList).mockResolvedValue(page([]) as never);
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue(page([]) as never);
  vi.mocked(accountsApi.markTourSeen).mockResolvedValue({ data: { tours_seen: ["publish"] } } as never);
  vi.mocked(guidelinesApi.list).mockResolvedValue({ data: [] } as never);
  vi.mocked(guidelinesApi.advisersTemplates).mockResolvedValue({ data: [] } as never);
});

afterEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ user: null });
});

describe("the first Publish (AC 2)", () => {
  it("runs the tour inside the dialog, from the form's first step", async () => {
    signIn([]);
    renderScreen(<PublishDialog />, { route: "/?publish=new" });

    const dialog = await screen.findByRole("dialog", { name: "Publish your research" });
    const tour = await within(dialog).findByRole("dialog", { name: "Publish tour" });
    expect(tour).toHaveTextContent("Four steps");
    // The steps on screen: the four steps, the type, the file, leaving, how it goes.
    expect(tour).toHaveTextContent("Step 1 of 5");
    await expectNoBlockingA11yViolations(document.body);
  });

  it("Escape closes the tour alone: the dialog stays, nothing is asked, nothing is created", async () => {
    signIn([]);
    renderScreen(<PublishDialog />, { route: "/?publish=new" });
    const dialog = await screen.findByRole("dialog", { name: "Publish your research" });
    await within(dialog).findByRole("dialog", { name: "Publish tour" });

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Publish tour" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Publish your research" })).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "What are you publishing?" })).toBeInTheDocument();
    expect(recordsApi.create).not.toHaveBeenCalled();
    expect(accountsApi.markTourSeen).toHaveBeenCalledWith("publish");
    // Focus is back in the dialog, not on the page behind it.
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("Next walks the tour and never moves the dialog off its step", async () => {
    signIn([]);
    renderScreen(<PublishDialog />, { route: "/?publish=new" });
    await screen.findByRole("dialog", { name: "Publish tour" });
    for (let i = 0; i < 4; i++) await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("dialog", { name: "Publish tour" })).toHaveTextContent("How publishing goes");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(screen.queryByRole("dialog", { name: "Publish tour" })).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Publish steps" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "What are you publishing?" })).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("a second opening shows no tour", async () => {
    signIn(["publish"]);
    renderScreen(<PublishDialog />, { route: "/?publish=new" });
    await screen.findByRole("radiogroup", { name: "What are you publishing?" });
    await act(async () => {});
    expect(screen.queryByRole("dialog", { name: "Publish tour" })).not.toBeInTheDocument();
  });

  it("Settings' link starts it again, and opening it this way creates nothing", async () => {
    signIn(["publish"]);
    renderScreen(<PublishDialog />, { route: "/?publish=new&tour=publish" });
    expect(await screen.findByRole("dialog", { name: "Publish tour" })).toBeInTheDocument();
    await waitFor(() => expect(recordsApi.create).not.toHaveBeenCalled());
  });
});
