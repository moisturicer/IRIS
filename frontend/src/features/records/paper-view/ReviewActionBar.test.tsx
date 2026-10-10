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
    routeOptions: vi.fn(() => new Promise(() => {})),
    acceptAndRoute: vi.fn(),
    route: vi.fn(),
    requestRevision: vi.fn(() => Promise.resolve({ data: {} })),
    withdrawRevisionRequest: vi.fn(() => Promise.resolve({ data: {} })),
  },
}));

const record = {
  id: 7,
  title: "Groundwater Recharge Mapping in Metro Cebu",
  can_request_document: ["ierc"],
  current_holders: [{ party: "ierc", label: "IERC", opened_at: null, opened_by: null }],
  revision: { party: "ierc", label: "IERC", blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: {
    party: "rdco", outcomes: ["publish", "keep_unlisted", "reject"], blocked: null,
    closes: { assignments: [], document_requests: 0 }, token: "t", author_hints: [],
  },
  versions: [],
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
  capability: "accept_publish",
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
  extra: { onChanged?: () => void } = {},
) {
  return renderScreen(
    <ReviewActionBar
      record={record}
      can={new Set(granted)}
      actions={actions}
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
    renderBar(["route", "accept_publish"], [acceptAndPublish, route]);

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

  it("states a reason two actions share once, and both name it (IR-269)", async () => {
    const shared = () => "Open the review first.";
    const clear: ReviewAction = { ...route, capability: "office_review", label: "Clear…", blockedReason: shared };
    const finding: ReviewAction = { ...route, capability: "office_review", label: "Record finding…", blockedReason: shared };
    const { container } = renderBar(["office_review"], [clear, finding]);

    expect(buttonNames()).toEqual(["Clear…", "Record finding…"]);
    expect(screen.getAllByText("Open the review first.")).toHaveLength(1);
    for (const name of ["Clear…", "Record finding…"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toBeDisabled();
      expect(button).toHaveAccessibleDescription("Open the review first.");
    }
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
    renderBar(["accept_publish"], [acceptAndPublish], { onChanged });

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
    renderBar(["accept_publish"], [acceptAndPublish]);

    await userEvent.click(screen.getByRole("button", { name: "Accept & publish" }));
    const confirm = screen.getByRole("dialog", { name: "Accept and publish this record?" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Accept & publish" }));

    expect(await within(confirm).findByRole("alert")).toHaveTextContent(
      "This record is no longer yours to decide.",
    );
  });

  it("moves between its controls with the arrow keys", async () => {
    renderBar(["route", "accept_publish"], [route, acceptAndPublish]);

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

  // IR-261: the Adviser's filled action is Accept & route; an office keeps
  // Request documents filled, with Route to office beside it.
  it("orders the routing actions so each viewer's primary is the right one", async () => {
    const { unmount } = renderBar(["accept_route", "request_document"]);
    let bar = screen.getByRole("toolbar", { name: "Review actions" });
    expect(within(bar).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual([
      "Accept & route…",
      "Request documents",
    ]);
    unmount();

    renderBar(["request_document", "route"]);
    bar = screen.getByRole("toolbar", { name: "Review actions" });
    expect(within(bar).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual([
      "Request documents",
      "Route to office…",
    ]);

    await userEvent.click(within(bar).getByRole("button", { name: "Route to office…" }));
    expect(screen.getByRole("dialog", { name: "Route to office" })).toBeInTheDocument();
  });

  // IR-272: accepting is a decision, so an open revision request disables it
  // and says why; the party that asked is offered the withdrawal, last.
  it("holds Accept & route while a revision is requested, and lets the asking party withdraw", async () => {
    const onChanged = vi.fn();
    const asked = {
      ...record,
      revision: {
        party: "ierc", label: "IERC", blocked: null, withdrawable: 5,
        decision_blocked: "Waiting on the author: IERC asked for a revision.",
        open: [],
      },
    } as unknown as RecordDetail;
    renderScreen(
      <ReviewActionBar
        record={asked}
        can={new Set<Capability>(["accept_route", "withdraw_revision"])}
        onChanged={onChanged}
      />,
    );

    const accept = screen.getByRole("button", { name: "Accept & route…" });
    expect(accept).toBeDisabled();
    expect(accept).toHaveAccessibleDescription("Waiting on the author: IERC asked for a revision.");
    expect(buttonNames()).toEqual(["Accept & route…", "Withdraw revision request"]);

    await userEvent.click(screen.getByRole("button", { name: "Withdraw revision request" }));
    const confirm = screen.getByRole("dialog", { name: "Withdraw the revision request?" });
    await userEvent.click(within(confirm).getByRole("button", { name: "Withdraw request" }));

    expect(recordsApi.withdrawRevisionRequest).toHaveBeenCalledWith(7, 5);
    expect(await screen.findByRole("status")).toHaveTextContent("Revision request withdrawn.");
    expect(onChanged).toHaveBeenCalledOnce();
  });

  // IR-270: a decider's primary is Accept & publish, and Reject is the last
  // of the dialogs; an open revision request holds all three Decisions.
  it("orders the Decisions so publishing is primary and rejecting comes last", async () => {
    const { unmount } = renderBar(["reject", "request_document", "accept_route", "request_revision", "accept_publish"]);
    expect(buttonNames()).toEqual([
      "Accept & publish…", "Accept & route…", "Request Revision…", "Request documents", "Reject…",
    ]);
    unmount();

    renderBar(["reject", "route", "keep_unlisted", "request_document", "accept_publish"]);
    expect(buttonNames()).toEqual([
      "Accept & publish…", "Keep unlisted…", "Request documents", "Route to office…", "Reject…",
    ]);
    await userEvent.click(screen.getByRole("button", { name: "Keep unlisted…" }));
    expect(screen.getByRole("dialog", { name: "Accept and keep unlisted?" })).toBeInTheDocument();
  });

  // IR-271: a Proposal's Adviser has Accept as primary, Reject last.
  it("orders a Proposal's Decisions so accepting is primary and rejecting comes last", () => {
    renderBar(["reject", "request_document", "request_revision", "accept_proposal"]);
    expect(buttonNames()).toEqual([
      "Accept…", "Request Revision…", "Request documents", "Reject…",
    ]);
  });

  it("holds every Decision while the server says it is blocked", () => {
    const blocked = {
      ...record,
      decision: {
        party: "adviser", outcomes: ["publish", "reject"], token: "t", closes: null, author_hints: [],
        blocked: "Waiting on the author: IERC asked for a revision.",
      },
    } as unknown as RecordDetail;
    renderScreen(
      <ReviewActionBar
        record={blocked}
        can={new Set<Capability>(["accept_publish", "reject"])}
        onChanged={() => {}}
      />,
    );

    for (const name of ["Accept & publish…", "Reject…"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toBeDisabled();
      expect(button).toHaveAccessibleDescription("Waiting on the author: IERC asked for a revision.");
    }
  });

  it("offers Request Revision under `request_revision`, through its own dialog", async () => {
    renderBar(["request_revision"]);

    await userEvent.click(screen.getByRole("button", { name: "Request Revision…" }));
    const dialog = screen.getByRole("dialog", { name: "Request Revision" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: "What needs revising?" }), "Cite the 2019 survey.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Request Revision" }));

    expect(recordsApi.requestRevision).toHaveBeenCalledWith(7, { reason: "Cite the 2019 survey." });
    expect(await screen.findByRole("status")).toHaveTextContent("Revision requested. The owner has been notified.");
  });

  it("offers nothing a viewer with no review capability was not granted", () => {
    renderBar(["cite", "edit_details", "continue_draft"]);

    expect(screen.queryByRole("toolbar")).not.toBeInTheDocument();
  });
});
