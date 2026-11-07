import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { auditApi } from "@/api/audit";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import AuditLogPage from "./AuditLogPage";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { AUDIT_EVENT_LABELS } from "@/types/audit";

vi.mock("@/api/audit", () => ({ auditApi: { list: vi.fn(), exportCsv: vi.fn(), eventTypes: vi.fn() } }));

/** What GET /audit/event-types/ returns (IR-913): the server's own types and labels. */
const serverTypes = Object.entries(AUDIT_EVENT_LABELS).map(([type, label]) => ({ type, label }));

function respondWithTypes(types: { type: string; label: string }[]) {
  vi.mocked(auditApi.eventTypes).mockResolvedValue({ data: types } as unknown as Awaited<ReturnType<typeof auditApi.eventTypes>>);
}

beforeEach(() => {
  vi.clearAllMocks();
  respondWithTypes(serverTypes);
  vi.mocked(auditApi.list).mockResolvedValue({ data: { count: 1, results: [{
    id: 1, event_type: "RESUBMITTED", user: 2, user_name: "Lee Cruz", record: 3,
    record_title: "Water study", created_at: "2026-10-01T12:13:14Z",
    metadata: { version: 2, preserved_parties: ["itso"], policy: "clearance_aware" },
  }] } } as unknown as Awaited<ReturnType<typeof auditApi.list>>);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("shows labelled workflow details and grouped filters with the API actor name", async () => {
  const { container } = renderScreen(<AuditLogPage />);
  expect(await screen.findByText("Lee Cruz")).toBeInTheDocument();
  expect(screen.getByText("Preserved parties")).toBeInTheDocument();
  expect(screen.getByText("ITSO")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Workflow" })).toBeInTheDocument();
  expect(await screen.findByRole("option", { name: "Assignment Deadline Extended" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Water study" })).toHaveAttribute("href", "/records/3");
  const table = screen.getByRole("table", { name: "Audit log events" });
  for (const header of within(table).getAllByRole("columnheader")) {
    expect(header).toHaveAttribute("scope", "col");
  }
  // Every type the server lists is a filter option with that value. The test no
  // longer reads backend source (IR-913), so a new backend type cannot fail it.
  expect(serverTypes.length).toBeGreaterThan(30);
  for (const { type, label } of serverTypes) {
    expect(screen.getByRole("option", { name: label })).toHaveValue(type);
  }
  await expectNoBlockingA11yViolations(container);
});

it("offers a type the frontend has never heard of, under Other, the moment the server lists it", async () => {
  respondWithTypes([...serverTypes, { type: "A_BRAND_NEW_EVENT", label: "A Brand New Event" }]);
  renderScreen(<AuditLogPage />);

  const added = await screen.findByRole("option", { name: "A Brand New Event" });

  expect(added).toHaveValue("A_BRAND_NEW_EVENT");
  expect(within(screen.getByRole("group", { name: "Other" })).getByRole("option", { name: "A Brand New Event" })).toBe(added);
});

it("does not offer a type the server no longer lists, even though the frontend still groups it", async () => {
  respondWithTypes(serverTypes.filter(({ type }) => type !== "PIN_GENERATED"));
  renderScreen(<AuditLogPage />);

  await screen.findByRole("option", { name: "Login" });

  expect(screen.queryByRole("option", { name: "PIN Generated" })).not.toBeInTheDocument();
});

it("filters by an event type it learned only from the server", async () => {
  respondWithTypes([...serverTypes, { type: "A_BRAND_NEW_EVENT", label: "A Brand New Event" }]);
  const person = userEvent.setup();
  renderScreen(<AuditLogPage />);
  await screen.findByRole("option", { name: "A Brand New Event" });

  await person.selectOptions(screen.getByRole("combobox", { name: "Event type" }), "A_BRAND_NEW_EVENT");
  await person.click(screen.getByRole("button", { name: "Filter" }));

  await waitFor(() => expect(auditApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ event_type: "A_BRAND_NEW_EVENT" })));
});

it("shows the log without type options, and says so, when the types cannot be loaded", async () => {
  vi.mocked(auditApi.eventTypes).mockRejectedValue(new Error("Offline"));
  renderScreen(<AuditLogPage />);

  expect(await screen.findByText("Lee Cruz")).toBeInTheDocument();
  expect(await screen.findByText(/event types could not be loaded/i)).toBeInTheDocument();
  const select = screen.getByRole("combobox", { name: "Event type" });
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["All events"]);
  // The page still works: the log loaded, and the other filters are there.
  expect(screen.getByRole("button", { name: "Filter" })).toBeEnabled();
});

it("treats a types response that is not a list like a failed request, and still shows the log", async () => {
  // The shape of an answer is the server's to keep, and the page must not crash on a
  // wrong one: the router tests answer every GET with a paginated object (IR-913 CI).
  vi.mocked(auditApi.eventTypes).mockResolvedValue({ data: { count: 0, results: [] } } as unknown as Awaited<ReturnType<typeof auditApi.eventTypes>>);
  renderScreen(<AuditLogPage />);

  expect(await screen.findByText("Lee Cruz")).toBeInTheDocument();
  expect(await screen.findByText(/event types could not be loaded/i)).toBeInTheDocument();
  const select = screen.getByRole("combobox", { name: "Event type" });
  expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["All events"]);
});

it("names an event it has no label for by the server's label, not the raw code", async () => {
  respondWithTypes([...serverTypes, { type: "A_BRAND_NEW_EVENT", label: "A Brand New Event" }]);
  vi.mocked(auditApi.list).mockResolvedValue({ data: { count: 1, results: [{
    id: 2, event_type: "A_BRAND_NEW_EVENT", user: 2, user_name: "Lee Cruz", record: null,
    record_title: null, created_at: "2026-10-02T12:13:14Z", metadata: {},
  }] } } as unknown as Awaited<ReturnType<typeof auditApi.list>>);
  renderScreen(<AuditLogPage />);

  const table = await screen.findByRole("table", { name: "Audit log events" });

  expect(await within(table).findByText("A Brand New Event")).toBeInTheDocument();
});


it("announces loading and an empty result set through a named polite status", async () => {
  let resolveList!: (value: Awaited<ReturnType<typeof auditApi.list>>) => void;
  vi.mocked(auditApi.list).mockImplementationOnce(() => new Promise((resolve) => {
    resolveList = resolve;
  }));

  renderScreen(<AuditLogPage />);

  const status = screen.getByRole("status", { name: "Audit log events status" });
  expect(status).toHaveAttribute("aria-live", "polite");
  expect(status).toHaveTextContent("Loading Audit log events.");

  resolveList(
  { data: { count: 0, results: [] } } as unknown as Awaited<ReturnType<typeof auditApi.list>>,
);
  await waitFor(() => expect(status).toHaveTextContent("Audit log events has no results."));
  expect(screen.getByRole("table", { name: "Audit log events" })).toBeInTheDocument();
  expect(screen.getByText("No records found.")).toBeInTheDocument();
});

it("applies filters on the first page and exports all matching rows with the same filters", async () => {
  const person = userEvent.setup();
  renderScreen(<AuditLogPage />);
  await screen.findByText("Lee Cruz");
  await screen.findByRole("option", { name: "New Version Submitted" });
  await person.selectOptions(screen.getByRole("combobox", { name: "Event type" }), "RESUBMITTED");
  await person.type(screen.getByLabelText("Record ID"), "3");
  await person.type(screen.getByLabelText("From date"), "2026-10-01");
  await person.type(screen.getByLabelText("To date"), "2026-10-30");
  await person.click(screen.getByRole("button", { name: "Filter" }));
  await waitFor(() => expect(auditApi.list).toHaveBeenLastCalledWith({
    event_type: "RESUBMITTED", record: 3, user: undefined, from: "2026-10-01", to: "2026-10-30", page: 1, page_size: 20,
  }));
  vi.mocked(auditApi.exportCsv).mockRejectedValue(new Error("Offline"));
  await person.click(screen.getByRole("button", { name: "Export CSV" }));
  expect(auditApi.exportCsv).toHaveBeenCalledWith({
    event_type: "RESUBMITTED", record: 3, user: undefined, from: "2026-10-01", to: "2026-10-30",
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not export");
});

it("reports failed loads and empty metadata without inventing history", async () => {
  vi.mocked(auditApi.list).mockRejectedValue(new Error("Offline"));
  renderScreen(<AuditLogPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load");
  expect(screen.getByText(/missing events do not prove/)).toBeInTheDocument();
});

it("downloads the CSV returned by the API", async () => {
  const createObjectURL = vi.fn().mockReturnValue("blob:audit-download");
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const file = new Blob(["created_at,event_type\n"], { type: "text/csv" });
  vi.mocked(auditApi.exportCsv).mockResolvedValue({ data: file } as Awaited<ReturnType<typeof auditApi.exportCsv>>);
  renderScreen(<AuditLogPage />);
  await screen.findByText("Lee Cruz");
  await userEvent.setup().click(screen.getByRole("button", { name: "Export CSV" }));
  expect(createObjectURL).toHaveBeenCalledWith(file);
  expect(click).toHaveBeenCalledOnce();
  expect(click.mock.instances[0]).toHaveAttribute("download", "iris-audit.csv");
});

