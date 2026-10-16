import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import { ASK_IRIS_NOTICE, AskIrisNotice } from "./AskIrisNotice";
import { ChatInput } from "./ChatInput";

const TEXT = "Ask IRIS can make mistakes. Check important details against the cited papers.";

describe("the mistake notice (IR-596)", () => {
  it("says exactly the specified sentence, as plain readable text", () => {
    const { container } = renderScreen(<AskIrisNotice />);

    expect(ASK_IRIS_NOTICE).toBe(TEXT);
    expect(screen.getByText(TEXT)).toBeInTheDocument();
    expect(container.querySelector("[aria-hidden]")).toBeNull();
  });

  it("is visible under the Ask IRIS prompt box before any question", () => {
    renderScreen(<ChatInput onSend={vi.fn()} />);

    const notice = screen.getByText(TEXT);
    const box = screen.getByRole("textbox");
    expect(box.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("wraps rather than truncating", () => {
    renderScreen(<AskIrisNotice />);

    const classes = screen.getByText(TEXT).className;
    expect(classes).not.toMatch(/truncate|whitespace-nowrap/);
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<AskIrisNotice />);

    await expectNoBlockingA11yViolations(container);
  });
});
