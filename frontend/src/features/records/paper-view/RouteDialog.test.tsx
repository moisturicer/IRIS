/**
 * The routing dialog: *Accept & route…* and *Route to office…* (IR-261,
 * ADR-032 §3–§4). Every query goes through the accessible tree, by role and
 * accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor } from "@/test/render";
import type { RouteOptions } from "@/types/records";

import { RouteDialog } from "./RouteDialog";

const routeOptions = vi.fn();
const acceptAndRoute = vi.fn();
const route = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    routeOptions: (id: number) => routeOptions(id),
    acceptAndRoute: (id: number, body: unknown) => acceptAndRoute(id, body),
    route: (id: number, body: unknown) => route(id, body),
  },
}));

const RECORD_ID = 7;

const ADVISER_OPTIONS: RouteOptions = {
  from_party: "adviser",
  from_label: "Adviser",
  accept: true,
  targets: [
    {
      party: "itso",
      label: "ITSO",
      members: [{ id: 51, name: "Ina Tso" }, { id: 52, name: "Ivo Tso" }],
      already_holds: false,
      author_hint: "The author flagged possible intellectual property.",
    },
    { party: "ierc", label: "IERC", members: [{ id: 61, name: "Iris Erc" }], already_holds: false, author_hint: null },
    { party: "ktto", label: "KTTO", members: [], already_holds: false, author_hint: null },
  ],
};

function open(mode: "accept" | "route" = "accept") {
  const onClose = vi.fn();
  const onRouted = vi.fn();
  const view = renderScreen(
    <RouteDialog recordId={RECORD_ID} mode={mode} onClose={onClose} onRouted={onRouted} />,
  );
  return { onClose, onRouted, container: view.container };
}

const submitButton = () => screen.getByRole("button", { name: "Accept and route" });

beforeEach(() => {
  routeOptions.mockReset().mockResolvedValue({ data: ADVISER_OPTIONS });
  acceptAndRoute.mockReset().mockResolvedValue({ data: {} });
  route.mockReset().mockResolvedValue({ data: {} });
});

describe("RouteDialog", () => {
  it("offers each office unticked, with the author's hint beside it", async () => {
    const { container } = open();

    expect(screen.getByRole("dialog", { name: "Accept and route" })).toBeInTheDocument();
    const itso = await screen.findByRole("checkbox", { name: "ITSO" });
    expect(itso).not.toBeChecked();
    expect(itso).toHaveAccessibleDescription("The author flagged possible intellectual property.");
    expect(screen.getByRole("checkbox", { name: "IERC" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "KTTO" })).not.toBeChecked();
    await expectNoBlockingA11yViolations(container);
  });

  it("waits for an office and a reason before it can be sent", async () => {
    open();
    await userEvent.click(await screen.findByRole("checkbox", { name: "ITSO" }));
    expect(submitButton()).toBeDisabled();

    await userEvent.type(screen.getByRole("textbox", { name: "Reason" }), "Patentable sensor.");
    expect(submitButton()).toBeEnabled();
  });

  it("accepts and routes to the ticked offices, with a nominee where one was chosen", async () => {
    const { onRouted } = open();
    await userEvent.click(await screen.findByRole("checkbox", { name: "ITSO" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "IERC" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Reviewer at ITSO" }), "52");
    // IERC's picker is left at its default: the record goes to IERC's pool.
    expect(screen.getByRole("combobox", { name: "Reviewer at IERC" })).toHaveDisplayValue(
      "Leave in IERC's pool",
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Reason" }), "Patentable sensor.");
    await userEvent.click(submitButton());

    await waitFor(() => expect(onRouted).toHaveBeenCalledWith(["ITSO", "IERC"]));
    expect(acceptAndRoute).toHaveBeenCalledWith(RECORD_ID, {
      reason: "Patentable sensor.",
      to: [{ party: "itso", nominee: 52 }, { party: "ierc" }],
    });
    expect(route).not.toHaveBeenCalled();
  });

  it("onward routing uses the route endpoint and says the router keeps reviewing", async () => {
    routeOptions.mockResolvedValue({
      data: {
        ...ADVISER_OPTIONS,
        from_party: "itso",
        from_label: "ITSO",
        accept: false,
        targets: ADVISER_OPTIONS.targets.slice(1),
      },
    });
    const { onRouted } = open("route");

    expect(await screen.findByText(/ITSO keeps reviewing this record/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "KTTO" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Reason" }), "Commercial potential.");
    await userEvent.click(screen.getByRole("button", { name: "Route" }));

    await waitFor(() => expect(onRouted).toHaveBeenCalledWith(["KTTO"]));
    expect(route).toHaveBeenCalledWith(RECORD_ID, { reason: "Commercial potential.", to: [{ party: "ktto" }] });
  });

  it("an office already reviewing it needs a nominee", async () => {
    routeOptions.mockResolvedValue({
      data: {
        ...ADVISER_OPTIONS,
        targets: [{ ...ADVISER_OPTIONS.targets[0], already_holds: true }],
      },
    });
    open();
    await userEvent.click(await screen.findByRole("checkbox", { name: "ITSO already reviewing" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Reason" }), "Second opinion.");
    expect(submitButton()).toBeDisabled();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Reviewer at ITSO" }), "51");
    expect(submitButton()).toBeEnabled();
  });

  it("shows a refusal in the dialog and keeps what was typed", async () => {
    acceptAndRoute.mockRejectedValue({ response: { data: { detail: "The nominee is not a member of ITSO." } } });
    const { onRouted } = open();
    await userEvent.click(await screen.findByRole("checkbox", { name: "ITSO" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Reason" }), "Patentable sensor.");
    await userEvent.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("The nominee is not a member of ITSO.");
    expect(screen.getByRole("textbox", { name: "Reason" })).toHaveValue("Patentable sensor.");
    expect(screen.getByRole("checkbox", { name: "ITSO" })).toBeChecked();
    expect(onRouted).not.toHaveBeenCalled();
  });

  it("says so when the offices cannot be loaded", async () => {
    routeOptions.mockRejectedValue({ response: { data: { detail: "Only a reviewer seated on this record may route it onward." } } });
    open("route");

    expect(await screen.findByRole("alert")).toHaveTextContent("Only a reviewer seated on this record");
  });
});
