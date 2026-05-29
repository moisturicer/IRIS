export interface UploadSlot {
  id:          number;
  name:        string;
  record_type: number;
  is_required: boolean;
}

export interface UploadReview {
  id:           number;
  upload:       number;
  reviewed_by:  number;
  reviewer_name:string;
  status:       number | null;
  comment:      string;
  created_at:   string;
}

export interface RecordUpload {
  id:               number;
  record:           number;
  slot:             number;
  slot_name:        string;
  file:             string;
  version:          number;
  status:           string | null;    // "approved" | "pending" | "declined" etc.
  status_name:      string | null;
  uploaded_by:      number | null;
  uploaded_by_name: string | null;    // denormalized display name
  created_at:       string;
  reviews:          UploadReview[];
}

/** UploadSlot with its uploads for a specific record -- returned by slotsForRecord() */
export interface SlotWithUploads extends UploadSlot {
  uploads: RecordUpload[];
}

export interface RecordFile {
  id:               number;
  record:           number;
  file:             string;
  filename:         string;
  uploaded_by:      number | null;
  uploaded_by_name: string | null;
  created_at:       string;
}
