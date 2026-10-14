/**
 * The comments section is drawn before it works (IR-569, spec §8): it must
 * read as closed, not as a working form.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import { CommentsSection } from "./CommentsSection";

describe("the comments section", () => {
  it("is a titled section with no comments", () => {
    renderScreen(<CommentsSection viewerName="Ana Reyes" />);

    expect(screen.getByRole("region", { name: /Comments/ })).toBeInTheDocument();
    expect(screen.getByText("No comments yet")).toBeInTheDocument();
  });

  it("says commenting is not open, and offers a field and Post that cannot be used", () => {
    renderScreen(<CommentsSection viewerName="Ana Reyes" />);

    expect(screen.getByText("Not open yet")).toBeInTheDocument();
    const field = screen.getByRole("textbox", { name: "Add a comment" });
    expect(field).toBeDisabled();
    expect(field).toHaveAccessibleDescription(/not open yet/i);
    expect(screen.getByRole("button", { name: "Post" })).toBeDisabled();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<CommentsSection viewerName={null} />);

    await expectNoBlockingA11yViolations(container);
  });
});
