/**
 * The Review section's action bar (IR-412; spec §4.7).
 *
 * Its buttons come from the capabilities adapter only: an action the viewer
 * was not granted is absent, one that is granted but blocked is disabled and
 * says why, and an action that ends the review asks first. Each ADR-032
 * action (IR-261, 269–273) arrives as one more entry in `REVIEW_ACTIONS`,
 * with its own dialog, and the bar itself does not change -- which these
 * tests show by handing it actions it has never seen, and by the real
 * *Request documents* entry. Every query goes through the accessible tree.
 */
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

import { recordsApi } from "@/api/records";

import { ReviewActionBar } from "./ReviewActionBar";
import type { ReviewAction, ReviewActionDialogProps } from "./reviewActions";

vi.mock("@/api/records", () => ({
  recordsApi: {
    documentRequestSlots: vi.fn(() => Promise.resolve({ data: [{ id: 3, name: "Ethics Clearance" }] })),
    createDocumentRequest: vi.fn(() => Promise.resolve({ data: { id: 1 } })),
  },
}));

const record = {
  id: 7,
  title: "Groundwater Recharge Mapping in Metro Cebu",
  can_request_document: ["ierc"],
  current_holders: [{ party: "ierc", label: "IERC", opened_at: null, opened_by: null }],
} as unknown as RecordDetail;

function RouteDialog({ onClose, onDone }: ReviewActionDialogProps) {
  return (
    <div role="dialog" aria-label="Route this record">
      <button type="button" onClick={() => onDone("Routed to ITSO.")}>
        Send
      </button>
      <button type="button" onClick={onClose}>
        Cancel
      </button>
    </div>
  );
}

const route: ReviewAction = {
  kind: "dialog",
  capability: "route",
  label: "Route",
  icon: "fa-route",
  Dialog: RouteDialog,
};

const publish = vi.fn(() => Promise.resolve("Published."));

const acceptAndPublish: ReviewAction = {
  kind: "terminal",
  capability: "decide",
  label: "Accept & publish",
  icon: "fa-check",
  confirm: {
    title: "Accept and publish this record?",
    consequence: "It becomes public in Discover, and the review ends.",
    confirmLabel: "Accept & publish",
  },
  run: publish,
};

const reviseBlocked: ReviewAction = {
  kind: "dialog",
  capability: "request_revision",
  label: "Request revision",
  icon: "fa-arrow-rotate-left",
  blockedReason: () => "Waiting on the documents IERC asked for.",
  Dialog: RouteDialog,
};

function renderBar(
  granted: Capability[],
  actions?: ReviewAction[],
  extra: { secondary?: ReactNode; onChanged?: () => void } = {},
) {
  return renderScreen(
    <ReviewActionBar
      record={record}
      can={new Set(granted)}
      actions={actions}
      secondary={extra.secondary}
      onChanged={extra.onChanged ?? (() => {})}
    />,
  );
}

const buttonNames = () =>
  within(screen.getByRole("toolbar", { name: "Review actions" }))
    .getAllByRole("button")
    .map((b) => b.textContent?.trim());

describe("ReviewActionBar", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders exactly the actions the viewer was granted", async () => {
    const { container } = renderBar(["route"], [route, acceptAndPublish, reviseBlocked]);

    expect(buttonNames()).toEqual(["Route"]);
    expect(screen.queryByRole("button", { name: "Accept & publish" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request revision" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("puts an action that ends the review last, whatever order it was given in", () => {
    renderBar(["route", "decide"], [acceptAndPublish, route]);

    expect(buttonNames()).toEqual(["Route", "Accept & publish"]);
  });

  it("renders nothing when nothing was granted", () => {
    renderBar([], [route, acceptAndPublish]);

    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });

  it("disables a blocked action and says why, next to it", async () => {
    const { container } = renderBar(["request_revision"], [reviseBlocked]);

    const button = screen.getByRole("button", { name: "Request revision" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Waiting on the documents IERC asked for.");
    expect(screen.getByText("Waiting on the documents IERC asked for.")).toBeVisible();
    await expectNoBlockingA11yViolations(container);
  });

  it("opens an action's own dialog, and reports its outcome when it is done", async () => {
    const onChanged = vi.fn();
    renderBar(["route"], [route], { onChanged });

    await userEvent.click(screen.getByRole("button", { name: "Route" }));
    const dialog = screen.getByRole("dialog", { name: "Route this record" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Send" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Routed to ITSO.");
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("closes an action's dialog on cancel, having changed nothing", async () => {
    const onChanged = vi.fn();
    renderBar(["route"], [route], { onChanged });

    await userEvent.click(screen.getByRole("button", { name: "Route" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("asks before an action that ends the review, stating the consequence", async () => {
    const onChanged = vi.fn();
    renderBar(["decide"], [acceptAndPublish], { onChanged });

    await userEvent.click(screen.getByRole("button", { name: "Accept & publish" }));
    const confirm = screen.getByRole("dialog", { name: "Accept and publish this record?" });
    expect(confirm).toHaveTextContent("It becomes public in Discover, and the review ends.");

    await userEvent.click(within(confirm).getByRole("button", { name: "Cancel" }));
    expect(publish).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Accept & publish" }));
    await userEvent.click(
      within(screen.getByRole("dialog", { name: "Accept and publish this record?" })).getByRole("button", {
        name: "Accept & publish",
      }),
    );

    expect(publish).toHaveBeenCalledOnce();
    expect(await screen.findByRole("status")).toHaveTextContent("Published.");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("keeps the confirmation open and says what went wrong when the action fails", async () => {
    publish.mockRejectedValueOnce({ response: { data: { detail: "This record is no longer yours to decide." } } });
    renderBar(["decide"], [acceptAndPublish]);

    await userEvent.click(screen.getByRole("button", { name: "Accept & publish" }));
    const confirm = screen.getByRole("dialog", { name: "Accept and publish this record?" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Accept & publish" }));

    expect(await within(confirm).findByRole("alert")).toHaveTextContent(
      "This record is no longer yours to decide.",
    );
  });

  it("carries a secondary link in the same toolbar", () => {
    renderBar(["route"], [route], { secondary: <a href="/review/7/evaluate">Record a decision (current form)</a> });

    const bar = screen.getByRole("toolbar", { name: "Review actions" });
    expect(within(bar).getByRole("link", { name: "Record a decision (current form)" })).toBeInTheDocument();
  });

  it("moves between its controls with the arrow keys", async () => {
    renderBar(["route", "decide"], [route, acceptAndPublish]);

    screen.getByRole("button", { name: "Route" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("button", { name: "Accept & publish" })).toHaveFocus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("button", { name: "Route" })).toHaveFocus();
  });
});

describe("the real actions (REVIEW_ACTIONS)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("offers Request documents under `request_document`, through its own dialog", async () => {
    const onChanged = vi.fn();
    renderBar(["request_document"], undefined, { onChanged });

    await userEvent.click(screen.getByRole("button", { name: "Request documents" }));
    const dialog = screen.getByRole("dialog", { name: "Request documents" });
    await userEvent.click(await within(dialog).findByRole("checkbox", { name: "Ethics Clearance" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Message to the owner/ }), "Please attach it.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send request" }));

    expect(recordsApi.createDocumentRequest).toHaveBeenCalledWith(7, {
      message: "Please attach it.",
      items: [{ slot: 3 }],
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Documents requested. The owner has been notified.",
    );
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("offers nothing a viewer with no review capability was not granted", () => {
    renderBar(["cite", "edit_details", "continue_draft"]);

    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });
});
