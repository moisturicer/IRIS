/**
 * Paper View's embargo card (ADR-052 decisions 5, 6 and 11, IR-817, IR-882).
 *
 * Every control comes from `capabilities`: the card compares no role names.
 * Releasing asks first and says the text goes to outside AI companies for good.
 * A refusal shows the server's own words. Every query goes through the
 * accessible tree.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail, RecordEmbargo, RecordIpRelease } from "@/types/records";

import { recordsApi } from "@/api/records";

import { EmbargoCard } from "./EmbargoCard";

vi.mock("@/api/records", () => ({
  recordsApi: {
    setEmbargo: vi.fn(),
    releaseEmbargo: vi.fn(),
    releaseIp: vi.fn(),
  },
}));

const TODAY = "2026-11-03";

function paper(
  embargo: RecordEmbargo | null,
  capabilities: Capability[] = [],
  { isIp = false, ipRelease = null }: { isIp?: boolean; ipRelease?: RecordIpRelease | null } = {},
) {
  return { id: 7, embargo, capabilities, is_ip: isIp, ip_release: ipRelease } as unknown as RecordDetail;
}

const ACTIVE: RecordEmbargo = { state: "active", until: "2099-01-01" };
/** How every paper starts (IR-882). */
const UNDATED: RecordEmbargo = { state: "active", until: null };

function refusal(data: unknown, status = 400) {
  return Object.assign(new Error("refused"), { response: { status, data } });
}

function renderCard(record: RecordDetail) {
  const onChanged = vi.fn();
  const view = renderScreen(<EmbargoCard record={record} onChanged={onChanged} today={TODAY} />);
  return { ...view, onChanged };
}

beforeEach(() => {
  vi.mocked(recordsApi.setEmbargo).mockReset();
  vi.mocked(recordsApi.releaseEmbargo).mockReset();
  vi.mocked(recordsApi.releaseIp).mockReset();
});

describe("where the embargo stands", () => {
  it("shows an active embargo and its review date, which ends nothing", () => {
    renderCard(paper(ACTIVE));

    const card = screen.getByRole("region", { name: "Embargo" });
    expect(within(card).getByText("Under embargo")).toBeInTheDocument();
    expect(within(card).getByText(/Review by Jan 1, 2099/)).toBeInTheDocument();
    expect(within(card).getByText(/lasts until someone releases it/)).toBeInTheDocument();
  });

  it("shows an embargo with no date, which holds until someone releases it", () => {
    renderCard(paper(UNDATED));

    expect(screen.getByText("Under embargo")).toBeInTheDocument();
    expect(screen.getByText(/No review date\. Ask IRIS won't use it and it can't be published/)).toBeInTheDocument();
  });

  it("shows a released one with the date it held", () => {
    renderCard(paper({ state: "released", until: "2026-12-01" }));
    expect(screen.getByText("Released")).toBeInTheDocument();
    expect(screen.getByText(/Its review date was Dec 1, 2026/)).toBeInTheDocument();
  });

  it("is absent for a viewer the API tells nothing", () => {
    renderCard(paper(null));

    expect(screen.queryByRole("region", { name: "Embargo" })).not.toBeInTheDocument();
  });
});

