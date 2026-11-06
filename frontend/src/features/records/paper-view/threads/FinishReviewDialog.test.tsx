/**
 * *Finish review* (ADR-032 §7, IR-875): the drafts and the verdict go in one
 * act, the verdicts are what the capabilities grant, a held verdict says why,
 * and a Decision with open Must fix threads lists them and needs a reason.
 * Queries go through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Capability } from "@/features/records/capabilities";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { DecisionFlags, RecordDetail, ReviewComment } from "@/types/records";

import { FinishReviewDialog } from "./FinishReviewDialog";
import { comment } from "./threadFixtures";

const finishReview = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: { finishReview: (id: number, body: unknown) => finishReview(id, body) },
}));

beforeEach(() => {
  finishReview.mockReset().mockResolvedValue({ data: {} });
});

const DECISION: DecisionFlags = {
  party: "rdco", outcomes: ["publish", "keep_unlisted", "reject"], blocked: null,
  blocked_outcomes: {}, reason_required: false,
  closes: { assignments: [], document_requests: 0, threads: [] }, token: "t1", author_hints: [],
};

function record(over: Partial<RecordDetail> = {}): RecordDetail {
  return {
    id: 9,
    revision: { party: "itso", label: "ITSO", blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
    routing: { send_to_rdco: false, send_to_rdco_blocked: null, route_as: null, targets: [] },
    office_review: { party: "itso", label: "ITSO", blocked: null, clear_blocked: null, assignment: 3 },
    decision: DECISION,
    ...over,
  } as unknown as RecordDetail;
}

function open(caps: Capability[], drafts: ReviewComment[] = [], rec = record()) {
  const onDone = vi.fn();
  const onSendToRdco = vi.fn();
  const view = renderScreen(
    <FinishReviewDialog record={rec} can={new Set<Capability>(["finish_review", ...caps])} drafts={drafts}
      onClose={vi.fn()} onDone={onDone} onSendToRdco={onSendToRdco} />,
  );
  return { ...view, onDone, onSendToRdco };
}

describe("Finish review", () => {
  it("sends the drafts and the verdict in one act", async () => {
    const user = userEvent.setup();
    const { onDone } = open(["request_revision", "office_review"], [comment({ is_draft: true, severity: "must_fix" })]);
    expect(screen.getByText("1 draft comment, 1 Must fix, will be sent with it.")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /Request revision/ }));
    const send = screen.getByRole("button", { name: "Request revision" });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Summary/ }), "The methods need the calibration detail.");
    await user.click(send);

    expect(finishReview).toHaveBeenCalledTimes(1);
    expect(finishReview).toHaveBeenCalledWith(9, { verdict: "request_revision", summary: "The methods need the calibration detail." });
    expect(onDone).toHaveBeenCalledWith("Revision requested. The owner has been notified.");
  });

  it("offers only the granted verdicts, and says why a held one is unavailable", () => {
    open(["office_review"], [], record({
      office_review: { party: "itso", label: "ITSO", blocked: null, clear_blocked: "ITSO has 1 open Must fix thread.", assignment: 3 },
    } as Partial<RecordDetail>));
    const radios = screen.getAllByRole("radio").map((r) => r.closest("label")?.querySelector("span span")?.textContent);
    expect(radios).toEqual(["Comment only", "Clear for ITSO", "Record a finding"]);
    const clear = screen.getByRole("radio", { name: /Clear for ITSO/ });
    expect(clear).toBeDisabled();
    expect(clear).toHaveAccessibleDescription("Unavailable: ITSO has 1 open Must fix thread.");
    expect(screen.queryByRole("radio", { name: /Reject/ })).toBeNull();
  });

  it("won't approve while sending the reviewer's own Must fix draft", () => {
    open(["office_review"], [comment({ is_draft: true, severity: "must_fix" })]);
    expect(screen.getByRole("radio", { name: /Clear for ITSO/ })).toHaveAccessibleDescription(/Change it to Suggestion/);
    expect(screen.getByRole("radio", { name: /Record a finding/ })).toBeEnabled();
  });

  it("asks for a summary or a comment before Comment only", async () => {
    const user = userEvent.setup();
    open([]);
    const send = screen.getByRole("button", { name: "Send review" });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Summary/ }), "Reads well so far.");
    await user.click(send);
    expect(finishReview).toHaveBeenCalledWith(9, { verdict: "comment_only", summary: "Reads well so far." });
  });

  it("hands Accept & send to RDCO on to the routing step with the summary", async () => {
    const user = userEvent.setup();
    const { onSendToRdco } = open(["send_to_rdco"]);
    await user.click(screen.getByRole("radio", { name: /Accept & send to RDCO/ }));
    await user.type(screen.getByRole("textbox", { name: /Summary/ }), "Ready for RDCO.");
    await user.click(screen.getByRole("button", { name: "Choose offices…" }));
    expect(onSendToRdco).toHaveBeenCalledWith("Ready for RDCO.");
    expect(finishReview).not.toHaveBeenCalled();
  });
});

describe("a Decision with open threads", () => {
  const withThreads = record({
    decision: {
      ...DECISION, reason_required: true,
      closes: {
        assignments: [{ party: "ierc", label: "IERC", holders: ["Elena Reyes"] }], document_requests: 0,
        threads: [
          { id: 1, party: "itso", label: "ITSO", severity: "must_fix", anchored: true },
          { id: 2, party: "adviser", label: "Adviser", severity: "suggestion", anchored: false },
        ],
      },
    },
  } as Partial<RecordDetail>);

  it("lists the Must fix threads it closes and requires the reason", async () => {
    const user = userEvent.setup();
    open(["accept_publish", "keep_unlisted", "reject"], [], withThreads);
    await user.click(screen.getByRole("radio", { name: /Keep unlisted/ }));
    const closes = screen.getByRole("region", { name: "What this Decision closes" });
    expect(closes).toHaveTextContent("IERC's review in progress (Elena Reyes)");
    expect(closes).toHaveTextContent("2 open threads, 1 Must fix:");
    expect(closes).toHaveTextContent("ITSO, on a passage");
    expect(closes).toHaveTextContent("Your summary is the reason each open Must fix thread closes with.");

    const send = screen.getByRole("button", { name: "Keep unlisted" });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Summary \(required/ }), "Ahead of a patent filing.");
    await user.click(send);
    expect(finishReview).toHaveBeenCalledWith(9, { verdict: "keep_unlisted", summary: "Ahead of a patent filing.", token: "t1" });
  });

  it("takes the fresh token from a 409 and keeps the summary", async () => {
    finishReview.mockRejectedValueOnce({
      response: { status: 409, data: { detail: "The record changed while this was open.", decision: { ...DECISION, token: "t2" } } },
    });
    const user = userEvent.setup();
    open(["accept_publish"], [], withThreads);
    await user.click(screen.getByRole("radio", { name: /Accept & publish/ }));
    await user.type(screen.getByRole("textbox", { name: /Summary/ }), "Published.");
    await user.click(screen.getByRole("button", { name: "Accept & publish" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The record changed while this was open. Your summary and drafts are kept.");
    expect(screen.getByRole("textbox", { name: /Summary/ })).toHaveValue("Published.");
    await user.click(screen.getByRole("button", { name: "Accept & publish" }));
    expect(finishReview).toHaveBeenLastCalledWith(9, { verdict: "publish", summary: "Published.", token: "t2" });
  });
});

it("has no serious or critical accessibility violations", async () => {
  open(["request_revision", "office_review"], [comment({ is_draft: true })]);
  await expectNoBlockingA11yViolations(document.body);
});
