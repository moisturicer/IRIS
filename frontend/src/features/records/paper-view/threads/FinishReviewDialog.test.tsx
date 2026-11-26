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
import type { DecisionFlags, RecordDetail, ReviewComment, ReviewVerdict } from "@/types/records";

import { FinishReviewDialog } from "./FinishReviewDialog";
import { comment } from "./threadFixtures";
import { groupThreads } from "./threadModel";

const finishReview = vi.fn();
const documentRequests = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: {
    finishReview: (id: number, body: unknown) => finishReview(id, body),
    documentRequests: (id: number) => documentRequests(id),
  },
}));

beforeEach(() => {
  finishReview.mockReset().mockResolvedValue({ data: {} });
  documentRequests.mockReset().mockResolvedValue({ data: [] });
});

/** A document request this reviewer drafted in the Documents tab (ADR-022 Amendment 9). */
function drafted(id: number, labels: string[]) {
  return {
    id, party: "itso", label: "ITSO", state: "draft", state_label: "Draft", message: "Please.",
    requested_by: "Ivy", created_at: "2026-11-24T02:00:00Z", closed_at: null, can_manage: true,
    items: labels.map((label, i) => ({
      id: id * 10 + i, slot: null, label, state: "missing", state_label: "Missing", upload: null,
      uploaded_at: null, rejection_reason: null, decided_at: null,
    })),
  };
}

const DECISION: DecisionFlags = {
  party: "rdco", outcomes: ["publish", "keep_unlisted", "reject"], blocked: null,
  blocked_outcomes: {}, reason_required: false,
  closes: { assignments: [], document_requests: 0, threads: [] }, token: "t1", author_hints: [],
};

