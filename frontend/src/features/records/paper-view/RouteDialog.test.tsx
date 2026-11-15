/**
 * The routing dialog: *Accept & send to RDCO…* and *Request review…*
 * (ADR-047 §1–§3). Every query goes through the accessible tree, by role and
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
  from_party: "adviser", from_label: "Adviser", accept: true,
  targets: [{ party: "rdco", label: "RDCO", members: [{ id: 51, name: "Rhea Director" }, { id: 52, name: "Rico Officer" }], already_holds: false, author_hint: null }],
};
const OFFICE_OPTIONS: RouteOptions = {
  from_party: "rdco", from_label: "RDCO", accept: false, suggested_offices: ["itso"],
  targets: [{ ...ADVISER_OPTIONS.targets[0], party: "itso", label: "ITSO" },
    { party: "ierc", label: "IERC", members: [], already_holds: false, author_hint: null }],
};

function open(mode: "accept" | "route" = "accept", authorHints: string[] = []) {
  const onClose = vi.fn();
  const onRouted = vi.fn();
  const view = renderScreen(
    <RouteDialog recordId={RECORD_ID} mode={mode} authorHints={authorHints} onClose={onClose} onRouted={onRouted} />,
  );
  return { onClose, onRouted, container: view.container };
}

const submitButton = () => screen.getByRole("button", { name: "Accept & send to RDCO" });

beforeEach(() => {
  routeOptions.mockReset().mockResolvedValue({ data: ADVISER_OPTIONS });
  acceptAndRoute.mockReset().mockResolvedValue({ data: {} });
  route.mockReset().mockResolvedValue({ data: {} });
});

describe("RouteDialog", () => {
  it("sends to RDCO's pool and keeps suggestions separate", async () => {
    const { onRouted, container } = open();
    expect(await screen.findByRole("checkbox", { name: "RDCO" })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "ITSO" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Why? (required)" }), "Possible IP.");
    await expectNoBlockingA11yViolations(container);
    await userEvent.click(submitButton());
    await waitFor(() => expect(onRouted).toHaveBeenCalledWith(["RDCO"]));
    expect(acceptAndRoute).toHaveBeenCalledWith(RECORD_ID, { reason: "Possible IP.", to: [{ party: "rdco" }], suggested_offices: ["itso"] });
  });
  it("nominates multiple RDCO officers", async () => {
    open();
    expect(await screen.findByRole("checkbox", { name: "RDCO" })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Rhea Director" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Rico Officer" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Why? (required)" }), "Institutional review.");
    await userEvent.click(submitButton());
    await waitFor(() => expect(acceptAndRoute).toHaveBeenCalledWith(RECORD_ID, { reason: "Institutional review.", to: [{ party: "rdco", nominees: [51, 52] }], suggested_offices: [] }));
  });
  it("offices request the pool or multiple officers and see the Adviser's suggestions", async () => {
    routeOptions.mockResolvedValue({ data: OFFICE_OPTIONS });
    const { onRouted } = open("route");
    await userEvent.click(await screen.findByRole("checkbox", { name: "ITSO" }));
    expect(screen.getByText(/The Adviser suggested ITSO/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Rhea Director" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Rico Officer" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "IERC" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Why? (required)" }), "IP and ethics.");
    await userEvent.click(screen.getByRole("button", { name: "Send request" }));
    await waitFor(() => expect(onRouted).toHaveBeenCalledWith(["ITSO", "IERC"]));
    expect(route).toHaveBeenCalledWith(RECORD_ID, { reason: "IP and ethics.", to: [{ party: "itso", nominees: [51, 52] }, { party: "ierc" }] });
  });
  it("requires officers for an office that already holds the record", async () => {
    routeOptions.mockResolvedValue({ data: { ...OFFICE_OPTIONS, targets: [{ ...OFFICE_OPTIONS.targets[0], already_holds: true }] } });
    open("route");
    await userEvent.click(await screen.findByRole("checkbox", { name: "ITSO already reviewing" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Why? (required)" }), "Second opinion.");
    expect(screen.getByRole("button", { name: "Send request" })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Rhea Director" }));
    expect(screen.getByRole("button", { name: "Send request" })).toBeEnabled();
  });
  it("keeps the reason and officers after a refusal", async () => {
    acceptAndRoute.mockRejectedValue({ response: { data: { detail: "Officer unavailable." } } });
    open();
    expect(await screen.findByRole("checkbox", { name: "RDCO" })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Rhea Director" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Why? (required)" }), "Institutional review.");
    await userEvent.click(submitButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Officer unavailable.");
    expect(screen.getByRole("checkbox", { name: "Rhea Director" })).toBeChecked();
    expect(screen.getByRole("textbox", { name: "Why? (required)" })).toHaveValue("Institutional review.");
  });
  it("says where an unnamed request goes and who is told when officers are named", async () => {
    open("accept", ["The author flagged possible intellectual property."]);
    expect(await screen.findByText("Nobody picked: it goes to RDCO's pool, and anyone there can claim it.")).toBeInTheDocument();
    expect(screen.getByText(/The author flagged: The author flagged possible intellectual property./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Rhea Director" }));
    expect(screen.getByText("Rhea Director is asked directly and told now.")).toBeInTheDocument();
  });
  it("reports failure to load offices", async () => {
    routeOptions.mockRejectedValue(new Error("offline")); open("route");
    expect(await screen.findByRole("alert")).toHaveTextContent("The offices could not be loaded.");
  });
  it("offers Try again when the offices did not load, and reads them again (IR-1078)", async () => {
    routeOptions.mockRejectedValueOnce(Object.assign(new Error("500"), { response: { status: 500 } }));
    open("route");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("IRIS took too long to answer. Try again.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("checkbox", { name: "RDCO" })).toBeInTheDocument();
    expect(routeOptions).toHaveBeenCalledTimes(2);
  });
});
