import { beforeEach, describe, expect, it, vi } from "vitest";
import { useLocation } from "react-router-dom";
import { renderScreen, screen, userEvent } from "@/test/render";
import { ContinueProposal } from "./ContinueProposal";

vi.mock("@/api/records", () => ({ recordsApi: {
  recordTypes: vi.fn().mockResolvedValue({ data: [{ id: 3, name: "Project" }] }),
  continueAs: vi.fn().mockResolvedValue({ data: { id: 42 } }),
} }));

const { recordsApi } = await import("@/api/records");

function Address() {
  const location = useLocation();
  return <output aria-label="Address">{location.pathname}{location.search}</output>;
}

beforeEach(() => {
  vi.mocked(recordsApi.recordTypes).mockResolvedValue({ data: {
    count: 1, next: null, previous: null, results: [{ id: 3, name: "Project" }],
  } } as never);
  vi.mocked(recordsApi.continueAs).mockResolvedValue({ data: { id: 42 } } as never);
});

describe("Proposal continuation", () => {
  it("creates the chosen child and opens Publish at its draft", async () => {
    renderScreen(<><ContinueProposal recordId={12} /><Address /></>);
    await userEvent.click(screen.getByRole("button", { name: "Continue as Project" }));
    expect(recordsApi.continueAs).toHaveBeenCalledWith(12, 3);
    expect(await screen.findByText("/?publish=42")).toBeInTheDocument();
  });

  it("shows a refusal and allows retry without navigating", async () => {
    vi.mocked(recordsApi.continueAs).mockRejectedValueOnce({ response: {
      status: 409, data: { detail: "This proposal has already been continued." },
    } });
    renderScreen(<><ContinueProposal recordId={12} /><Address /></>);
    await userEvent.click(screen.getByRole("button", { name: "Continue as Project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already been continued");
    expect(screen.getByRole("button", { name: "Continue as Project" })).toBeEnabled();
    expect(screen.getByLabelText("Address")).toHaveTextContent("/");
  });
});
