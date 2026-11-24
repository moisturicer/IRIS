/**
 * The Review pane footer's actions (IR-1139): the prototype's merge box -- a
 * "More review actions" menu, at most one secondary pill and one filled
 * primary. Every control is a granted capability; a held one is disabled with
 * the server's reason. Where *Finish review* is granted a verdict opens it on
 * that verdict, so drafts still go with it (ADR-032 §7, IR-875). Every query
 * goes through the accessible tree.
 */
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

import { recordsApi } from "@/api/records";

import { ReviewFooterActions } from "./ReviewFooterActions";
import { REVIEWER_FOOTER_ACTIONS } from "./reviewActions";

vi.mock("@/api/records", () => ({
  recordsApi: {
    releaseEmbargo: vi.fn(() => Promise.resolve({ data: {} })),
    documentRequestSlots: vi.fn(() => new Promise(() => {})),
  },
}));

const EMBARGO = "Under embargo until 01 Jan 2099. Release the embargo, then publish.";

function record(blockedOutcomes: Record<string, string> = {}): RecordDetail {
  return {
    id: 7,
    title: "Groundwater Recharge Mapping in Metro Cebu",
    revision: { party: "rdco", label: "RDCO", blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
    decision: {
      party: "rdco", outcomes: ["publish", "keep_unlisted", "reject"], blocked: null, blocked_outcomes: blockedOutcomes,
      closes: { assignments: [], document_requests: 0 }, token: "t", author_hints: [],
    },
    versions: [],
  } as unknown as RecordDetail;
}

const RDCO: Capability[] = ["finish_review", "accept_publish", "keep_unlisted", "request_revision", "reject", "request_document"];
const OFFICE: Capability[] = ["finish_review", "office_review", "request_revision", "request_document", "add_reviewer"];

function renderFooter(can: Capability[], { held = {}, finishing = true, lead, drafts }: {
  held?: Record<string, string>; finishing?: boolean; lead?: ReactNode; drafts?: number;
} = {}) {
  const onFinish = vi.fn();
  const onChanged = vi.fn();
  // The list the Review workspace gives its footer, so these tests can't drift from it.
  const view = renderScreen(
    <ReviewFooterActions record={record(held)} can={new Set(can)} actions={REVIEWER_FOOTER_ACTIONS} finishing={finishing}
      onFinish={onFinish} lead={lead} onChanged={onChanged} drafts={drafts} />,
  );
  return { ...view, onFinish, onChanged };
}

const toolbar = () => within(screen.getByRole("toolbar", { name: "Review actions" }));
const openMenu = async () => {
  await userEvent.click(screen.getByRole("button", { name: "More review actions" }));
  return within(screen.getByRole("menu", { name: "More review actions" }));
};

describe("ReviewFooterActions", () => {
  it("gives RDCO Accept & publish, Keep unlisted beside it, and the rest in the menu", async () => {
    const { onFinish } = renderFooter(RDCO);

    const bar = toolbar();
    expect(bar.getAllByRole("button").map((b) => b.textContent)).toEqual(["", "Keep unlisted…", "Accept & publish…"]);
    expect(bar.getByRole("button", { name: "Accept & publish…" })).toBeEnabled();

    const menu = await openMenu();
    expect(menu.getAllByRole("menuitem").map((m) => m.textContent)).toEqual([
      "Request changes…", "Reject…",
    ]);
    await userEvent.click(menu.getByRole("menuitem", { name: "Reject…" }));
    expect(onFinish).toHaveBeenCalledWith("reject");

    await userEvent.click(bar.getByRole("button", { name: "Accept & publish…" }));
    expect(onFinish).toHaveBeenLastCalledWith("publish");
  });

  it("holds Accept & publish on an embargoed paper, says why, and offers the release", async () => {
    renderFooter([...RDCO, "release_embargo"], { held: { publish: EMBARGO } });

    const publish = screen.getByRole("button", { name: "Accept & publish…" });
    expect(publish).toBeDisabled();
    expect(publish).toHaveAccessibleDescription(`${EMBARGO} Release embargo…`);
    expect(screen.getByRole("button", { name: "Keep unlisted…" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "Release embargo…" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Release this embargo?" })).getByRole("button", { name: "Release" }));
    expect(recordsApi.releaseEmbargo).toHaveBeenCalledWith(7);
  });

  it("does not offer the release to someone the server does not let release it", () => {
    renderFooter(RDCO, { held: { publish: EMBARGO } });

    expect(screen.getByText(EMBARGO)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Release embargo…" })).not.toBeInTheDocument();
  });

  // Changed deliberately by IR-1254: Request documents left the menu for the Documents tab.
  it("gives an office reviewer one Finish review, with a colleague in the menu", async () => {
    const { onFinish } = renderFooter(OFFICE);

    expect(toolbar().getAllByRole("button").map((b) => b.textContent)).toEqual(["", "Finish review…"]);
    const menu = await openMenu();
    expect(menu.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Add a colleague…"]);

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More review actions" })).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Finish review…" }));
    expect(onFinish).toHaveBeenCalledWith();
  });

  it("offers Send N comments while drafts wait, opening Finish review on Comment only (IR-1194)", async () => {
    const { onFinish } = renderFooter(RDCO, { drafts: 2 });

    expect(toolbar().getAllByRole("button").map((b) => b.textContent))
      .toEqual(["", "Send 2 comments…", "Keep unlisted…", "Accept & publish…"]);
    await userEvent.click(screen.getByRole("button", { name: "Send 2 comments…" }));
    expect(onFinish).toHaveBeenCalledWith("comment_only");
  });

  it("offers no Send without drafts, or where the viewer may not finish a review", () => {
    const { unmount } = renderFooter(OFFICE, { drafts: 0 });
    expect(screen.queryByRole("button", { name: /^Send/ })).not.toBeInTheDocument();
    unmount();
    renderFooter(["withdraw_revision"], { finishing: false, drafts: 2 });
    expect(screen.queryByRole("button", { name: /^Send/ })).not.toBeInTheDocument();
  });

  it("names one draft in the singular", () => {
    renderFooter(OFFICE, { drafts: 1 });
    expect(screen.getByRole("button", { name: "Send 1 comment…" })).toBeInTheDocument();
  });

  it("keeps Open review or Claim as the primary and puts every granted act in the menu", async () => {
    // Changed deliberately by IR-1254: Withdraw revision request stands in for Request documents.
    renderFooter(["withdraw_revision"], {
      finishing: false, lead: <button type="button">Open review</button>,
    });

    expect(toolbar().getAllByRole("button").map((b) => b.textContent)).toEqual(["", "Open review"]);
    const menu = await openMenu();
    expect(menu.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Withdraw revision request"]);
  });

  // IR-1254 (ADR-032 §7 as amended 2026-11-21): a document request is the Documents
  // tab's, beside the requests it makes, so the footer never offers one.
  it("never offers Request documents, and draws nothing when that is all that was granted", async () => {
    const { unmount } = renderFooter(OFFICE);
    const menu = await openMenu();
    expect(menu.queryByRole("menuitem", { name: "Request documents" })).not.toBeInTheDocument();
    unmount();

    renderFooter(["request_document"], { finishing: false });
    expect(screen.queryByRole("toolbar", { name: "Review actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request documents" })).not.toBeInTheDocument();
  });

  it("draws nothing for someone granted nothing", () => {
    renderFooter([], { finishing: false });

    expect(screen.queryByRole("toolbar", { name: "Review actions" })).not.toBeInTheDocument();
  });

  it("has no blocking accessibility violations with its menu open", async () => {
    const { container } = renderFooter([...RDCO, "release_embargo"], { held: { publish: EMBARGO } });
    await openMenu();

    await expectNoBlockingA11yViolations(container);
  });
});
