import type { PipelineStatus } from "@/lib/constants";

export interface RecordOwner {
  id:         number;
  user:       number;
  email:      string;
  full_name:  string;
  is_primary: boolean;
}

export interface Author {
  id:   number;
  name: string;
  role: number | null;
}

export interface RecordListItem {
  id:                    number;
  title:                 string;
  abstract:              string;
  year_accomplished:     number | null;
  classification_name:   string | null;
  record_type_name:      string | null;
  pipeline_status:       PipelineStatus;
  is_ip:                 boolean;
  for_commercialization: boolean;
  community_extension:   boolean;
  access_count:          number;
  created_at:            string;
  authors:               Author[];
}

export interface RecordDetail extends RecordListItem {
  year_completed:  number | null;
  abstract:        string;
  abstract_file:   string | null;
  classification:  number | null;
  psced:           number | null;
  record_type:     number | null;
  adviser:         number | null;
  added_by:        number | null;
  owners:          RecordOwner[];
  is_deleted:      boolean;
}

export interface RecordFormData {
  title:                 string;
  year_accomplished?:    number;
  year_completed?:       number;
  abstract?:             string;
  classification?:       number;
  psced?:                number;
  record_type?:          number;
  adviser?:              number;
  is_ip?:                boolean;
  for_commercialization?: boolean;
  community_extension?:  boolean;
}

export interface Classification {
  id:   number;
  name: string;
}

export interface PSCEDClassification {
  id:   number;
  name: string;
}

export interface RecordType {
  id:   number;
  name: string;
}

export interface DownloadRequest {
  id:          number;
  record:      number;
  requested_by:number;
  status:      "pending" | "approved" | "declined";
  created_at:  string;
}

export interface DeleteRequest {
  id:          number;
  record:      number;
  requested_by:number;
  reason:      string;
  status:      "pending" | "approved" | "declined";
  created_at:  string;
}