function record(over: Partial<RecordDetail> = {}): RecordDetail {
  return {
    id: 9,
    can_request_document: [],
    revision: { party: "itso", label: "ITSO", blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
    routing: { send_to_rdco: false, send_to_rdco_blocked: null, route_as: null, targets: [] },
    office_review: { party: "itso", label: "ITSO", blocked: null, clear_blocked: null, assignment: 3 },
    decision: DECISION,
    ...over,
  } as unknown as RecordDetail;
}

function open(caps: Capability[], drafts: ReviewComment[] = [], rec = record(), initialVerdict?: ReviewVerdict) {
  const onDone = vi.fn();
  const onSendToRdco = vi.fn();
  const view = renderScreen(
    <FinishReviewDialog record={rec} can={new Set<Capability>(["finish_review", ...caps])} drafts={drafts}
      initialVerdict={initialVerdict} onClose={vi.fn()} onDone={onDone} onSendToRdco={onSendToRdco} />,
  );
  return { ...view, onDone, onSendToRdco };
}

describe("Finish review", () => {
  it("sends the drafts and the verdict in one act", async () => {
    const user = userEvent.setup();
    const { onDone } = open(["request_revision", "office_review"], [comment({ is_draft: true, severity: "must_fix" })]);
    expect(screen.getByText("1 draft comment, 1 Must fix, will be sent with it.")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /Request changes/ }));
    const send = screen.getByRole("button", { name: "Request changes" });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Summary/ }), "The methods need the calibration detail.");
    await user.click(send);

    expect(finishReview).toHaveBeenCalledTimes(1);
    expect(finishReview).toHaveBeenCalledWith(9, {
      verdict: "request_revision", summary: "The methods need the calibration detail.",
    });
    expect(onDone).toHaveBeenCalledWith("Changes requested. The authors have been notified.");
  });

  // ADR-022 Amendment 9 (IR-1325): documents are asked for in the Documents tab
  // and wait as drafts; Request changes and Comment only send them, and no
  // other verdict goes while any wait.
  it("asks for no documents itself: Request changes is a new version, nothing to tick", async () => {
    const user = userEvent.setup();
    open(["request_revision", "office_review"], [], record({ can_request_document: ["itso"] } as Partial<RecordDetail>));

    await user.click(screen.getByRole("radio", { name: /Request changes/ }));

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Documents you need" })).not.toBeInTheDocument();
  });

  it("names the drafted document requests it sends, and sends them with Request changes", async () => {
    const user = userEvent.setup();
    documentRequests.mockResolvedValue({ data: [drafted(1, ["Ethics Clearance", "Consent Paper"])] });
    const { container } = open(["request_revision", "office_review"], [], record({ can_request_document: ["itso"] } as Partial<RecordDetail>));

    expect(await screen.findByText("2 document requests will be sent with it: Ethics Clearance, Consent Paper.")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Request changes/ }));
    await user.type(screen.getByRole("textbox", { name: /Summary/ }), "Revise the methods.");
    await expectNoBlockingA11yViolations(container);
    await user.click(screen.getByRole("button", { name: "Request changes" }));

    expect(finishReview).toHaveBeenCalledWith(9, { verdict: "request_revision", summary: "Revise the methods." });
  });

  it("holds every other verdict while drafted requests wait, saying how to free it", async () => {
    documentRequests.mockResolvedValue({ data: [drafted(1, ["Ethics Clearance"])] });
    open(["request_revision", "office_review"], [], record({ can_request_document: ["itso"] } as Partial<RecordDetail>), "cleared");

    const clear = screen.getByRole("radio", { name: /Clear for ITSO/ });
    await vi.waitFor(() => expect(clear).toBeDisabled());
    expect(clear).toHaveAccessibleDescription(
      "Unavailable: You have 1 document request waiting. Remove it in the Documents tab first, or choose Request changes or Comment only.",
    );
    // It falls back to Comment only, which sends the request on its own.
    expect(screen.getByRole("radio", { name: "Comment only" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Send review" })).toBeEnabled();
  });

  it("offers only the granted verdicts, and says why a held one is unavailable", () => {
    open(["office_review"], [], record({
      office_review: { party: "itso", label: "ITSO", blocked: null, clear_blocked: "ITSO has 1 open Must fix thread.", assignment: 3 },
    } as Partial<RecordDetail>));
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    // Named by the verdict alone; what it does is its description (found by hand on #595).
    expect(radios[0]).toHaveAccessibleName("Comment only");
    expect(radios[1]).toHaveAccessibleName("Clear for ITSO");
    expect(radios[2]).toHaveAccessibleName("Record a finding");
    expect(radios[2]).toHaveAccessibleDescription("A reasoned concern. It goes to RDCO, which decides.");
    const clear = screen.getByRole("radio", { name: /Clear for ITSO/ });
    expect(clear).toBeDisabled();
    expect(clear).toHaveAccessibleDescription("Unavailable: ITSO has 1 open Must fix thread.");
    expect(screen.queryByRole("radio", { name: /Reject/ })).toBeNull();
  });

  it("won't approve while sending the reviewer's own Must fix draft", () => {
    open(["office_review"], [comment({ is_draft: true, severity: "must_fix" })]);
    expect(screen.getByRole("radio", { name: /Clear for ITSO/ })).toHaveAccessibleDescription(/Change it to Suggestion/);
    // Changed deliberately by IR-1226 (2026-11-19): a finding ends the seat as
    // Clear does, so it waits on the reviewer's own Must fix too.
    const finding = screen.getByRole("radio", { name: /Record a finding/ });
    expect(finding).toBeDisabled();
    expect(finding).toHaveAccessibleDescription(/can't record a finding while sending a Must fix/);
  });

  it("holds Record a finding while the office has an open Must fix (IR-1226)", () => {
    const why = "ITSO has 1 open Must fix thread. Resolve each one, or change it to Suggestion, before recording a finding.";
    open(["office_review"], [], record({
      office_review: { party: "itso", label: "ITSO", blocked: null, clear_blocked: why, finding_blocked: why, assignment: 3 },
    } as Partial<RecordDetail>));
    const finding = screen.getByRole("radio", { name: /Record a finding/ });
    expect(finding).toBeDisabled();
    expect(finding).toHaveAccessibleDescription(`Unavailable: ${why}`);
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
  it("opens on the verdict a footer button named (IR-1139)", () => {
    open(["accept_publish", "keep_unlisted", "reject"], [], record(), "keep_unlisted");

    expect(screen.getByRole("group", { name: "Your decision" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Keep unlisted/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Keep unlisted" })).toBeInTheDocument();
  });

  it("falls back to Comment only when the named verdict is held (IR-1139)", () => {
    const held = record({ decision: { ...DECISION, blocked_outcomes: { publish: "Under embargo. Release the embargo, then publish." } } });
    open(["accept_publish", "keep_unlisted"], [], held, "publish");

    expect(screen.getByRole("radio", { name: /Accept & publish/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Comment only/ })).toBeChecked();
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
          // A thread on a supporting document is named by it (IR-1204).
          { id: 3, party: "ierc", label: "IERC", severity: "must_fix", anchored: false, document: "Consent form, v1" },
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
    expect(closes).toHaveTextContent("3 open threads, 2 Must fix:");
    expect(closes).toHaveTextContent("ITSO, on a passage");
    expect(closes).toHaveTextContent("IERC, on Consent form, v1");
    expect(closes).toHaveTextContent("Your summary is the reason each open Must fix thread closes with.");

    const send = screen.getByRole("button", { name: "Keep unlisted" });
    expect(send).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: /Summary \(required/ }), "Ahead of a patent filing.");
    await user.click(send);
    expect(finishReview).toHaveBeenCalledWith(9, { verdict: "keep_unlisted", summary: "Ahead of a patent filing.", token: "t1" });
  });

  it("names each closing Must fix by its pin and quote when the tab has it", async () => {
    const user = userEvent.setup();
    const sent = groupThreads([comment({ id: 1, party: "itso", party_label: "ITSO", severity: "must_fix",
      anchor: { version: 1, page: 2, quote: "a sample of 40" } })]).sent;
    renderScreen(
      <FinishReviewDialog record={withThreads} can={new Set<Capability>(["finish_review", "reject"])} drafts={[]}
        sent={sent} onClose={vi.fn()} onDone={vi.fn()} onSendToRdco={vi.fn()} />,
    );
    await user.click(screen.getByRole("radio", { name: /Reject/ }));
    expect(screen.getByRole("region", { name: "What this Decision closes" }))
      .toHaveTextContent("Thread 1, ITSO: “a sample of 40”");
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
