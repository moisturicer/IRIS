import { useState } from "react";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
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
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <p className="text-[13px] font-semibold text-gray-800 mb-3 flex items-center gap-2">
            <i className="fas fa-info-circle text-[#6B0F12]" /> Instructions
          </p>
          <ol className="list-decimal pl-4 space-y-2 text-[13px] text-gray-600">
            <li>Follow the data entry format -- <button onClick={handleDownloadTemplate} className="text-[#6B0F12] font-semibold hover:underline">download template here</button>.</li>
            <li>To add a new entry, duplicate a row and replace the values.</li>
            <li>The migration stops when it reads a merged cell containing <strong>END OF RECORDS</strong>.</li>
            <li>Press <strong>Generate</strong> to import.</li>
          </ol>
        </div>

        {/* Upload */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <p className="text-[13px] font-semibold text-gray-800 mb-3 flex items-center gap-2">
            <i className="fas fa-file-upload text-[#6B0F12]" /> Upload Spreadsheet
          </p>
          <label
            className="block border-2 border-dashed border-gray-200 rounded-xl p-6 text-center cursor-pointer hover:border-[#6B0F12] transition-colors"
          >
            <i className="fas fa-cloud-upload-alt text-3xl text-gray-300 mb-2" />
            <p className="text-[13px] font-semibold text-gray-600">
              {file ? file.name : "Click to choose a file"}
            </p>
            <p className="text-[11px] text-gray-400 mt-1">Supports .xls and .xlsx</p>
            <input
              type="file"
              accept=".xls,.xlsx"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>

          <button
            onClick={handleImport}
            disabled={!file || loading}
            className="mt-4 w-full bg-[#6B0F12] text-white py-2.5 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215] disabled:opacity-50"
          >
            <i className="fas fa-cogs mr-1.5" />
            {loading ? "Importing..." : "Generate"}
          </button>
        </div>
      </div>

      {/* Log */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <p className="text-[13px] font-semibold text-gray-800 mb-3 flex items-center gap-2">
          <i className="fas fa-terminal text-[#6B0F12]" /> Import Log
        </p>
        <textarea
          readOnly
          rows={8}
          value={log}
          className="w-full font-mono text-[12px] bg-gray-50 border border-gray-200 rounded-lg p-3 text-gray-600 resize-y"
        />
      </div>
    </div>
  );
}
