/**
 * The clearance strip (IR-1083, audit spec §4.4): one line per office, the
 * server's words, a tone and an icon that never stand in for them.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { ClearanceStripEntry } from "@/types/records";

import { ClearanceStrip } from "./ClearanceStrip";

function entry(overrides: Partial<ClearanceStripEntry> = {}): ClearanceStripEntry {
  return {
    party: "itso", label: "ITSO", kind: "cleared", text: "Cleared", note: null, version: null,
    ...overrides,
  };
}

const KEPT = entry({ kind: "kept", note: "Kept from v1", version: 1 });
const RESET = entry({
  party: "ierc", label: "IERC", kind: "reviewing", text: "Reviewing v2", note: "Reset by v2", version: 2,
});

describe("ClearanceStrip", () => {
  it("reads a kept clearance in the server's words, with the version it was kept from", () => {
    renderScreen(<ClearanceStrip entries={[KEPT]} />);

    const item = within(screen.getByRole("list", { name: "Clearances" })).getByRole("listitem");
    expect(item).toHaveTextContent("ITSO");
    expect(item).toHaveTextContent("Cleared");
    expect(item).toHaveTextContent("Kept from v1");
  });

  it("reads a reset clearance as being reviewed again, and says which version reset it", () => {
    renderScreen(<ClearanceStrip entries={[KEPT, RESET]} />);

    const [, ierc] = screen.getAllByRole("listitem");
    expect(ierc).toHaveTextContent("IERC");
    expect(ierc).toHaveTextContent("Reviewing v2");
    expect(ierc).toHaveTextContent("Reset by v2");
  });

  it("prints the text and note as given and invents none", () => {
    renderScreen(
      <ClearanceStrip
        entries={[
          entry({ kind: "kept", text: "Cleared", note: "Kept from the first round" }),
          entry({ party: "ktto", label: "KTTO", kind: "unclaimed", text: "Waiting for a reviewer" }),
        ]}
      />,
    );

    expect(screen.getByText("Kept from the first round", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Waiting for a reviewer", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(/kept from v/i)).not.toBeInTheDocument();
  });

  it("draws nothing when no office has been routed the record", () => {
    const { container } = renderScreen(<ClearanceStrip entries={[]} />);

    expect(screen.queryByRole("list", { name: "Clearances" })).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("draws nothing, and does not throw, when the response carries no strip (F1)", () => {
    const { container } = renderScreen(
      <ClearanceStrip entries={undefined} />,
    );
    renderScreen(<ClearanceStrip entries={null} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("list", { name: "Clearances" })).not.toBeInTheDocument();
  });

  it("gives every kind a word, so colour and icon are never the only signal", () => {
    const kinds: ClearanceStripEntry[] = [
      entry({ kind: "kept", text: "Cleared", note: "Kept from v1" }),
      entry({ kind: "cleared", text: "Cleared" }),
      entry({ kind: "reviewing", text: "Reviewing v2" }),
      entry({ kind: "unclaimed", text: "Unclaimed" }),
      entry({ kind: "revision", text: "Asked for revision" }),
      entry({ kind: "not_cleared", text: "Not cleared" }),
    ];
    renderScreen(<ClearanceStrip entries={kinds} />);

    for (const item of screen.getAllByRole("listitem")) {
      expect((item.textContent ?? "").trim().length).toBeGreaterThan("ITSO".length);
    }
  });

  it("has no serious accessibility violations", async () => {
    const { container } = renderScreen(<ClearanceStrip entries={[KEPT, RESET]} />);

    await expectNoBlockingA11yViolations(container);
  });
});
