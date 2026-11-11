/**
 * Paper View's Contact person card (ADR-051 decision 27, IR-803).
 *
 * Any owner names another owner the Contact person, who gets the review emails.
 * The card comes from `capabilities` and compares no role names. A failed save
 * shows the server's own words and goes back to the choice before it. Every
 * query goes through the accessible tree.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail, RecordOwner } from "@/types/records";

import { recordsApi } from "@/api/records";

import { ContactPersonCard } from "./ContactPersonCard";

vi.mock("@/api/records", () => ({
  recordsApi: { changeContactPerson: vi.fn() },
}));

function owner(user: number, fullName: string, isPrimary = false): RecordOwner {
  return { id: user * 10, user, email: `${fullName.split(" ")[0].toLowerCase()}@cit.edu`, full_name: fullName, is_primary: isPrimary };
}

const ANA = owner(1, "Ana Reyes", true);
const BEN = owner(2, "Ben Cruz");
const CARLA = owner(3, "Carla Lim");

function paper(owners: RecordOwner[], capabilities: Capability[] = ["change_contact_person"]) {
  return { id: 7, owners, capabilities } as unknown as RecordDetail;
}

function renderCard(record: RecordDetail) {
  const onChanged = vi.fn();
  const view = renderScreen(<ContactPersonCard record={record} onChanged={onChanged} />);
  return { ...view, onChanged };
}

beforeEach(() => {
  vi.mocked(recordsApi.changeContactPerson).mockReset();
});

describe("what an owner sees", () => {
  it("lists every owner in one dropdown, with the Contact person selected", () => {
    renderCard(paper([ANA, BEN, CARLA]));

    const card = screen.getByRole("region", { name: "Contact person" });
    const select = within(card).getByRole("combobox", { name: "Contact person" });
    expect(select).toHaveDisplayValue("Ana Reyes");
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Ana Reyes", "Ben Cruz", "Carla Lim",
    ]);
  });

  it("says in one line what the Contact person is for", () => {
    renderCard(paper([ANA, BEN]));
    const select = screen.getByRole("combobox", { name: "Contact person" });
    expect(select).toHaveAccessibleDescription("This person gets the review emails.");
  });

  it("shows the only owner by name, with no dropdown, on a paper with one owner", () => {
    renderCard(paper([ANA]));

    const card = screen.getByRole("region", { name: "Contact person" });
    expect(within(card).getByText("Ana Reyes")).toBeInTheDocument();
    expect(within(card).getByText("This person gets the review emails.")).toBeInTheDocument();
    expect(within(card).queryByRole("combobox")).not.toBeInTheDocument();
    expect(within(card).queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows an owner's email when they gave no name", () => {
    renderCard(paper([{ ...ANA, full_name: " " }, BEN]));
    expect(screen.getByRole("combobox", { name: "Contact person" })).toHaveDisplayValue("ana@cit.edu");
  });

  it("is not there for anyone the server doesn't offer it to", () => {
    renderCard(paper([ANA, BEN], ["cite", "comment_review"]));
    expect(screen.queryByRole("region", { name: "Contact person" })).not.toBeInTheDocument();
  });
});

function refusal(data: unknown, status = 400) {
  return Object.assign(new Error("refused"), { response: { status, data } });
}

describe("naming another owner", () => {
  const SAVE = { name: "Make Contact person" };

  it("offers the save only once a different owner is chosen", async () => {
    const user = userEvent.setup();
    renderCard(paper([ANA, BEN]));

    expect(screen.getByRole("button", SAVE)).toBeDisabled();
    await user.selectOptions(screen.getByRole("combobox", { name: "Contact person" }), "Ben Cruz");
    expect(screen.getByRole("button", SAVE)).toBeEnabled();
    await user.selectOptions(screen.getByRole("combobox", { name: "Contact person" }), "Ana Reyes");
    expect(screen.getByRole("button", SAVE)).toBeDisabled();
    expect(recordsApi.changeContactPerson).not.toHaveBeenCalled();
  });

  it("saves the chosen owner, says so, and reads the paper again", async () => {
    vi.mocked(recordsApi.changeContactPerson).mockResolvedValue({ data: { owners: [] } } as never);
    const user = userEvent.setup();
    const { onChanged } = renderCard(paper([ANA, BEN, CARLA]));

    await user.selectOptions(screen.getByRole("combobox", { name: "Contact person" }), "Carla Lim");
    await user.click(screen.getByRole("button", SAVE));

    expect(recordsApi.changeContactPerson).toHaveBeenCalledExactlyOnceWith(7, 3);
    expect(await screen.findByRole("status")).toHaveTextContent("Carla Lim is now the Contact person.");
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("shows the server's refusal and goes back to the choice before it", async () => {
    vi.mocked(recordsApi.changeContactPerson).mockRejectedValue(
      refusal({ owner: ["That owner's account is closed, so they can't be the Contact person."] }),
    );
    const user = userEvent.setup();
    renderCard(paper([ANA, BEN]));

    const select = screen.getByRole("combobox", { name: "Contact person" });
    await user.selectOptions(select, "Ben Cruz");
    await user.click(screen.getByRole("button", SAVE));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That owner's account is closed, so they can't be the Contact person.",
    );
    expect(select).toHaveDisplayValue("Ana Reyes");
    expect(screen.getByRole("button", SAVE)).toBeDisabled();
  });

  it("shows a refusal's detail when it names no field", async () => {
    vi.mocked(recordsApi.changeContactPerson).mockRejectedValue(
      refusal({ detail: "You do not have permission to perform this action." }, 403),
    );
    const user = userEvent.setup();
    renderCard(paper([ANA, BEN]));

    await user.selectOptions(screen.getByRole("combobox", { name: "Contact person" }), "Ben Cruz");
    await user.click(screen.getByRole("button", SAVE));

    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission to perform this action.");
  });
});

describe("accessibility", () => {
  it("has no serious or critical axe findings with the dropdown", async () => {
    const { container } = renderCard(paper([ANA, BEN]));
    await expectNoBlockingA11yViolations(container);
  });

  it("has none with one owner", async () => {
    const { container } = renderCard(paper([ANA]));
    await expectNoBlockingA11yViolations(container);
  });

  it("has none once a save is refused", async () => {
    vi.mocked(recordsApi.changeContactPerson).mockRejectedValue(refusal({ owner: ["That owner is already the Contact person."] }));
    const user = userEvent.setup();
    const { container } = renderCard(paper([ANA, BEN]));
    await user.selectOptions(screen.getByRole("combobox", { name: "Contact person" }), "Ben Cruz");
    await user.click(screen.getByRole("button", { name: "Make Contact person" }));
    await screen.findByRole("alert");
    await expectNoBlockingA11yViolations(container);
  });
});

/*
 * jsdom computes no layout, so a 360 px render is the same tree as any other
 * (see reflow360.test.tsx): a native select is as wide as its longest option
 * unless it may shrink, and a long name must wrap rather than widen the rail.
 * These pin those causes; the Core journeys' browser check measures the page.
 */
describe("at 360 px", () => {
  const LONG = "Maria-Concepcion Villanueva-Santos-Hernandez de la Cruz-Abellana";

  it("lets the dropdown shrink below its longest owner's name", () => {
    renderCard(paper([ANA, owner(4, LONG)]));
    const select = screen.getByRole("combobox", { name: "Contact person" });
    expect(select.className).toMatch(/\bmin-w-0\b/);
    expect(select.className).toMatch(/\bmax-w-full\b/);
  });

  it("wraps a long name, and clips no control", () => {
    renderCard(paper([owner(4, LONG, true)]));
    expect(screen.getByText(LONG).className).toContain("[overflow-wrap:anywhere]");
    expect(screen.getByRole("region", { name: "Contact person" }).querySelector(".truncate, .whitespace-nowrap")).toBeNull();
  });
});
