export interface Notification {
  id:                number;
  notif_type:        number;
  notif_type_name:   string;
  message:           string;
  record:            number | null;
  record_title:      string | null;
  sender:            number | null;
  sender_name:       string | null;
  recipient:         number | null;
  broadcast_to_role: number | null;
  created_at:        string;
  is_read:           boolean;
}
