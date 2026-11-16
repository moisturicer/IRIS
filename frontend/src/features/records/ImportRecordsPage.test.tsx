/**
 * Import Records' buttons (IR-1088): both are the one Button, and Generate says
 * what it is waiting for.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "@/api/records";
import * as utils from "@/lib/utils";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import ImportRecordsPage from "./ImportRecordsPage";

afterEach(() => vi.restoreAllMocks());

describe("Import Records", () => {
  it("shows Generate as a pill that says what it is waiting for: a sheet, then a check", async () => {
    const user = userEvent.setup();
    renderScreen(<ImportRecordsPage />);

    const generate = screen.getByRole("button", { name: "Generate" });
    expect(generate).toBeDisabled();
    expect(generate).toHaveClass("rounded-full");
    expect(generate).toHaveAccessibleDescription("Choose a spreadsheet to import.");

    await user.upload(screen.getByLabelText(/Click to choose a file/), new File(["x"], "records.xlsx"));

    expect(screen.getByRole("button", { name: "Check file" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generate" })).toHaveAccessibleDescription("Check the file first.");
  });

  it("downloads the template from a button, not from a link inside a sentence", async () => {
    const user = userEvent.setup();
    const blob = new Blob(["x"]);
    vi.spyOn(recordsApi, "downloadTemplate").mockResolvedValue({ data: blob } as never);
    const save = vi.spyOn(utils, "downloadBlob").mockImplementation(() => undefined);
    renderScreen(<ImportRecordsPage />);

    const download = screen.getByRole("button", { name: "Download the template (.xlsx)" });
    expect(download).toHaveClass("rounded-full");
    await user.click(download);

    expect(save).toHaveBeenCalledWith(blob, "iris_import_template.xlsx");
  });

  const CHECK = {
    check: true as const,
    ok: 1,
    skipped: 1,
    errors: [],
    unused_pdfs: ["spare.pdf"],
    rows: [
      { row: 2, title: "Good paper", file_name: "good.pdf", problems: [] },
      { row: 3, title: "", file_name: "", problems: ["Title is required"] },
    ],
  };

  async function chooseAndCheck(user: ReturnType<typeof userEvent.setup>) {
    await user.upload(screen.getByLabelText(/Click to choose a file/), new File(["x"], "records.csv"));
    await user.upload(screen.getByLabelText(/Choose the PDFs/), [new File(["%PDF"], "good.pdf", { type: "application/pdf" })]);
    await user.click(screen.getByRole("button", { name: "Check file" }));
  }

  it("checks the sheet and its PDFs first, lists every row, and only then offers Generate (IR-1138)", async () => {
    const user = userEvent.setup();
    const importExcel = vi.spyOn(recordsApi, "importExcel").mockResolvedValue({ data: CHECK } as never);
    renderScreen(<ImportRecordsPage />);

    await chooseAndCheck(user);

    expect(importExcel).toHaveBeenCalledWith(expect.any(File), { pdfs: [expect.any(File)], check: true });
    expect(await screen.findByRole("status")).toHaveTextContent("1 row is ready to import; 1 will be skipped.");
    const table = screen.getByRole("table", { name: /Every row of the file/ });
    expect(within(table).getByRole("row", { name: /Good paper.*Ready/ })).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /No title.*Skipped: Title is required/ })).toBeInTheDocument();
    expect(screen.getByText(/Not named by any row, so not imported: spare\.pdf/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();
  });

  it("imports with the same files after a check, and asks for a new check when they change", async () => {
    const user = userEvent.setup();
    const importExcel = vi.spyOn(recordsApi, "importExcel")
      .mockResolvedValueOnce({ data: CHECK } as never)
      .mockResolvedValueOnce({ data: { log: "Done — 1 record(s) created, 1 skipped.", created: 1, skipped: 1 } } as never);
    renderScreen(<ImportRecordsPage />);
    await chooseAndCheck(user);
    await screen.findByRole("status");
    // Audit US-14 (IR-1098): no empty Import log before there is anything in it.
    expect(screen.queryByRole("textbox", { name: "Import log" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(importExcel).toHaveBeenLastCalledWith(expect.any(File), { pdfs: [expect.any(File)] });
    expect(await screen.findByRole("textbox", { name: "Import log" })).toHaveDisplayValue(/1 record\(s\) created/);

    await user.upload(screen.getByLabelText(/Choose the PDFs|PDF.* chosen/), [new File(["%PDF"], "other.pdf", { type: "application/pdf" })]);
    expect(screen.queryByRole("table", { name: /Every row of the file/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  it("keeps Generate off when no row can be imported", async () => {
    const user = userEvent.setup();
    vi.spyOn(recordsApi, "importExcel").mockResolvedValue({ data: { ...CHECK, ok: 0, skipped: 2 } } as never);
    renderScreen(<ImportRecordsPage />);

    await chooseAndCheck(user);
    await screen.findByRole("status");

    const generate = screen.getByRole("button", { name: "Generate" });
    expect(generate).toBeDisabled();
    expect(generate).toHaveAccessibleDescription("No row in the file can be imported.");
  });

  it("says so when the check itself fails, and offers no Generate", async () => {
    const user = userEvent.setup();
    vi.spyOn(recordsApi, "importExcel").mockRejectedValue(new Error("down"));
    renderScreen(<ImportRecordsPage />);

    await chooseAndCheck(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("The file could not be checked.");
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });
});
