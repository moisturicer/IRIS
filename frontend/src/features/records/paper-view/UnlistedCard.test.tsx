/**
 * RDCO publishes an Unlisted paper later (ADR-047 §10, IR-878).
 *
 * The card follows the server: it appears only when `publish_unlisted` is
 * offered, and while the embargo holds, Publish stays visible but disabled,
 * with the server's reason. Every query goes through the accessible tree.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

import { recordsApi } from "@/api/records";

import { UnlistedCard } from "./UnlistedCard";

vi.mock("@/api/records", () => ({
  recordsApi: { publishUnlisted: vi.fn() },
}));

const HELD = "Under embargo until 15 Jan 2099. Release the embargo, then publish.";

function paper(
  publishUnlisted: { blocked: string | null } | null,
  capabilities: Capability[] = publishUnlisted ? ["publish_unlisted"] : [],
) {
  return {
    id: 7, record_type_name: "Thesis / Research", capabilities, publish_unlisted: publishUnlisted,
  } as unknown as RecordDetail;
}

function refusal(data: unknown, status = 400) {
  return Object.assign(new Error("refused"), { response: { status, data } });
}

function renderCard(record: RecordDetail) {
  const onChanged = vi.fn();
  const view = renderScreen(<UnlistedCard record={record} onChanged={onChanged} />);
  return { ...view, onChanged };
}

beforeEach(() => {
  vi.mocked(recordsApi.publishUnlisted).mockReset();
});

describe("who sees it", () => {
  it("is absent when the server offers no later publish", () => {
    renderCard(paper(null));
    expect(screen.queryByRole("region", { name: "Unlisted" })).not.toBeInTheDocument();
  });

  it("is absent when the block is there but the capability isn't", () => {
    renderCard(paper({ blocked: null }, []));
    expect(screen.queryByRole("region", { name: "Unlisted" })).not.toBeInTheDocument();
  });
});

describe("while the embargo holds", () => {
  it("shows Publish disabled, with the server's reason", async () => {
    const { container } = renderCard(paper({ blocked: HELD }));

    const card = screen.getByRole("region", { name: "Unlisted" });
    const publish = within(card).getByRole("button", { name: "Publish to Discover" });
    expect(publish).toBeDisabled();
    expect(publish).toHaveAccessibleDescription(HELD);
    await expectNoBlockingA11yViolations(container);
  });
});

describe("once released", () => {
  it("asks first, sends the note, and announces the result", async () => {
    vi.mocked(recordsApi.publishUnlisted).mockResolvedValue({ data: {} } as never);
    const { onChanged } = renderCard(paper({ blocked: null }));

    await userEvent.click(screen.getByRole("button", { name: "Publish to Discover" }));
    const dialog = screen.getByRole("dialog", { name: "Publish this thesis to Discover?" });
    expect(dialog).toHaveTextContent(/any signed-in user can read it/);
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Note (optional)" }), "Patent filed.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Publish" }));

    expect(recordsApi.publishUnlisted).toHaveBeenCalledWith(7, "Patent filed.");
    expect(onChanged).toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Published. It is now in Discover.");
  });

  it("Cancel sends nothing", async () => {
    renderCard(paper({ blocked: null }));

    await userEvent.click(screen.getByRole("button", { name: "Publish to Discover" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(recordsApi.publishUnlisted).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the server's refusal in its own words and reads the record again", async () => {
    vi.mocked(recordsApi.publishUnlisted).mockRejectedValue(refusal({ detail: HELD }));
    const { onChanged } = renderCard(paper({ blocked: null }));

    await userEvent.click(screen.getByRole("button", { name: "Publish to Discover" }));
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(HELD);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("keeps the refusal on screen when the reloaded record no longer offers it", async () => {
    // Another RDCO member published it first: the reload drops the offer.
    const gone = "Only an Unlisted paper can be published this way.";
    vi.mocked(recordsApi.publishUnlisted).mockRejectedValue(refusal({ detail: gone }));
    const onChanged = vi.fn();
    const { rerender } = renderScreen(<UnlistedCard record={paper({ blocked: null })} onChanged={onChanged} />);

    await userEvent.click(screen.getByRole("button", { name: "Publish to Discover" }));
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await screen.findByRole("alert");
    rerender(<UnlistedCard record={paper(null)} onChanged={onChanged} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(gone);
  });
});
