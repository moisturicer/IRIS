/**
 * No Ask IRIS string names the institution (IR-1090, IR-768): the institution is
 * a property of the deployment, so copy that does not need it stays neutral.
 */
import { describe, expect, it } from "vitest";

import { INSTITUTION } from "@/config/institution";
import { renderScreen } from "@/test/render";

import { AssistantMessageSkeleton } from "./AssistantMessageSkeleton";
import { ChatMessageList } from "./ChatMessageList";

const institutionNames = [INSTITUTION.shortName, INSTITUTION.name];

function expectNeutral(container: HTMLElement) {
  const shown = `${container.textContent} ${[...container.querySelectorAll("[aria-label]")]
    .map((element) => element.getAttribute("aria-label"))
    .join(" ")}`;
  for (const name of institutionNames) expect(shown).not.toContain(name);
}

describe("Ask IRIS copy", () => {
  it("does not name the institution while an answer is being found", () => {
    const { container } = renderScreen(<AssistantMessageSkeleton />);

    expect(container.textContent).toMatch(/searching/i);
    expectNeutral(container);
  });

  it("does not name the institution in an empty earlier conversation", () => {
    const { container } = renderScreen(<ChatMessageList messages={[]} isLoading={false} indexedRecords={12} />);

    expect(container.textContent).toMatch(/grounded in published/i);
    expectNeutral(container);
  });
});
