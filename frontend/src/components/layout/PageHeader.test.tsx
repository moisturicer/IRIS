/**
 * The page head (IR-405). About twenty screens use it, so its contract stays
 * as it was: a title, an optional description and an actions area. What
 * changes is its look (spec §4.12): the title is set in the display face, and
 * the actions wrap under the title on a phone instead of squeezing it.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("is the page's one top-level heading, with its description and actions", async () => {
    const { container } = renderScreen(
      <PageHeader
        title="Users"
        description="Manage user accounts and roles."
        actions={<button type="button">Invite user</button>}
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Users" })).toBeInTheDocument();
    expect(screen.getByText("Manage user accounts and roles.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Invite user" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("renders a title alone", () => {
    renderScreen(<PageHeader title="Audit Log" />);

    expect(screen.getByRole("heading", { level: 1, name: "Audit Log" })).toBeInTheDocument();
  });
});
