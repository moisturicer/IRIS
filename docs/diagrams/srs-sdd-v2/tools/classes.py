"""C-*: class diagrams for SDD v2 §3, per feature group (v1 had one per feature).

Models show their fields; service modules are drawn as classes whose
operations are the module's functions (the upper box is empty for a module).
Workflow (§3.3.1–3.3.4) reuses D-20 and the AI runtime (§3.5.4–3.5.5) D-21.
"""

C = "at 2d8d4e4a (IR-1275)."
MOD = {"stereotype": "module"}
VIEW = {"stereotype": "view"}


def fig(fid, sec, name, src, nodes, columns, edges, **kw):
    return {"title": f"C-{fid}  Classes: {name}", "caption": f"SDD v2 §{sec}. From {src} {C}",
            "nodes": nodes, "columns": columns, "edges": edges, **kw}


FIGURES = {
    "C-1.1-sign-up": fig("1.1", "3.1.1, 3.1.4", "sign-up, notice and recovery",
        "apps/accounts (models.py, views.py, notice.py, recovery/)", [
        ("RegisterView", [], ["post(request)"], VIEW),
        ("User", ["email", "role → Role", "is_verified", "ai_consent", "answered_notice_version", "credential_version"]),
        ("DataNotice", ["number", "title", "sections", "published_at"]),
        ("NoticeAnswer", ["user → User", "notice → DataNotice", "agreed_dpa", "ai_consent", "answered_at"]),
        ("recovery.service", [], ["admit_request()", "enqueue()", "confirm_verification()", "confirm_reset()"], MOD),
        ("RecoveryToken", ["digest", "user → User", "purpose", "expires_at", "consumed_at"]),
        ("RecoveryIntent", ["purpose", "recipient", "status", "attempts", "next_attempt_at"]),
    ], [["RegisterView", "recovery.service"], ["User", "RecoveryToken"], ["NoticeAnswer", "DataNotice", "RecoveryIntent"]], [
        ("RegisterView", "User", "uses"), ("RegisterView", "NoticeAnswer", "uses"),
        ("User", "NoticeAnswer", "owns"), ("NoticeAnswer", "DataNotice", "assoc"),
        ("recovery.service", "RecoveryToken", "uses"), ("recovery.service", "RecoveryIntent", "uses"),
        ("RecoveryToken", "User", "assoc"),
    ]),
    "C-1.2-sessions": fig("1.2", "3.1.2", "sessions and the refresh cookie",
        "apps/accounts (views.py, sessions.py, refresh_cookie.py, authentication.py), simplejwt", [
        ("LoginView", [], ["post(request)"], VIEW),
        ("RefreshView", [], ["post(request)"], VIEW),
        ("LogoutView", [], ["post(request)"], VIEW),
        ("refresh_cookie", [], ["require_first_party()", "read()", "set_cookie()", "clear_cookie()"], MOD),
        ("sessions", [], ["start_session()", "touch()", "check_open()", "end_session()", "end_all_sessions()"], MOD),
        ("UserSession", ["id (sid)", "user → User", "last_activity_at", "remembered", "expires_at", "ended_reason"]),
        ("OutstandingToken", ["jti", "user → User", "expires_at"]),
        ("BlacklistedToken", ["token → OutstandingToken", "blacklisted_at"]),
    ], [["LoginView", "RefreshView", "LogoutView"], ["refresh_cookie", "sessions"], ["UserSession", "OutstandingToken", "BlacklistedToken"]], [
        ("LoginView", "sessions", "uses"), ("RefreshView", "sessions", "uses"), ("LogoutView", "sessions", "uses"),
        ("RefreshView", "refresh_cookie", "uses"), ("LoginView", "refresh_cookie", "uses"),
        ("sessions", "UserSession", "uses"), ("BlacklistedToken", "OutstandingToken", "assoc"),
    ]),
    "C-1.3-protection": fig("1.3", "3.1.3", "lockout and throttles",
        "config/settings/base.py, core/throttling.py, apps/accounts/lockout.py, django-axes", [
        ("AnonBurstThrottle", ["scope: anon_burst"], ["allow_request()"]),
        ("UserBurstThrottle", ["scope: user_burst"], ["allow_request()"]),
        ("AnonRateThrottle", ["API_THROTTLE_ANON"], ["allow_request()"]),
        ("UserRateThrottle", ["API_THROTTLE_USER"], ["allow_request()"]),
        ("AccessAttempt", ["username", "ip_address", "failures_since_start", "attempt_time"]),
        ("lockout", [], ["lockout_response()"], MOD),
    ], [["AnonBurstThrottle", "AnonRateThrottle"], ["UserBurstThrottle", "UserRateThrottle"], ["AccessAttempt", "lockout"]], [
        ("lockout", "AccessAttempt", "uses"),
    ]),
    "C-1.5-roles": fig("1.5", "3.1.5, 3.1.6", "roles, requests and account administration",
        "core/enums.py RoleName, core/permissions.py, apps/accounts/views.py", [
        ("User", ["role → Role", "is_locked", "is_office_coordinator"]),
        ("Role", ["name (7 RoleName values)"]),
        ("RoleRequest", ["user → User", "requested_role → Role", "status", "reviewed_by"]),
        ("permissions", [], ["IsStaff / IsAdmin / IsAccountAdmin", "IsSystemAdmin", "role_change_refusal()"], MOD),
        ("UserSession", ["user → User", "ended_reason"]),
    ], [["permissions"], ["User", "UserSession"], ["Role", "RoleRequest"]], [
        ("User", "Role", "assoc"), ("RoleRequest", "User", "assoc"), ("RoleRequest", "Role", "assoc"),
        ("User", "UserSession", "owns"), ("permissions", "User", "uses"),
    ]),
    "C-1.7-data-rights": fig("1.7", "3.1.7", "personal data rights",
        "apps/accounts (deletion/, personal_data/), apps/audit/retention.py", [
        ("AccountDeletionRequest", ["user → User", "status", "decided_by", "reason"]),
        ("deletion.service", [], ["request_deletion()", "confirm_deletion()", "reject_deletion()"], MOD),
        ("deletion.blockers", [], ["blockers_for()"], MOD),
        ("personal_data.export", [], ["account()", "papers_owned()", "reading_notes()", "…"], MOD),
        ("SystemSetting", ["key", "value", "updated_by"]),
    ], [["deletion.service", "deletion.blockers"], ["AccountDeletionRequest", "personal_data.export"], ["SystemSetting"]], [
        ("deletion.service", "AccountDeletionRequest", "uses"), ("deletion.service", "deletion.blockers", "uses"),
    ]),
    "C-2.1-records": fig("2.1", "3.2.1", "records and submission",
        "apps/records (models.py, views.py, versions.py, duplicates.py, embargo.py)", [
        ("RecordViewSet", [], ["create()", "submit()", "partial_update()", "duplicate_matches()"], VIEW),
        ("Record", ["title", "record_type → RecordType", "adviser → User", "pipeline_status", "is_embargoed", "ai_consent"]),
        ("RecordOwner", ["record → Record", "user → User", "is_primary"]),
        ("RecordType", ["name", "manuscript_template"]),
        ("RecordVersion", ["number", "manuscript", "manuscript_sha256", "cause"]),
        ("versions", [], ["write_version()", "latest_version()", "served_manuscript()"], MOD),
        ("duplicates", [], ["exact_matches()", "enforce_exact()"], MOD),
    ], [["RecordViewSet", "versions", "duplicates"], ["Record", "RecordOwner"], ["RecordType", "RecordVersion"]], [
        ("RecordViewSet", "Record", "uses"), ("RecordViewSet", "versions", "uses"), ("RecordViewSet", "duplicates", "uses"),
        ("Record", "RecordOwner", "owns", {"m": "1..*"}), ("Record", "RecordVersion", "owns", {"m": "1..*"}),
        ("Record", "RecordType", "assoc"),
    ]),
    "C-2.2-requirements": fig("2.2", "3.2.2", "requirements and templates",
        "apps/documents (models.py, setup.py, adviser_templates.py)", [
        ("setup", [], ["add_requirement()", "edit_requirement()", "reorder_requirements()", "remove_requirement()", "set_requirement_template()"], MOD),
        ("RecordType", ["name", "manuscript_description", "manuscript_template"]),
        ("UploadSlot", ["name", "record_type → RecordType", "is_required", "position", "template", "hidden_at"]),
        ("AdviserTemplate", ["owner → User", "title", "file", "position"]),
    ], [["setup"], ["RecordType", "UploadSlot"], ["AdviserTemplate"]], [
        ("setup", "UploadSlot", "uses"), ("RecordType", "UploadSlot", "owns"),
    ]),
    "C-2.3-uploads": fig("2.3", "3.2.3", "upload checks",
        "apps/documents (validators.py, scanning.py, models.py)", [
        ("validators", [], ["pdf_upload_problem()", "supplementary_file_problem()"], MOD),
        ("scanning", [], ["current_scanner()", "scan_verdict()", "upload_problem()"], MOD),
        ("ClamdScanner", ["MALWARE_SCAN_HOST", "TCP 3310"], ["scan(stream) → Verdict  (zINSTREAM)"]),
        ("RecordUpload", ["record → Record", "slot → UploadSlot", "file", "version", "uploaded_by", "sent_at (null: held)"]),
        ("RecordFile", ["record → Record", "file", "party", "uploaded_by"]),
    ], [["validators", "scanning"], ["ClamdScanner"], ["RecordUpload", "RecordFile"]], [
        ("scanning", "ClamdScanner", "uses"),
    ]),
    "C-2.4-versions": fig("2.4", "3.2.4", "Versions and review text",
        "apps/records (models.py, review_text/), apps/reviews/version_comparison.py, ADR-058", [
        ("RecordVersion", ["number", "manuscript", "manuscript_sha256", "cause", "review_text → ReviewText"]),
        ("RecordVersionDocument", ["version → RecordVersion", "upload → RecordUpload"]),
        ("ReviewText", ["manuscript_sha256", "state", "reader", "page_count"]),
        ("ReviewTextSection", ["ordinal", "key", "heading", "page", "text_hash"]),
        ("version_comparison", [], ["compare(a, b)"], MOD),
    ], [["RecordVersion", "RecordVersionDocument"], ["ReviewText", "ReviewTextSection"], ["version_comparison"]], [
        ("RecordVersion", "RecordVersionDocument", "owns"), ("RecordVersion", "ReviewText", "assoc"),
        ("ReviewText", "ReviewTextSection", "owns"), ("version_comparison", "ReviewText", "uses"),
    ]),
    "C-2.5-downloads": fig("2.5", "3.2.5", "download requests and watermarks",
        "apps/records (models.py, download_service.py, watermark.py), ADR-048", [
        ("DownloadRequestViewSet", [], ["create()", "approve()", "decline()", "revoke()", "cancel()"], VIEW),
        ("DownloadRequest", ["record → Record", "requested_by → User", "status", "grant_expires_at", "note", "rdco_note"]),
        ("download_service", [], ["download_exemption()", "grant_is_live()", "decide_download_request()", "revoke_download_grant()"], MOD),
        ("watermark", [], ["watermark_pdf()"], MOD),
    ], [["DownloadRequestViewSet"], ["download_service", "watermark"], ["DownloadRequest"]], [
        ("DownloadRequestViewSet", "download_service", "uses"), ("download_service", "DownloadRequest", "uses"),
        ("download_service", "watermark", "uses"),
    ]),
    "C-2.6-delete-import": fig("2.6", "3.2.6, 3.2.7", "delete requests and Excel import",
        "apps/records (models.py, views.py, services.py)", [
        ("DeleteRequestViewSet", [], ["create()", "approve()", "decline()"], VIEW),
        ("DeleteRequest", ["record → Record", "requested_by", "status", "previous_pipeline_status", "rdco_note"]),
        ("RecordViewSet", [], ["download_template()", "import_excel()"], VIEW),
        ("services", [], ["parse_excel_import()", "check_import_row()", "check_import_pdf()"], MOD),
    ], [["DeleteRequestViewSet", "RecordViewSet"], ["DeleteRequest", "services"]], [
        ("DeleteRequestViewSet", "DeleteRequest", "uses"), ("RecordViewSet", "services", "uses"),
    ]),
    "C-3.5-doc-requests": fig("3.5", "3.3.5", "document requests",
        "apps/documents (models.py, requests.py), ADR-022", [
        ("requests", [], ["create_request()", "send_drafts()", "send_held_uploads()", "accept_item()", "reject_item()", "withdraw_request()"], MOD),
        ("DocumentRequest", ["record → Record", "assignment → RecordAssignment", "party", "state", "closed_by_decision"]),
        ("DocumentRequestItem", ["request → DocumentRequest", "slot → UploadSlot", "upload", "state", "rejection_reason"]),
    ], [["requests"], ["DocumentRequest"], ["DocumentRequestItem"]], [
        ("requests", "DocumentRequest", "uses"), ("DocumentRequest", "DocumentRequestItem", "owns", {"m": "1..*"}),
    ]),
    "C-3.6-threads": fig("3.6", "3.3.6", "review threads",
        "apps/reviews (models.py, threads.py, mentions.py, saved_replies.py), ADR-032 §7", [
        ("threads", [], ["open_must_fix()", "new_version_blocked_reason()", "resolve()", "reopen()"], MOD),
        ("ReviewComment", ["record → Record", "author", "kind", "severity", "state", "answer", "anchor_version"]),
        ("ThreadPlace", ["thread → ReviewComment", "version", "outcome", "page"]),
        ("ReviewThreadEvent", ["thread → ReviewComment", "kind", "old_value", "new_value"]),
        ("ReviewMention", ["comment → ReviewComment", "user", "notified_at"]),
        ("SavedReply", ["owner → User", "title", "body"]),
    ], [["threads", "SavedReply"], ["ReviewComment"], ["ThreadPlace", "ReviewThreadEvent", "ReviewMention"]], [
        ("threads", "ReviewComment", "uses"), ("ReviewComment", "ThreadPlace", "owns"),
        ("ReviewComment", "ReviewThreadEvent", "owns"), ("ReviewComment", "ReviewMention", "owns"),
    ]),
    "C-3.7-deadlines": fig("3.7", "3.3.7", "turnaround and reminders",
        "apps/reviews (models.py, deadlines.py, reminders.py), ADR-043", [
        ("deadlines", [], ["start_clock()", "working_days_after()", "extend()", "is_overdue()"], MOD),
        ("reminders", [], ["run_deadline_notifications()"], MOD),
        ("RecordAssignment", ["party", "due_at", "original_due_at", "document_pause_started_at"]),
        ("Turnaround", ["party", "working_days"]),
        ("Holiday", ["date", "name"]),
        ("Extension", ["assignment → RecordAssignment", "due_at", "reason", "actor"]),
        ("DeadlineMoment", ["assignment → RecordAssignment", "kind", "step", "sent_at"]),
    ], [["deadlines", "reminders"], ["RecordAssignment", "Turnaround", "Holiday"], ["Extension", "DeadlineMoment"]], [
        ("deadlines", "RecordAssignment", "uses"), ("deadlines", "Turnaround", "uses"), ("deadlines", "Holiday", "uses"),
        ("RecordAssignment", "Extension", "owns"), ("RecordAssignment", "DeadlineMoment", "owns"),
        ("reminders", "DeadlineMoment", "uses"),
    ]),
    "C-3.8-ip-embargo": fig("3.8", "3.3.8, 3.5.3", "IP and embargo on a record",
        "apps/records (models.py, embargo.py, ip_release.py), ADR-052", [
        ("Record", ["is_ip", "ip_type", "ip_released_at / _by", "is_embargoed", "embargoed_until", "embargo_released_at / _by"]),
        ("embargo", [], ["set_embargo()", "release_embargo()", "state_payload()"], MOD),
        ("ip_release", [], ["why_not_releasable()", "release_ip()"], MOD),
        ("EmbargoReminder", ["record → Record", "embargo_set_at", "step", "sent_at"]),
    ], [["embargo", "ip_release"], ["Record"], ["EmbargoReminder"]], [
        ("embargo", "Record", "uses"), ("ip_release", "Record", "uses"), ("Record", "EmbargoReminder", "owns"),
    ]),
    "C-4.1-notifications": fig("4.1", "3.4.1, 3.4.2", "notifications and live hints",
        "apps/notifications (models.py, services.py, settling.py), apps/live", [
        ("notifications.services", [], ["notify_routed()", "notify_decided()", "notify_new_version()", "…"], MOD),
        ("settling", [], ["settle_record()", "settle_for()"], MOD),
        ("Notification", ["recipient → User", "record → Record", "notif_type", "task_kind", "resolved_at", "resolved_label"]),
        ("NotificationRead", ["notification → Notification", "user", "read_at"]),
        ("live.channels", [], ["channels_for()", "record_topic()"], MOD),
        ("live.publish", [], ["publish()"], MOD),
        ("live.stream", [], ["get_hub()", "events()"], MOD),
    ], [["notifications.services", "settling"], ["Notification", "NotificationRead"], ["live.publish", "live.channels", "live.stream"]], [
        ("notifications.services", "Notification", "uses"), ("settling", "Notification", "uses"),
        ("Notification", "NotificationRead", "owns"), ("notifications.services", "live.publish", "uses"),
        ("live.stream", "live.channels", "uses"),
    ]),
    "C-5.1-extraction": fig("5.1", "3.5.1", "extraction",
        "apps/ai/extraction (ports, selection.py, unstructured_client.py, shaping_unstructured.py), apps/documents/models.py, ADR-067", [
        ("StructuredExtractor", ["«port»"], ["extract(pdf_bytes, filename) → ExtractedDocument"]),
        ("UnstructuredExtractor", ["UNSTRUCTURED_PLATFORM_API_KEY", "strategy: hi_res"], ["extract()"]),
        ("disclosure", [], ["may_disclose()"], MOD),
        ("PdfExtraction", ["record → Record", "status", "extractor", "structure", "raw_result", "pages_read"]),
        ("ExtractionFigure", ["extraction → PdfExtraction", "page", "bbox", "caption", "image"]),
    ], [["StructuredExtractor", "UnstructuredExtractor"], ["disclosure"], ["PdfExtraction", "ExtractionFigure"]], [
        ("UnstructuredExtractor", "StructuredExtractor", "assoc", {"head": "tri", "dash": True}),
        ("PdfExtraction", "ExtractionFigure", "owns"),
    ]),
    "C-5.2-indexing": fig("5.2", "3.5.2", "chunks and vectors",
        "apps/ai (models/, chunking/, indexing.py, repositories.py), ADR-013, ADR-015", [
        ("indexing", [], ["build_embedding_provider()", "embed_active_chunk_set()", "embed_record_summary()"], MOD),
        ("EmbeddingProvider", ["«port»"], ["embed_document_chunks()", "embed_query()"]),
        ("ChunkSet", ["record → Record", "source_revision", "strategy_id", "is_active"]),
        ("DocumentChunk", ["chunk_set → ChunkSet", "sequence", "text_hash", "token_count", "section_key", "search_vector"]),
        ("ChunkEmbedding", ["chunk → DocumentChunk", "space → EmbeddingSpace", "embedding (1024)"]),
        ("EmbeddingSpace", ["model_id", "dimensions", "metric", "state"]),
        ("RecordSpaceEmbedding", ["record → Record", "space → EmbeddingSpace", "embedding"]),
    ], [["indexing", "EmbeddingProvider"], ["ChunkSet", "DocumentChunk"], ["ChunkEmbedding", "EmbeddingSpace", "RecordSpaceEmbedding"]], [
        ("indexing", "EmbeddingProvider", "uses"), ("ChunkSet", "DocumentChunk", "owns"),
        ("DocumentChunk", "ChunkEmbedding", "owns"), ("ChunkEmbedding", "EmbeddingSpace", "assoc"),
        ("RecordSpaceEmbedding", "EmbeddingSpace", "assoc"),
    ]),
    "C-5.6-overview": fig("5.6", "3.5.6, 3.5.8", "AI Overview, paper brief and index jobs",
        "apps/ai (models/summary.py, overview/service.py, briefs/, views/embedding.py)", [
        ("overview.service", [], ["overview_for()", "queue_overview_for_chunk_set()", "generate_overview()"], MOD),
        ("RecordOverview", ["record → Record", "state", "text", "citations", "model_id", "content_hash"]),
        ("PaperBrief", ["record → Record", "chunk_set", "state", "fields", "section_briefs"]),
        ("EmbeddingJob", ["record → Record", "status", "celery_task_id", "error"]),
    ], [["overview.service"], ["RecordOverview", "PaperBrief"], ["EmbeddingJob"]], [
        ("overview.service", "RecordOverview", "uses"),
    ]),
    "C-6.1-library": fig("6.1", "3.6.1–3.6.3", "the reader's library",
        "apps/library/models.py, ADR-044, ADR-064, ADR-065, ADR-070", [
        ("SavedRecord", ["owner → User", "record → Record", "reading_status"]),
        ("LibraryFolder", ["owner → User", "name"]),
        ("FolderMembership", ["folder → LibraryFolder", "saved_record → SavedRecord"]),
        ("ReadingNote", ["owner", "record", "body", "revision"]),
        ("ReadingHighlight", ["owner", "record", "manuscript_revision", "manuscript_sha256", "page", "quote"]),
        ("ReadingPosition", ["owner", "record", "manuscript_sha256", "page", "fraction"]),
    ], [["SavedRecord", "FolderMembership", "LibraryFolder"], ["ReadingNote", "ReadingHighlight", "ReadingPosition"]], [
        ("LibraryFolder", "FolderMembership", "owns"), ("FolderMembership", "SavedRecord", "assoc"),
    ]),
    "C-6.4-calls": fig("6.4", "3.6.4", "Calls & Conferences", "apps/opportunities (models.py, review.py, services.py), ADR-050", [
        ("OpportunityViewSet", [], ["create()", "confirm()", "reject()", "remove()", "save()", "calendar()"], VIEW),
        ("Opportunity", ["opportunity_type", "title", "due_date", "start_date / end_date", "status", "is_featured", "posted_by"]),
        ("SavedCall", ["owner → User", "call → Opportunity"]),
        ("services", [], ["build_ics()"], MOD),
    ], [["OpportunityViewSet", "services"], ["Opportunity", "SavedCall"]], [
        ("OpportunityViewSet", "Opportunity", "uses"), ("Opportunity", "SavedCall", "owns"),
        ("OpportunityViewSet", "services", "uses"),
    ]),
    "C-6.5-discovery": fig("6.5", "3.6.5", "personal discovery", "apps/records (models.py, discovery.py), ADR-062", [
        ("discovery", [], ["get_interests()", "put_interests()", "get_feed()", "dismiss()", "undo_dismissal()"], MOD),
        ("DiscoveryInterests", ["user → User", "classifications", "psced", "revision"]),
        ("DiscoveryDismissal", ["user", "record"]),
        ("DiscoveryFeedSnapshot", ["user", "recipe_version", "mode", "entries"]),
    ], [["discovery"], ["DiscoveryInterests", "DiscoveryDismissal", "DiscoveryFeedSnapshot"]], [
        ("discovery", "DiscoveryInterests", "uses"), ("discovery", "DiscoveryDismissal", "uses"),
        ("discovery", "DiscoveryFeedSnapshot", "uses"),
    ]),
    "C-7.1-audit": fig("7.1", "3.7.1–3.7.3", "audit and administration",
        "apps/audit (models.py, workflow.py, services.py, views.py), apps/accounts SystemSetting", [
        ("audit.workflow", [], ["submitted()", "routed()", "assignment_closed()", "…"], MOD),
        ("create_audit_event", [], ["(event_type, user, record, metadata)"], MOD),
        ("AuditEvent", ["event_type", "user → User", "record → Record", "metadata", "created_at"]),
        ("AuditEventListView", [], ["get()  IsSystemAdmin"], VIEW),
        ("SystemSetting", ["key", "value", "updated_by"]),
    ], [["audit.workflow", "create_audit_event"], ["AuditEvent"], ["AuditEventListView", "SystemSetting"]], [
        ("audit.workflow", "AuditEvent", "uses"), ("create_audit_event", "AuditEvent", "uses"),
        ("AuditEventListView", "AuditEvent", "uses"),
    ]),
}
