/**
 * The one way IRIS shows a data notice (ADR-051 decisions 16-17, IR-800):
 * the server's `text`, as plain text with its line breaks, under its version
 * and date. Registration, the notice screen, Settings, the sign-in header and
 * the Notices page's preview all render it, so a preview is what readers see.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/render";
import { NoticeText } from "./NoticeText";

const notice = {
  version: 3,
  published_at: "2026-11-02T08:00:00Z",
  text: "What IRIS keeps\nYour name.\n\nSee <b>https://cit.edu/privacy</b> for more.",
};

describe("a data notice", () => {
  it("shows its version and date, then its text with every line break kept", () => {
    render(<NoticeText notice={notice} />);

    expect(screen.getByRole("heading", { name: "Data notice" })).toBeInTheDocument();
    expect(screen.getByText("Version 3 · published Nov 2, 2026")).toBeInTheDocument();
    const body = screen.getByText(/What IRIS keeps/);
    expect(body.textContent).toBe(notice.text);
    expect(body.className).toMatch(/\bwhitespace-pre-wrap\b/);
  });

  it("shows markup and addresses as the characters they are, never as formatting or links", () => {
    const { container } = render(<NoticeText notice={notice} />);

    expect(screen.getByText(/See <b>https:\/\/cit\.edu\/privacy<\/b> for more\./)).toBeInTheDocument();
    expect(container.querySelector("b")).toBeNull();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("says a draft is unpublished instead of giving it a date", () => {
    render(<NoticeText notice={{ version: 4, published_at: null, text: "Draft" }} />);

    expect(screen.getByText("Version 4 · not published yet")).toBeInTheDocument();
  });
});
