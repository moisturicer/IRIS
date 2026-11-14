import { useState } from "react";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { downloadBlob } from "@/lib/utils";

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
      <PageHeader title="Import Records" description="Migrate research records in bulk using a formatted spreadsheet." />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* Instructions */}
        <div className="bg-white rounded-xl border border-stone-200 p-6">
          <p className="text-[14px] font-semibold text-stone-800 mb-3 flex items-center gap-2">
            <i className="fas fa-info-circle text-brand" aria-hidden /> Instructions
          </p>
          <ol className="list-decimal pl-4 space-y-2 text-[14px] text-stone-600">
            <li>Follow the data entry format in the template below.</li>
            <li>To add a new entry, duplicate a row and replace the values.</li>
            <li>The migration stops when it reads a merged cell containing <strong>END OF RECORDS</strong>.</li>
            <li>Press <strong>Generate</strong> to import.</li>
          </ol>
          <Button type="button" variant="outline" size="sm" className="mt-4" onClick={handleDownloadTemplate}>
            <i className="fas fa-download" aria-hidden />
            Download template
          </Button>
        </div>

        {/* Upload */}
        <div className="bg-white rounded-xl border border-stone-200 p-6">
          <p className="text-[14px] font-semibold text-stone-800 mb-3 flex items-center gap-2">
            <i className="fas fa-file-upload text-brand" aria-hidden /> Upload Spreadsheet
          </p>
          <label
            className="block border-2 border-dashed border-stone-200 rounded-xl p-6 text-center cursor-pointer hover:border-brand transition-colors"
          >
            <i className="fas fa-cloud-upload-alt text-3xl text-stone-300 mb-2" aria-hidden />
            <p className="text-[14px] font-semibold text-stone-600">
              {file ? file.name : "Click to choose a file"}
            </p>
            <p className="text-[12px] text-stone-500 mt-1">Supports .xls and .xlsx</p>
            <input
              type="file"
              accept=".xls,.xlsx"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>

          <Button
            type="button"
            size="full"
            className="mt-4"
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
      <div className="bg-white rounded-xl border border-stone-200 p-6">
        <p className="text-[14px] font-semibold text-stone-800 mb-3 flex items-center gap-2">
          <i className="fas fa-terminal text-brand" aria-hidden /> Import Log
        </p>
        <textarea
          readOnly
          aria-label="Import log"
          rows={8}
          value={log}
          className="w-full font-mono text-[13px] bg-stone-50 border border-stone-200 rounded-lg p-3 text-stone-600 resize-y"
        />
      </div>
    </div>
  );
}
