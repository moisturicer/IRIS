import { useState, type ReactNode } from "react";
import { recordsApi } from "@/api/records";
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

export default function ImportRecordsPage() {
  const [file,   setFile]   = useState<File | null>(null);
  const [log,    setLog]    = useState("");
  const [loading,setLoading]= useState(false);

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    setLog("Importing...");
    try {
      const { data } = await recordsApi.importExcel(file);
      setLog(data.log ?? "Import complete.");
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

  return (
    <div>
      <PageHeader title="Import Records" description="Add papers that were finished before IRIS, in one batch, from a spreadsheet." />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <StepCard n={1} title="Get the template">
          <p>One row per paper, in the format of the template.</p>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={handleDownloadTemplate}>
            <i className="fas fa-download" aria-hidden />
            Download template
          </Button>
        </StepCard>
        <StepCard n={2} title="Fill it in">
          <p>
            Duplicate a row for each paper and replace the values. The import stops at a merged cell
            containing <strong>END OF RECORDS</strong>.
          </p>
        </StepCard>
        <StepCard n={3} title="Upload">
          <p>Upload the spreadsheet (.xls or .xlsx), then press Generate to import it.</p>
        </StepCard>
      </div>

      <div className="mt-6 mb-4 rounded-card border border-stone-200 bg-white p-6">
        <label
          className="block cursor-pointer rounded-card border-2 border-dashed border-stone-200 p-6 text-center transition-colors hover:border-brand"
        >
          <i className="fas fa-cloud-upload-alt mb-2 text-3xl text-stone-300" aria-hidden />
          <p className="text-body font-semibold text-stone-600">
            {file ? file.name : "Click to choose a file"}
          </p>
          <p className="mt-1 text-label text-stone-500">Supports .xls and .xlsx</p>
          <input
            type="file"
            accept=".xls,.xlsx"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="mt-4 flex justify-end">
          <Button
            type="button"
            loading={loading}
            disabled={!file}
            disabledReason="Choose a spreadsheet to import."
            onClick={handleImport}
          >
            {!loading && <i className="fas fa-cogs" aria-hidden />}
            {loading ? "Importing..." : "Generate"}
          </Button>
        </div>
      </div>

      {/* Log */}
      <div className="bg-white rounded-card border border-stone-200 p-6">
        <p className="text-body font-semibold text-stone-800 mb-3 flex items-center gap-2">
          <i className="fas fa-terminal text-brand" aria-hidden /> Import Log
        </p>
        <textarea
          readOnly
          aria-label="Import log"
          rows={8}
          value={log}
          className="w-full font-mono text-small bg-stone-50 border border-field rounded-control p-3 text-stone-600 resize-y"
        />
      </div>
    </div>
  );
}
