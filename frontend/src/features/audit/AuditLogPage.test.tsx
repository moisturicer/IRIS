import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { auditApi } from "@/api/audit";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import AuditLogPage from "./AuditLogPage";
import { expectNoBlockingA11yViolations } from "@/test/axe";

vi.mock("@/api/audit", () => ({ auditApi: { list: vi.fn(), exportCsv: vi.fn() } }));

beforeEach(() => {
  vi.clearAllMocks();
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
  expect(screen.getByRole("option", { name: "Assignment Deadline Extended" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Water study" })).toHaveAttribute("href", "/records/3");
  const { readFileSync } = await vi.importActual<{ readFileSync: (path: string, encoding: string) => string }>("node:fs");
  const backendAuditModel = readFileSync("../backend/apps/audit/models.py", "utf8");
  const choices = [...backendAuditModel.matchAll(/^\s+\(([A-Z_]+),\s+"([^"]+)"\),/gm)];
  expect(choices.length).toBeGreaterThan(30);
  for (const [, type, name] of choices) {
    expect(screen.getByRole("option", { name })).toHaveValue(type);
  }
  await expectNoBlockingA11yViolations(container);
});

it("applies filters on the first page and exports all matching rows with the same filters", async () => {
  const person = userEvent.setup();
  renderScreen(<AuditLogPage />);
  await screen.findByText("Lee Cruz");
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
