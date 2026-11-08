/**
 * RDCO's controls on a paper in review (ADR-051 decision 10, IR-798).
 *
 * The card follows the server's offers alone (`replace_adviser`, `add_owner`,
 * `withdraw_paper`); each act asks first, in a dialog that says who is told and
 * what ends; a refusal shows the server's words and reloads the record. Every
 * query goes through the accessible tree.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { AdviserOption } from "@/types/auth";
import type { RecordDetail } from "@/types/records";

import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";

import { RdcoPaperControls } from "./RdcoPaperControls";

vi.mock("@/api/records", () => ({
  recordsApi: { replaceAdviser: vi.fn(), addOwner: vi.fn(), rdcoWithdraw: vi.fn() },
}));
vi.mock("@/api/accounts", () => ({
  accountsApi: { listAdvisers: vi.fn() },
}));

const ALL: Capability[] = ["replace_adviser", "add_owner", "withdraw_paper"];

function adviser(id: number, first: string, last: string): AdviserOption {
  return {
    id, first_name: first, middle_initial: "", last_name: last,
    email: `${first.toLowerCase()}@cit.edu`, college_name: "CCS", department_name: "Computer Science",
  } as AdviserOption;
}

const CURRENT = adviser(5, "Ramon", "Cruz");
const NEXT = adviser(6, "Liza", "Tan");
const OWNER_ADVISER = adviser(7, "Owen", "Reyes");

function paper(capabilities: Capability[] = ALL) {
  return {
    id: 7,
    capabilities,
    adviser: CURRENT.id,
    adviser_name: "Ramon Cruz",
    owners: [{ id: 1, user: OWNER_ADVISER.id, email: "owen@cit.edu", full_name: "Owen Reyes", is_primary: true }],
  } as unknown as RecordDetail;
}

function refusal(data: unknown, status = 400) {
  return Object.assign(new Error("refused"), { response: { status, data } });
}

function renderCard(record: RecordDetail = paper()) {
  const onChanged = vi.fn();
  const onWithdrawn = vi.fn();
  const view = renderScreen(
    <RdcoPaperControls record={record} onChanged={onChanged} onWithdrawn={onWithdrawn} />,
  );
  return { ...view, onChanged, onWithdrawn };
}

beforeEach(() => {
  vi.mocked(recordsApi.replaceAdviser).mockReset();
  vi.mocked(recordsApi.addOwner).mockReset();
  vi.mocked(recordsApi.rdcoWithdraw).mockReset();
  vi.mocked(accountsApi.listAdvisers).mockReset();
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue({
    data: { count: 3, next: null, previous: null, results: [CURRENT, NEXT, OWNER_ADVISER] },
  } as never);
});

describe("what it offers", () => {
  it("is absent when the server offers none of the three acts", () => {
    renderCard(paper([]));
    expect(screen.queryByRole("region", { name: "RDCO controls" })).not.toBeInTheDocument();
  });

  it("offers each act only when its capability is there", () => {
    renderCard(paper(["add_owner", "withdraw_paper"]));
    const card = screen.getByRole("region", { name: "RDCO controls" });
    expect(within(card).queryByRole("button", { name: "Replace Adviser" })).not.toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Add owner" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Withdraw paper" })).toBeInTheDocument();
  });

  it("passes axe with all three offered", async () => {
    const { container } = renderCard();
    expect(screen.getAllByRole("button")).toHaveLength(3);
    await expectNoBlockingA11yViolations(container);
  });
});

describe("replacing the Adviser", () => {
  it("says who is told and what ends, then names the chosen Adviser", async () => {
    vi.mocked(recordsApi.replaceAdviser).mockResolvedValue({
      data: { adviser: { id: NEXT.id, name: "Liza Tan" }, seat: 40 },
    } as never);
    const { onChanged } = renderCard();

    await userEvent.click(screen.getByRole("button", { name: "Replace Adviser" }));
    const dialog = screen.getByRole("dialog", { name: "Replace this paper's Adviser?" });
    expect(dialog).toHaveTextContent(/Ramon Cruz's Adviser review ends/);
    const told = within(dialog).getByRole("list", { name: "Who is told" });
    expect(within(told).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Ramon Cruz, that they were replaced and their review is closed.",
      "The new Adviser, that the review is waiting for them.",
    ]);

    const picker = await within(dialog).findByRole("combobox", { name: "New Adviser" });
    await userEvent.click(picker);
    const options = within(screen.getByRole("listbox", { name: "Advisers" })).getAllByRole("option");
    // The current Adviser and an owner can't be chosen (IR-260), so only Liza is offered.
    expect(options.map((o) => o.textContent)).toEqual([expect.stringContaining("Liza Tan")]);
    await expectNoBlockingA11yViolations(document.body);

    await userEvent.click(options[0]);
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Reason (optional)" }), "On leave.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Replace Adviser" }));

    expect(recordsApi.replaceAdviser).toHaveBeenCalledWith(7, NEXT.id, "On leave.");
    expect(await screen.findByRole("status")).toHaveTextContent("Liza Tan is now the Adviser. Both Advisers have been told.");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("asks for a choice before sending anything", async () => {
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Replace Adviser" }));
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByRole("combobox", { name: "New Adviser" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Replace Adviser" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Choose the new Adviser.");
    expect(recordsApi.replaceAdviser).not.toHaveBeenCalled();
  });

  it("shows the server's refusal when the review moved on first", async () => {
    vi.mocked(recordsApi.replaceAdviser).mockRejectedValue(
      refusal({ detail: "No Adviser review is open on this paper." }),
    );
    const { onChanged } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Replace Adviser" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(await within(dialog).findByRole("combobox", { name: "New Adviser" }));
    await userEvent.click(within(screen.getByRole("listbox")).getByRole("option"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Replace Adviser" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No Adviser review is open on this paper.");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("says so when the list of advisers can't be loaded", async () => {
    vi.mocked(accountsApi.listAdvisers).mockRejectedValue(new Error("offline"));
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Replace Adviser" }));
    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent(
      "The list of advisers couldn't be loaded.",
    );
  });
});

describe("adding an owner", () => {
  it("says who is told and that the Contact person stays, then sends the address", async () => {
    vi.mocked(recordsApi.addOwner).mockResolvedValue({ data: { owners: [] } } as never);
    const { onChanged } = renderCard();

    await userEvent.click(screen.getByRole("button", { name: "Add owner" }));
    const dialog = screen.getByRole("dialog", { name: "Add an owner to this paper?" });
    expect(dialog).toHaveTextContent(/The Contact person stays the same/);
    const told = within(dialog).getByRole("list", { name: "Who is told" });
    expect(within(told).getAllByRole("listitem")).toHaveLength(2);
    await expectNoBlockingA11yViolations(document.body);

    await userEvent.type(within(dialog).getByRole("textbox", { name: "Email address" }), "  ana@cit.edu ");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add owner" }));

    expect(recordsApi.addOwner).toHaveBeenCalledWith(7, "ana@cit.edu");
    expect(await screen.findByRole("status")).toHaveTextContent("Owner added. The owners have been told.");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("shows the server's field refusal in the dialog", async () => {
    vi.mocked(recordsApi.addOwner).mockRejectedValue(
      refusal({ email: ["Use an existing, active, verified account."] }),
    );
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Add owner" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Email address" }), "who@cit.edu");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add owner" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Use an existing, active, verified account.");
    expect(within(dialog).getByRole("textbox", { name: "Email address" })).toHaveAttribute("aria-invalid", "true");
  });
});

describe("withdrawing the paper", () => {
  it("states that the review stops and who is told, and requires a reason", async () => {
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Withdraw paper" }));
    const dialog = screen.getByRole("dialog", { name: "Withdraw this paper?" });
    expect(dialog).toHaveTextContent("The paper's review stops. It is deleted and can't be restored.");
    const told = within(dialog).getByRole("list", { name: "Who is told" });
    expect(within(told).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Every owner, in IRIS and by email, with your reason.",
      "Each reviewer whose review closes, in IRIS.",
    ]);
    const reason = within(dialog).getByRole("textbox", { name: "Reason" });
    expect(reason).toBeRequired();
    await expectNoBlockingA11yViolations(document.body);

    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw paper" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Give a reason for withdrawing the paper.");
    expect(recordsApi.rdcoWithdraw).not.toHaveBeenCalled();
  });

  it("sends the reason and hands over once the paper is gone", async () => {
    vi.mocked(recordsApi.rdcoWithdraw).mockResolvedValue({ data: { id: 7, withdrawn: true } } as never);
    const { onWithdrawn, onChanged } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Withdraw paper" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Reason" }), "Owner left CIT-U.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw paper" }));

    expect(recordsApi.rdcoWithdraw).toHaveBeenCalledWith(7, "Owner left CIT-U.");
    await waitFor(() => expect(onWithdrawn).toHaveBeenCalledTimes(1));
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("keeps a stale refusal on the card after the reload takes the offer away", async () => {
    vi.mocked(recordsApi.rdcoWithdraw).mockRejectedValue(refusal({ detail: "This paper is not in review." }));
    const { onChanged, rerender } = renderCard();
    await userEvent.click(screen.getByRole("button", { name: "Withdraw paper" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Reason" }), "Duplicate.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw paper" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This paper is not in review.");
    expect(onChanged).toHaveBeenCalledTimes(1);

    // The reload: the paper left review, so nothing is offered any more.
    rerender(<RdcoPaperControls record={paper([])} onChanged={onChanged} onWithdrawn={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "RDCO controls" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("This paper is not in review.");
  });
});

/*
 * jsdom loads no stylesheet and computes no layout, so a 360 px render is the
 * same tree as any other (see reflow360.test.tsx). What would push a control
 * off a phone is a row that cannot wrap or a clamp on the words, so that is
 * what is asserted; the rendered check is the browser's.
 */
describe("at 360 px", () => {
  const unwrapped = (el: Element) => !!el.closest(".truncate, .whitespace-nowrap, [class*='line-clamp']");

  it("wraps the card's buttons and clips none of its words", () => {
    renderCard();
    const card = screen.getByRole("region", { name: "RDCO controls" });
    const row = within(card).getByRole("button", { name: "Add owner" }).parentElement!;
    expect(row.className).toMatch(/\bflex-wrap\b/);
    for (const button of within(card).getAllByRole("button")) expect(unwrapped(button)).toBe(false);
  });

  it.each([
    ["Replace Adviser", "Replace this paper's Adviser?"],
    ["Add owner", "Add an owner to this paper?"],
    ["Withdraw paper", "Withdraw this paper?"],
  ])("fits the %s dialog to the screen and wraps its buttons", async (opener, title) => {
    renderCard();
    await userEvent.click(screen.getByRole("button", { name: opener }));
    const dialog = screen.getByRole("dialog", { name: title });
    expect(dialog.className).toMatch(/\bw-full\b/);
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    expect(cancel.parentElement!.className).toMatch(/\bflex-wrap\b/);
    for (const item of within(dialog).getAllByRole("listitem")) expect(unwrapped(item)).toBe(false);
  });
});
