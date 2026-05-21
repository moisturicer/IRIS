export type AuditEventType = "LOGIN" | "LOGOUT" | "ACCESS" | "UPLOAD" | "DOWNLOAD" | "DELETE" | "RENAME";

export interface AuditEvent {
  id:            number;
  event_type:    AuditEventType;
  user:          number | null;
  user_name:     string | null;
  /** Formatted display string: "username (Full Name)" -- used in the table column */
  user_display:  string | null;
  record:        number | null;
  record_title:  string | null;
  metadata:      Record<string, unknown>;
  created_at:    string;
}