describe("who may act comes from capabilities alone", () => {
  it("offers Change date without Release, and says who can release it", () => {
    renderCard(paper(ACTIVE, ["set_embargo"]));

    expect(screen.getByRole("button", { name: "Change date" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Release embargo" })).not.toBeInTheDocument();
    expect(screen.getByText("Only the paper's Adviser or RDCO can release it.")).toBeInTheDocument();
  });

  it("offers Add review date on an embargo with no date, and Embargo again once released", () => {
    const { unmount } = renderCard(paper(UNDATED, ["set_embargo"]));
    expect(screen.getByRole("button", { name: "Add review date" })).toBeInTheDocument();
    unmount();

    renderCard(paper({ state: "released", until: null }, ["set_embargo"]));
    expect(screen.getByRole("button", { name: "Embargo again" })).toBeInTheDocument();
  });

  it("offers Release to whoever the server offers it, without the who-can line", () => {
    renderCard(paper(ACTIVE, ["set_embargo", "release_embargo"]));

    expect(screen.getByRole("button", { name: "Release embargo" })).toBeInTheDocument();
    expect(screen.queryByText(/can release it/)).not.toBeInTheDocument();
  });

  it("offers nothing to a viewer offered nothing", () => {
    renderCard(paper(ACTIVE));

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("setting or moving the date", () => {
  it("saves the chosen date and reloads the record", async () => {
    vi.mocked(recordsApi.setEmbargo).mockResolvedValue({ data: { state: "active", until: "2027-03-01" } } as never);
    const { onChanged } = renderCard(paper(ACTIVE, ["set_embargo"]));

    await userEvent.click(screen.getByRole("button", { name: "Change date" }));
    const dialog = screen.getByRole("dialog", { name: "Change the review date" });
    const field = within(dialog).getByLabelText("Review date");
    expect(field).toHaveAttribute("min", TODAY);
    await userEvent.clear(field);
    await userEvent.type(field, "2027-03-01");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save date" }));

    expect(recordsApi.setEmbargo).toHaveBeenCalledWith(7, "2027-03-01");
    expect(onChanged).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("warns first, then shows the server's notice, when text may already have gone out", async () => {
    vi.mocked(recordsApi.setEmbargo).mockResolvedValue({
      data: { state: "active", until: "2027-03-01", notice: "Text already sent to outside AI companies can't be recalled." },
    } as never);
    renderCard(paper({ state: "released", until: "2026-12-01" }, ["set_embargo"]));

    await userEvent.click(screen.getByRole("button", { name: "Embargo again" }));
    const dialog = screen.getByRole("dialog", { name: "Embargo this paper again" });
    expect(within(dialog).getByText(/already sent to outside AI companies can't be recalled/)).toBeInTheDocument();
    await userEvent.type(within(dialog).getByLabelText("Review date"), "2027-03-01");
    await userEvent.click(within(dialog).getByRole("button", { name: "Embargo again" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Text already sent to outside AI companies can't be recalled.",
    );
  });

  it("does not warn when nothing could have gone out", async () => {
    renderCard(paper(UNDATED, ["set_embargo"]));

    await userEvent.click(screen.getByRole("button", { name: "Add review date" }));

    const dialog = screen.getByRole("dialog", { name: "Add a review date" });
    expect(within(dialog).queryByText(/can't be recalled/)).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Add date" })).toBeInTheDocument();
  });

  it("keeps the dialog open with the server's refusal of the date", async () => {
    vi.mocked(recordsApi.setEmbargo).mockRejectedValue(
      refusal({ embargoed_until: ["The date to review this embargo cannot be in the past."] }),
    );
    const { onChanged } = renderCard(paper(ACTIVE, ["set_embargo"]));

    await userEvent.click(screen.getByRole("button", { name: "Change date" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save date" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The date to review this embargo cannot be in the past.",
    );
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe("releasing", () => {
  it("asks first, saying the text goes to AI companies for good", async () => {
    vi.mocked(recordsApi.releaseEmbargo).mockResolvedValue({ data: { state: "released", until: ACTIVE.until } } as never);
    const { onChanged } = renderCard(paper(ACTIVE, ["release_embargo"]));

    await userEvent.click(screen.getByRole("button", { name: "Release embargo" }));
    const dialog = screen.getByRole("dialog", { name: "Release this embargo?" });
    expect(dialog).toHaveTextContent(/outside AI companies/);
    expect(dialog).toHaveTextContent(/can't be undone/);
    expect(recordsApi.releaseEmbargo).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Release" }));

    expect(recordsApi.releaseEmbargo).toHaveBeenCalledWith(7);
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("sends nothing when cancelled", async () => {
    renderCard(paper(ACTIVE, ["release_embargo"]));

    await userEvent.click(screen.getByRole("button", { name: "Release embargo" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(recordsApi.releaseEmbargo).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a stale or refused release in the server's words, and reads the record again", async () => {
    vi.mocked(recordsApi.releaseEmbargo).mockRejectedValue(refusal({ detail: "This paper isn't under an embargo." }));
    const { onChanged } = renderCard(paper(ACTIVE, ["release_embargo"]));

    await userEvent.click(screen.getByRole("button", { name: "Release embargo" }));
    await userEvent.click(screen.getByRole("button", { name: "Release" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This paper isn't under an embargo.");
    expect(onChanged).toHaveBeenCalledOnce();
  });
});

describe("KTTO's release of an IP mark", () => {
  const marked = (capabilities: Capability[]) =>
    paper({ state: "released", until: null }, capabilities, {
      isIp: true, ipRelease: { released: false, released_at: null },
    });

  it("is offered only where the server offers it, and asks first", async () => {
    vi.mocked(recordsApi.releaseIp).mockResolvedValue({ data: { marked: true, released: true } } as never);
    const { onChanged } = renderCard(marked(["release_ip"]));

    await userEvent.click(screen.getByRole("button", { name: "Release IP mark" }));
    const dialog = screen.getByRole("dialog", { name: "Release this IP mark for the AI?" });
    expect(dialog).toHaveTextContent(/outside AI companies/);
    expect(dialog).toHaveTextContent(/can't be undone/);
    expect(dialog).toHaveTextContent(/stays marked as intellectual property/);
    await userEvent.click(within(dialog).getByRole("button", { name: "Release" }));

    expect(recordsApi.releaseIp).toHaveBeenCalledWith(7);
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("is absent without the capability", () => {
    renderCard(marked([]));

    expect(screen.queryByRole("button", { name: "Release IP mark" })).not.toBeInTheDocument();
  });

  it("shows a refused release in the server's words", async () => {
    vi.mocked(recordsApi.releaseIp).mockRejectedValue(
      refusal({ detail: "KTTO has already released this paper's IP mark." }),
    );
    renderCard(marked(["release_ip"]));

    await userEvent.click(screen.getByRole("button", { name: "Release IP mark" }));
    await userEvent.click(screen.getByRole("button", { name: "Release" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("KTTO has already released this paper's IP mark.");
  });
});

describe("accessibility", () => {
  it("has no blocking violations in the card or either dialog", async () => {
    const { container } = renderCard(paper(ACTIVE, ["set_embargo", "release_embargo"]));
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(screen.getByRole("button", { name: "Change date" }));
    await expectNoBlockingA11yViolations(document.body);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await userEvent.click(screen.getByRole("button", { name: "Release embargo" }));
    await expectNoBlockingA11yViolations(document.body);
  });
});
