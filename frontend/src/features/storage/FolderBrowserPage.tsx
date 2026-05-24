/**
 * File storage / folder browser page.
 * Mirrors the old file_management folder/subfolder structure.
 * TODO: wire drag-and-drop reorder once backend supports it.
 * TODO: add breadcrumb for deep navigation.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { storageApi }   from "@/api/storage";
import { PageHeader }   from "@/components/layout/PageHeader";
import { EmptyState }   from "@/components/shared/EmptyState";
import { Button }       from "@/components/ui/Button";
import { Modal }        from "@/components/ui/Modal";
import { Input }        from "@/components/ui/Input";
import { useUIStore }   from "@/store/ui.store";
import { formatDate }   from "@/lib/utils";
import type { StorageFolder, StorageFile } from "@/types/storage";

// TODO: add types/storage.ts with StorageFolder and StorageFile types

export default function FolderBrowserPage() {
  const { folderId } = useParams<{ folderId?: string }>();
  const navigate   = useNavigate();
  const addToast   = useUIStore((s) => s.addToast);

  const [folders, setFolders]   = useState<StorageFolder[]>([]);
  const [files, setFiles]       = useState<StorageFile[]>([]);
  const [loading, setLoading]   = useState(true);
  const [breadcrumb, setBreadcrumb] = useState<{ id: number; name: string }[]>([]);

  // Create folder modal
  const [createOpen, setCreateOpen]   = useState(false);
  const [folderName, setFolderName]   = useState("");
  const [creating, setCreating]       = useState(false);

  const load = () => {
    setLoading(true);
    const parentId = folderId ? Number(folderId) : undefined;
    storageApi
      .list(parentId)
      .then(({ data }) => {
        setFolders(data.folders);
        setFiles(data.files);
        setBreadcrumb(data.breadcrumb ?? []);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [folderId]);

  const handleCreateFolder = async () => {
    if (!folderName.trim()) return;
    setCreating(true);
    try {
      await storageApi.createFolder({ name: folderName.trim(), parent: folderId ? Number(folderId) : null });
      addToast({ type: "success", message: "Folder created." });
      setFolderName("");
      setCreateOpen(false);
      load();
    } catch {
      addToast({ type: "error", message: "Could not create folder." });
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteFolder = async (id: number, name: string) => {
    if (!confirm(`Delete folder "${name}" and all its contents?`)) return;
    try {
      await storageApi.deleteFolder(id);
      addToast({ type: "success", message: "Folder deleted." });
      load();
    } catch {
      addToast({ type: "error", message: "Delete failed." });
    }
  };

  return (
    <div>
      <PageHeader
        title="File Storage"
        description="Organize and manage your uploaded files."
        actions={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <i className="fa fa-folder-plus" /> New Folder
          </Button>
        }
      />

      {/* Breadcrumb */}
      {breadcrumb.length > 0 && (
        <nav className="flex items-center gap-1 text-[13px] mb-4 text-gray-500">
          <button onClick={() => navigate("/storage")} className="hover:text-[#6B0F12]">
            Storage
          </button>
          {breadcrumb.map((crumb, idx) => (
            <span key={crumb.id} className="flex items-center gap-1">
              <i className="fa fa-chevron-right text-[10px]" />
              {idx === breadcrumb.length - 1 ? (
                <span className="text-gray-900 font-medium">{crumb.name}</span>
              ) : (
                <button
                  onClick={() => navigate(`/storage/${crumb.id}`)}
                  className="hover:text-[#6B0F12]"
                >
                  {crumb.name}
                </button>
              )}
            </span>
          ))}
        </nav>
      )}

      {loading ? (
        <div className="p-8 text-center text-gray-400 text-[13px]">Loading...</div>
      ) : folders.length === 0 && files.length === 0 ? (
        <EmptyState icon="fa-folder-open" title="This folder is empty." />
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Modified</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Size</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {/* Folders */}
              {folders.map((f) => (
                <tr key={`folder-${f.id}`} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <button
                      onClick={() => navigate(`/storage/${f.id}`)}
                      className="flex items-center gap-2 text-gray-800 hover:text-[#6B0F12]"
                    >
                      <i className="fa fa-folder text-yellow-400 text-[15px]" />
                      {f.name}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(f.updated_at)}</td>
                  <td className="px-4 py-3 text-gray-400">--</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDeleteFolder(f.id, f.name)}
                      className="text-gray-400 hover:text-red-500 text-[12px]"
                    >
                      <i className="fa fa-trash" />
                    </button>
                  </td>
                </tr>
              ))}
              {/* Files */}
              {files.map((f) => (
                <tr key={`file-${f.id}`} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <a
                      href={f.file_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center gap-2 text-gray-800 hover:text-[#6B0F12]"
                    >
                      <i className="fa fa-file text-gray-400 text-[15px]" />
                      {f.name}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(f.uploaded_at)}</td>
                  <td className="px-4 py-3 text-gray-500">{f.size_display}</td>
                  <td className="px-4 py-3 text-right">
                    <a
                      href={f.file_url}
                      download
                      className="text-gray-400 hover:text-[#6B0F12] text-[12px] mr-3"
                    >
                      <i className="fa fa-download" />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create folder modal */}
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="New Folder">
        <div className="flex flex-col gap-4">
          <Input
            label="Folder name"
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreateFolder()}
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button loading={creating} onClick={handleCreateFolder}>Create</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
