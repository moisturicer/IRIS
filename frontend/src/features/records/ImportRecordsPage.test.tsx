/**
 * Import Records' buttons (IR-1088): both are the one Button, and Generate says
 * what it is waiting for.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "@/api/records";
import * as utils from "@/lib/utils";
import { renderScreen, screen, userEvent } from "@/test/render";

import ImportRecordsPage from "./ImportRecordsPage";

afterEach(() => vi.restoreAllMocks());

describe("Import Records", () => {
  it("shows Generate as a pill that says a spreadsheet is needed, until one is chosen", async () => {
    const user = userEvent.setup();
    renderScreen(<ImportRecordsPage />);

    const generate = screen.getByRole("button", { name: "Generate" });
    expect(generate).toBeDisabled();
    expect(generate).toHaveClass("rounded-full");
    expect(generate).toHaveAccessibleDescription("Choose a spreadsheet to import.");

    await user.upload(screen.getByLabelText(/Click to choose a file/), new File(["x"], "records.xlsx"));

    expect(screen.getByRole("button", { name: "Generate" })).toBeEnabled();
    expect(screen.queryByText("Choose a spreadsheet to import.")).not.toBeInTheDocument();
  });

  it("downloads the template from a button, not from a link inside a sentence", async () => {
    const user = userEvent.setup();
    const blob = new Blob(["x"]);
    vi.spyOn(recordsApi, "downloadTemplate").mockResolvedValue({ data: blob } as never);
    const save = vi.spyOn(utils, "downloadBlob").mockImplementation(() => undefined);
    renderScreen(<ImportRecordsPage />);

    const download = screen.getByRole("button", { name: "Download template" });
    expect(download).toHaveClass("rounded-full");
    await user.click(download);

    expect(save).toHaveBeenCalledWith(blob, "iris_import_template.xlsx");
  });
});
