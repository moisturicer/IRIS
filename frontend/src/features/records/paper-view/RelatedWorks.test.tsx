/**
 * "Related works" says why its list is the length it is (IR-568).
 *
 * The endpoint answers with a state beside the list. An empty list used to
 * look the same whether nothing was close, the paper was not indexed, or the
 * request failed; each is now said plainly. None of the copy may hint that a
 * close paper exists but is withheld (IR-460): only this paper's own coverage
 * is ever stated.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { SemanticSearchResult } from "@/types/ai";

import { RelatedWorks } from "./RelatedWorks";

const match = {
  id: 41,
  title: "Rainfall gauge networks for catchment flooding",
  year: 2023,
  classification: "Engineering",
  score: 0.8731,
} as SemanticSearchResult;

const similar = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: {
    similar: (...args: unknown[]) => similar(...(args as [])),
  },
}));

describe("RelatedWorks", () => {
  beforeEach(() => {
    similar.mockReset();
  });

  it("lists each related paper as a link when the state is ready", async () => {
    similar.mockResolvedValue({ data: { state: "ready", results: [match] } });

    const { container } = renderScreen(<RelatedWorks recordId={7} />);

    const link = await screen.findByRole("link", { name: /Rainfall gauge networks/ });
    expect(link).toHaveAttribute("href", "/records/41");
    expect(similar).toHaveBeenCalledWith(7);
    await expectNoBlockingA11yViolations(container);
  });

  it("says nothing close was found, without saying why a paper might be missing", async () => {
    similar.mockResolvedValue({ data: { state: "no_matches", results: [] } });

    const { container } = renderScreen(<RelatedWorks recordId={7} />);

    const note = await screen.findByText(/No related works found for this paper/);
    // IR-460: nothing here may separate "absent" from "withheld".
    expect(note).not.toHaveTextContent(/hidden|withheld|permission|access|restricted|embargo/i);
    expect(note).not.toHaveTextContent(/indexed/i);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("says this paper is not indexed yet, rather than that nothing is close", async () => {
    similar.mockResolvedValue({ data: { state: "not_indexed", results: [] } });

    const { container } = renderScreen(<RelatedWorks recordId={7} />);

    const note = await screen.findByText(/This paper has not been indexed yet/);
    expect(note).not.toHaveTextContent(/No related works found/);
    await expectNoBlockingA11yViolations(container);
  });

  it("says this paper's index does not match the current one", async () => {
    similar.mockResolvedValue({ data: { state: "incompatible", results: [] } });

    renderScreen(<RelatedWorks recordId={7} />);

    const note = await screen.findByText(/index is out of date/);
    expect(note).not.toHaveTextContent(/No related works found/);
  });

  it("says it could not load, offers another try, and does not claim nothing is close", async () => {
    similar
      .mockRejectedValueOnce({ response: { status: 503, data: { state: "unavailable", results: [] } } })
      .mockResolvedValueOnce({ data: { state: "ready", results: [match] } });

    renderScreen(<RelatedWorks recordId={7} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not be loaded/);
    expect(screen.queryByText(/No related works found/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("link", { name: /Rainfall gauge networks/ })).toBeInTheDocument();
    expect(similar).toHaveBeenCalledTimes(2);
  });

  it("treats a lost connection like any other failure to load", async () => {
    similar.mockRejectedValue(new Error("Network Error"));

    renderScreen(<RelatedWorks recordId={7} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/);
  });

  it("degrades on an answer with no state: matches are a list, none is no matches", async () => {
    similar.mockResolvedValueOnce({ data: { results: [match] } });
    const { unmount } = renderScreen(<RelatedWorks recordId={7} />);
    expect(await screen.findByRole("link", { name: /Rainfall gauge networks/ })).toBeInTheDocument();
    unmount();

    similar.mockResolvedValueOnce({ data: { results: [] } });
    renderScreen(<RelatedWorks recordId={7} />);
    expect(await screen.findByText(/No related works found for this paper/)).toBeInTheDocument();
  });

  it("reads again when the paper changes", async () => {
    similar.mockResolvedValue({ data: { state: "no_matches", results: [] } });

    const { rerender } = renderScreen(<RelatedWorks recordId={7} />);
    await screen.findByText(/No related works found for this paper/);
    rerender(<RelatedWorks recordId={8} />);

    await vi.waitFor(() => expect(similar).toHaveBeenLastCalledWith(8));
  });
});
