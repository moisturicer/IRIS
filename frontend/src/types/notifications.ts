export interface Notification {
  id:                number;
  notif_type:        number;
  notif_type_name:   string;
  message:           string;
  /** Set client-side after mark-read; optional from API when added. */
  is_read?:          boolean;
  record:            number | null;
  record_title:      string | null;
  sender:            number | null;
  sender_name:       string | null;
  recipient:         number | null;
  broadcast_to_role: number | null;
  created_at:        string;
}
