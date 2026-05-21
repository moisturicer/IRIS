export interface StorageFolder {
  id:         number;
  name:       string;
  parent:     number | null;
  created_by: number;
  updated_at: string;
  created_at: string;
}

export interface StorageFile {
  id:          number;
  name:        string;
  folder:      number | null;
  file_url:    string;
  size_bytes:  number;
  size_display: string;     // e.g. "2.4 MB" -- formatted by backend
  uploaded_by: number;
  uploaded_at: string;
}

export interface StorageListing {
  folders:    StorageFolder[];
  files:      StorageFile[];
  breadcrumb: { id: number; name: string }[];
}
