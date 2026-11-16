import { useState, type ReactNode } from "react";
import { recordsApi, type ImportAnswer } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { downloadBlob } from "@/lib/utils";

function StepCard({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="rounded-card border border-stone-200 bg-white p-5">
      <h2 className="flex items-center gap-2 text-body font-semibold text-stone-800">
        <span
          aria-hidden
          className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-brand text-label font-semibold text-white"
        >
          {n}
        </span>
        {title}
      </h2>
      <div className="mt-2 text-small text-stone-600">{children}</div>
    </div>
  );
}

/** What a check found: how many rows would go in, and for each row that would not, why. */
function CheckResult({ answer }: { answer: ImportAnswer }) {
  const rows = answer.rows ?? [];
  const ok = answer.ok ?? 0;
  const skipped = answer.skipped ?? 0;
  const unused = answer.unused_pdfs ?? [];
  return (
    <section aria-labelledby="import-check-title" className="mb-4 rounded-card border border-stone-200 bg-white p-6">
      <h2 id="import-check-title" className="text-body font-semibold text-stone-800">Check result</h2>
      <p role="status" className="mt-1 text-small text-stone-600">
        {ok} {ok === 1 ? "row is" : "rows are"} ready to import; {skipped} will be skipped.
      </p>
      {(answer.errors ?? []).map((message) => (
        <p key={message} className="mt-2 text-small text-brand">{message}</p>
      ))}
      {rows.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-small">
            <caption className="sr-only">Every row of the file and whether it can be imported</caption>
            <thead>
              <tr className="border-b border-stone-200 text-left text-stone-600">
                <th scope="col" className="px-3 py-2 font-semibold">Row</th>
                <th scope="col" className="px-3 py-2 font-semibold">Paper</th>
                <th scope="col" className="px-3 py-2 font-semibold">PDF</th>
                <th scope="col" className="px-3 py-2 font-semibold">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {rows.map((r) => (
                <tr key={r.row}>
                  <td className="px-3 py-2 tabular-nums">{r.row}</td>
                  <td className="px-3 py-2">{r.title || <span className="italic text-stone-500">No title</span>}</td>
                  <td className="px-3 py-2">{r.file_name || "—"}</td>
                  <td className="px-3 py-2">
                    {r.problems.length === 0 ? "Ready" : `Skipped: ${r.problems.join("; ")}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {unused.length > 0 && (
        <p className="mt-3 text-small text-stone-600">
          Not named by any row, so not imported: {unused.join(", ")}.
        </p>
      )}
    </section>
  );
}

export default function ImportRecordsPage() {
  const [file,    setFile]    = useState<File | null>(null);
  const [pdfs,    setPdfs]    = useState<File[]>([]);
  // What a check found, or that the check itself failed. Either is dropped the
  // moment the sheet or the PDFs change, so Generate never runs on a check of
  // something else.
  const [checked, setChecked] = useState<ImportAnswer | null>(null);
  const [checkFailed, setCheckFailed] = useState(false);
  const [checking, setChecking] = useState(false);
  const [log,     setLog]     = useState("");
  const [loading, setLoading] = useState(false);

  const forget = () => { setChecked(null); setCheckFailed(false); };

  const handleCheck = async () => {
    if (!file) return;
    setChecking(true);
    forget();
    try {
      const { data } = await recordsApi.importExcel(file, { pdfs, check: true });
      setChecked(data);
    } catch {
      setCheckFailed(true);
    } finally {
      setChecking(false);
    }
  };

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    setLog("Importing...");
    try {
      const { data } = await recordsApi.importExcel(file, { pdfs });
      setLog(data.log ?? "Import complete.");
      forget();
    } catch {
      setLog("Import failed. Check the file format and try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadTemplate = async () => {
    const { data } = await recordsApi.downloadTemplate();
    downloadBlob(data, "iris_import_template.xlsx");
  };

  const ready = checked?.ok ?? 0;
  const generateBlocked = !file
    ? "Choose a spreadsheet to import."
    : !checked
      ? "Check the file first."
      : ready === 0
        ? "No row in the file can be imported."
        : undefined;

  return (
    <div>
      <PageHeader
        title="Import Records"
        description="Add papers that were finished before IRIS, in one batch. IRIS checks every row before anything is added."
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <StepCard n={1} title="Get the template">
          <p>One row per paper, in the format of the template.</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={handleDownloadTemplate}>
            <i className="fas fa-download" aria-hidden />
            Download the template (.xlsx)
          </Button>
        </StepCard>
        <StepCard n={2} title="Fill it in">
          <p>
            Keep the column names. Authors are separated by semicolons or commas. Put each PDF&apos;s name in{" "}
            <strong>File Name</strong>. The import stops at a merged cell containing <strong>END OF RECORDS</strong>.
          </p>
        </StepCard>
        <StepCard n={3} title="Upload">
          <p>Upload the sheet (.xls, .xlsx or .csv) and the PDFs together, check them, then press Generate.</p>
        </StepCard>
      </div>

      <div className="mt-6 mb-4 rounded-card border border-stone-200 bg-white p-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label
            className="block cursor-pointer rounded-card border-2 border-dashed border-stone-200 p-6 text-center transition-colors hover:border-brand"
          >
            <i className="fas fa-cloud-upload-alt mb-2 text-3xl text-stone-300" aria-hidden />
            <p className="text-body font-semibold text-stone-600">
              {file ? file.name : "Click to choose a file"}
            </p>
            <p className="mt-1 text-label text-stone-500">Supports .xls, .xlsx and .csv</p>
            <input
              type="file"
              accept=".xls,.xlsx,.csv"
              className="hidden"
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); forget(); }}
            />
          </label>

          <label
            className="block cursor-pointer rounded-card border-2 border-dashed border-stone-200 p-6 text-center transition-colors hover:border-brand"
          >
            <i className="fas fa-file-pdf mb-2 text-3xl text-stone-300" aria-hidden />
            <p className="text-body font-semibold text-stone-600">
              {pdfs.length > 0
                ? `${pdfs.length} PDF${pdfs.length === 1 ? "" : "s"} chosen`
                : "Choose the PDFs (optional)"}
            </p>
            <p className="mt-1 text-label text-stone-500">The ones the File Name column names</p>
            <input
              type="file"
              accept=".pdf,application/pdf"
              multiple
              className="hidden"
              onChange={(e) => { setPdfs(Array.from(e.target.files ?? [])); forget(); }}
            />
          </label>
        </div>

        <div className="mt-4 flex flex-wrap justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            loading={checking}
            disabled={!file}
            disabledReason="Choose a spreadsheet to check."
            onClick={handleCheck}
          >
            {checking ? "Checking..." : "Check file"}
          </Button>
          <Button
            type="button"
            loading={loading}
            disabled={generateBlocked !== undefined}
            disabledReason={generateBlocked}
            onClick={handleImport}
          >
            {!loading && <i className="fas fa-cogs" aria-hidden />}
            {loading ? "Importing..." : "Generate"}
          </Button>
        </div>
      </div>

      {checkFailed && (
        <p role="alert" className="mb-4 rounded-card border border-stone-200 bg-white p-4 text-small text-stone-700">
          The file could not be checked. Check the file format and try again.
        </p>
      )}

      {checked && <CheckResult answer={checked} />}

      {/* The log, once an import has written to it (audit US-14). */}
      {log && (
      <div className="bg-white rounded-card border border-stone-200 p-6">
        <p className="text-body font-semibold text-stone-800 mb-3 flex items-center gap-2">
          <i className="fas fa-terminal text-brand" aria-hidden /> Import log
        </p>
        <textarea
          readOnly
          aria-label="Import log"
          rows={8}
          value={log}
          className="w-full font-mono text-small bg-stone-50 border border-field rounded-control p-3 text-stone-600 resize-y"
        />
      </div>
      )}
    </div>
  );
}
