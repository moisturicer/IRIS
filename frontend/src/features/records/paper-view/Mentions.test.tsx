/**
 * @mentions (ADR-032 §7 Conveniences, IR-877): people are picked beside the
 * text from the list the server offers, never typed into it. Every query
 * goes through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { MentionedPerson } from "@/types/records";

import { MentionPicker, MentionedPeople } from "./Mentions";

const api = vi.hoisted(() => ({ reviewMentionable: vi.fn() }));
vi.mock("@/api/records", () => ({ recordsApi: api }));

const ana = { id: 4, name: "Ana Cruz" };
const ben = { id: 5, name: "Ben Lim" };

beforeEach(() => {
  api.reviewMentionable.mockReset();
  api.reviewMentionable.mockResolvedValue({ data: { results: [ana, ben] } });
});

function Picker({ initial = [] }: { initial?: MentionedPerson[] }) {
  const [people, setPeople] = useState(initial);
  return (
    <>
      <MentionPicker recordId={7} value={people} onChange={setPeople} />
      <output aria-label="Picked">{people.map((p) => p.id).join(",")}</output>
    </>
  );
}

const picked = () => screen.getByRole("status", { name: "Picked" }).textContent;

describe("picking whom to mention", () => {
  it("asks who may be mentioned only once the picker is opened", async () => {
    const user = userEvent.setup();
    const { container } = renderScreen(<Picker />);
    expect(api.reviewMentionable).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Mention someone" }));
    await user.click(await screen.findByRole("checkbox", { name: "Ben Lim" }));

    expect(api.reviewMentionable).toHaveBeenCalledWith(7);
    expect(picked()).toBe("5");
    expect(within(screen.getByRole("list", { name: "Mentioning" })).getByText("@Ben Lim")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("removes a name from the chip or the list", async () => {
    const user = userEvent.setup();
    renderScreen(<Picker initial={[ana, ben]} />);

    await user.click(screen.getByRole("button", { name: "Stop mentioning Ana Cruz" }));
    expect(picked()).toBe("5");

    await user.click(screen.getByRole("button", { name: "Mention someone" }));
    await user.click(await screen.findByRole("checkbox", { name: "Ben Lim" }));
    expect(picked()).toBe("");
  });

  it("says when nobody else takes part", async () => {
    api.reviewMentionable.mockResolvedValue({ data: { results: [] } });
    const user = userEvent.setup();
    renderScreen(<Picker />);

    await user.click(screen.getByRole("button", { name: "Mention someone" }));

    expect(await screen.findByText("Nobody else takes part in this review yet.")).toBeInTheDocument();
  });

  it("reads an answer of the wrong shape as a failure, not as nobody (F1)", async () => {
    api.reviewMentionable.mockResolvedValue({ data: { people: [ana] } });
    const user = userEvent.setup();
    renderScreen(<Picker />);

    await user.click(screen.getByRole("button", { name: "Mention someone" }));

    expect(await screen.findByText("The people you can mention couldn’t be loaded.")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});

describe("showing whom a comment mentions", () => {
  it("names them, and drops what isn't a person (F1)", () => {
    renderScreen(<MentionedPeople people={[ana, { id: "6", name: "Not one" }, ben]} />);

    expect(screen.getByText("Mentioned: Ana Cruz, Ben Lim")).toBeInTheDocument();
  });

  it("shows nothing for a comment that mentions nobody, or an older payload", () => {
    const { container } = renderScreen(<><MentionedPeople people={[]} /><MentionedPeople people={undefined} /></>);

    expect(container.textContent).toBe("");
  });
});
