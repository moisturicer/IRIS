"""A-*: activity diagrams for SRS v2 §3.2, the counterpart of v1's sub-flow diagrams.

v1 drew swimlanes (Browser / Application / Database). The renderer draws the
UML alternative instead: each action names who does it on its first line.
"""

ACTORS = {"Guest", "Person", "Author", "Owner", "Adviser", "RDCO", "KTTO", "Reviewer", "Office member",
          "Coordinator", "Reader", "Staff", "System Admin", "Contact person", "Browser"}
C = "at a46d7fc4 (IR-1275)."


def fig(fid, sec, name, src, steps, aspect=0.7):
    return {"title": f"A-{fid}  Activity: {name}", "caption": f"SRS v2 §{sec}. From {src} {C}",
            "steps": steps, "aspect": aspect}


S = "IRIS"  # the server, where no narrower name helps

FIGURES = {
    # ---------------------------------------------------------------- Module 1
    "A-1.1a-register": fig("1.1a", "3.2.1.1", "register", "apps/accounts/views.py RegisterView, serializers.py", [
        ("Guest", "Fill in name, institutional email, password, role and college"),
        ("Guest", "Read the data notice; answer Yes or No to AI use"),
        (S, "Validate fields, email domain and password policy"),
        ("?", "Valid?", [
            (S, "Create the unverified account; record notice version, AI answer and time"),
            (S, "Queue the verification email"),
            ("Guest", "See 'Check your email'"),
        ], [(S, "Show field errors; create nothing"), "end"]),
    ]),
    "A-1.1b-verify": fig("1.1b", "3.2.1.1", "verify the email address", "apps/accounts/recovery, ADR-045", [
        ("Person", "Open the link from the email"),
        (S, "Check the token is authentic, unused and under 24 hours old"),
        ("?", "Valid?", [
            (S, "Mark the account verified; spend the token"),
            ("Person", "Sign in"),
        ], [(S, "Say the link no longer works"), ("Person", "Ask for a new link"),
            (S, "Send one, unless the rate limit stops it"), "end"]),
    ]),
    "A-1.2a-sign-in": fig("1.2a", "3.2.1.2", "sign in", "apps/accounts/views.py LoginView, lockout.py, ADR-072", [
        ("Person", "Enter email, password; maybe tick Keep me signed in"),
        (S, "Check throttles and the axes lock"),
        ("?", "Locked or throttled?", [(S, "Answer 429 with the next allowed time"), "end"], [
            (S, "Check the credentials"),
            ("?", "Correct and verified?", [
                (S, "Create the UserSession; audit LOGIN"),
                (S, "Return the access token; set the HttpOnly refresh cookie"),
                ("?", "Current notice answered?", [("Person", "Land on the workspace")],
                 [("Person", "Answer the notice first (or sign out)")]),
            ], [(S, "Count the failure; show a generic error"), "end"]),
        ]),
    ]),
    "A-1.2b-refresh-idle": fig("1.2b", "3.2.1.2", "stay signed in and the inactivity limit",
        "apps/accounts/views.py RefreshView, sessions.py, NFR-S2", [
        ("Person", "Open a tab, or a request answers 401"),
        ("Browser", "POST token/refresh; the browser sends the cookie"),
        ("?", "Cookie present?", [
            (S, "Check Origin and the session"),
            ("?", "Idle under 30 min, or remembered and unexpired?", [
                (S, "Rotate: blacklist the old token, set the new cookie"),
                ("Browser", "Retry the original request"),
            ], [(S, "End the session (idle or expired)"), ("Person", "See 'Your session ended'"), "end"]),
        ], [("Person", "Shown as signed out, with no message"), "end"]),
    ]),
    "A-1.3-lockout": fig("1.3", "3.2.1.3", "lockout and throttling", "config/settings/base.py, apps/accounts/lockout.py", [
        ("Person", "Send a request or a sign-in"),
        (S, "Check the per-user / per-address rate limit"),
        ("?", "Under the limit?", [
            ("?", "A failed sign-in?", [
                (S, "Count the failure for this account and address"),
                ("?", "Failures reach AXES_FAILURE_LIMIT?", [(S, "Lock for the cool-off; answer 429"), "end"],
                 [(S, "Answer 'Invalid email or password'")]),
            ], [(S, "Process the request")]),
        ], [(S, "Answer 429 Too Many Requests"), "end"]),
    ]),
    "A-1.4-reset": fig("1.4", "3.2.1.4", "reset a forgotten password", "apps/accounts/recovery, ADR-045", [
        ("Person", "Enter the email on Forgot password"),
        (S, "Answer 'If an account exists, we sent a link'"),
        ("?", "Eligible account and under the limits?", [
            ("Email service", "Deliver the single-use link (30 minutes)"),
            ("Person", "Open the link; enter a new password"),
            (S, "Check the policy; save; spend the link"),
            (S, "Bump credential_version: every session ends"),
        ], [(S, "Suppress silently; audit it"), "end"]),
    ]),
    "A-1.5-role-request": fig("1.5", "3.2.1.5", "request and grant a role", "apps/accounts/views.py RoleRequestDetailView, core/permissions.py", [
        ("Person", "Request the Student or Adviser role"),
        (S, "Hold the request as pending; hint RDCO's queue"),
        ("RDCO", "Open the request"),
        ("?", "Approve?", [(S, "Set the role; notify the person; audit it")],
         [("RDCO", "Give a reason"), (S, "Decline; notify the person with the reason")]),
    ]),
    "A-1.6-lock": fig("1.6", "3.2.1.6", "lock an account or revoke a session", "apps/accounts/views.py, sessions.py", [
        ("RDCO", "Open Users or Active sessions"),
        ("?", "Lock an account?", [
            (S, "Refuse if the target is a System Admin"),
            (S, "Lock; end its sessions (reason: locked); audit it"),
        ], [("RDCO", "Pick a session and confirm"),
            (S, "Blacklist its token; end it (reason: revoked); audit it")]),
        ("Person", "Next request fails; the page says why"),
    ]),
    "A-1.7-delete-account": fig("1.7", "3.2.1.7", "delete my account", "apps/accounts/deletion, ADR-051", [
        ("Person", "Request deletion in Settings"),
        ("System Admin", "Open the request"),
        (S, "List what blocks it (for example an Adviser of a paper in review)"),
        ("?", "Anything blocking?", [(S, "Refuse confirmation, naming each blocker"), "end"], [
            ("?", "Confirm?", [(S, "Delete personal data; end sessions; audit it")],
             [("System Admin", "Reject with a reason"), (S, "Tell the person why")]),
        ]),
    ]),
    # ---------------------------------------------------------------- Module 2
    "A-2.1-publish": fig("2.1", "3.2.2.1", "publish a record", "RecordViewSet create/submit, features/publish", [
        ("Author", "Choose the record type"),
        ("Author", "Upload the manuscript (checked: A-2.3)"),
        ("?", "Identical manuscript already in IRIS?", [("Author", "Review the matches and acknowledge")], []),
        ("Author", "Enter metadata, authors, co-owners, Adviser, origin"),
        ("Author", "Upload the type's documents (Required never blocks)"),
        ("Author", "Submit"),
        ("?", "Adviser is one of the owners?", [(S, "Refuse with a message"), "end"], [
            (S, "Write Version 1; status in_review; embargoed"),
            (S, "Open the Adviser's assignment; notify the Adviser; audit"),
        ]),
    ]),
    "A-2.2-requirements": fig("2.2", "3.2.2.2", "set a record type's requirements", "apps/documents/setup.py, ADR-063", [
        ("RDCO", "Open Setup and pick a record type"),
        ("RDCO", "Add or edit a requirement: name, description, Required or Optional"),
        ("?", "Attach a Template?", [("RDCO", "Upload the template (at most 50 MB, scanned)")], []),
        ("?", "Remove it?", [
            ("?", "Any record uploaded to it?", [(S, "Hide it; keep the files")], [(S, "Delete it")]),
        ], [(S, "Save; Guidelines and Publish show it at once")]),
    ]),
    "A-2.3-upload": fig("2.3", "3.2.2.3", "check an upload", "apps/documents/validators.py, scanning.py, ADR-074", [
        ("Person", "Upload a file"),
        (S, "Check signature, page count and size (50 MB)"),
        ("?", "A real PDF within the limit?", [
            ("ClamAV", "Scan the bytes (INSTREAM)"),
            ("?", "Clean, and the scanner answered?", [(S, "Store the file and save the row")],
             [(S, "Refuse (400); store nothing; audit UPLOAD_REFUSED_UNSAFE"), "end"]),
        ], [(S, "Refuse with the reason"), "end"]),
    ]),
    "A-2.4-version": fig("2.4", "3.2.2.4", "read and compare Versions", "apps/records/versions.py, apps/reviews/version_comparison.py", [
        ("Reviewer", "Open the paper's version menu"),
        ("Reviewer", "Pick a Version"),
        (S, "Serve that Version's manuscript and documents"),
        ("?", "Compare with another?", [
            (S, "Read both Versions' review texts (local, no AI)"),
            (S, "Match sections: unchanged, changed, added, removed"),
            ("Reviewer", "Read the Changes tab"),
        ], []),
    ]),
    "A-2.5-download": fig("2.5", "3.2.2.5", "request and use a download", "apps/records/download_service.py, ADR-048", [
        ("Reader", "Choose Download on a paper"),
        ("?", "Owner, Adviser, office or reviewer?", [(S, "Serve a watermarked copy; audit (exempt)"), "end"], [
            ("?", "Unexpired grant?", [(S, "Serve a watermarked copy; audit (grant)"), "end"], [
                ("Reader", "Request a download, saying why"),
                ("RDCO", "Review the request"),
                ("?", "Approve?", [(S, "Grant for 30 days; notify in-app and by email")],
                 [("RDCO", "Decline with a note"), (S, "Notify the reader")]),
            ]),
        ]),
    ]),
    "A-2.6-delete-request": fig("2.6", "3.2.2.6", "delete a record", "DeleteRequestViewSet", [
        ("Owner", "Ask for deletion, with a reason"),
        (S, "Keep the previous status; set pending_delete; hint RDCO"),
        ("RDCO", "Review the request"),
        ("?", "Approve?", [(S, "Delete the record; keep its audit history")],
         [("RDCO", "Decline with a note"), (S, "Restore the previous status")]),
        (S, "Notify the owner"),
    ]),
    "A-2.7-import": fig("2.7", "3.2.2.7", "import records from Excel", "RecordViewSet.import_excel, apps/records/services.py", [
        ("Staff", "Upload a .xls or .xlsx"),
        (S, "Parse the workbook"),
        ("?", "Readable?", [
            (S, "For each row: validate with the single-record rules"),
            ("?", "Row valid?", [(S, "Save its record, owner and authors together")],
             [(S, "Skip the row, saying why")]),
            ("Staff", "Read the import log"),
        ], [(S, "Refuse the file"), "end"]),
    ]),
    "A-2.8-search": fig("2.8", "3.2.2.8", "search Discover", "RecordViewSet.list, filters.py", [
        ("Reader", "Type keywords; pick filters and sort"),
        (S, "Narrow to published records the reader may see"),
        (S, "Match the weighted title (A) and abstract (B) index"),
        (S, "Apply filters; rank; paginate"),
        ("?", "Any results?", [("Reader", "Open a record's Paper View")], [("Reader", "See 'No results'")]),
    ]),
    # ---------------------------------------------------------------- Module 3
    "A-3.1-adviser": fig("3.1", "3.2.3.1", "the Adviser's review", "apps/reviews/decisions.py, routing.py, ADR-032, ADR-047", [
        ("Adviser", "Open the record from To review"),
        ("?", "A Proposal?", [
            ("?", "Accept?", [(S, "Set approved (Accepted); notify the owners")],
             [("Adviser", "Request revision or reject (with a reason)")]),
        ], [
            ("?", "Accept?", [
                ("Adviser", "Give a reason; maybe nominate RDCO officers and suggest offices"),
                (S, "Complete the Adviser's assignment; open RDCO's; notify RDCO"),
            ], [("Adviser", "Request revision or reject (with a reason)")]),
        ]),
    ]),
    "A-3.2-rdco": fig("3.2", "3.2.3.2", "RDCO routes and decides", "apps/reviews/routing.py, decisions.py, ADR-047", [
        ("RDCO", "Open the record; read the Adviser's and author's suggestions"),
        ("?", "Need specialist review?", [
            ("RDCO", "Pick offices (Pool or named officers) with a reason"),
            (S, "Open an assignment per office; notify them"),
            ("Office member", "Review in parallel (A-3.3)"),
        ], []),
        ("RDCO", "Choose Publish, Keep unlisted or Reject"),
        (S, "Warn: offices still reviewing, findings recorded"),
        ("?", "Publish and still embargoed?", [(S, "Refuse until the embargo is released"), "end"], [
            (S, "Write RDCO's Review; set the status"),
            (S, "Withdraw open assignments, Seats, document and revision requests"),
            (S, "Notify the owners once and each closed Seat"),
        ]),
    ]),
    "A-3.3-office": fig("3.3", "3.2.3.3", "an office's review", "apps/reviews/seats.py, office_review.py", [
        (S, "Assignment lands in the office's Pool"),
        ("?", "Coordinator assigns?", [("Coordinator", "Assign a reviewer")], [("Office member", "Claim it")]),
        ("Office member", "Review; maybe add a colleague or request another office"),
        ("?", "Outcome?", [(S, "Clearance: cleared")], [(S, "Clearance: not cleared (finding)")], ("clear", "finding")),
        (S, "Complete the office's assignment; notify RDCO"),
    ]),
    "A-3.4-resubmit": fig("3.4", "3.2.3.4", "clearance-aware resubmission", "apps/reviews/new_version.py, ADR-003, ADR-004", [
        ("Reviewer", "Request revision on the Version reviewed"),
        (S, "Open a ResubmissionRequest; record awaiting_resubmission"),
        ("Owner", "Answer each Must fix thread; upload changes"),
        ("Owner", "Submit the new Version"),
        ("?", "Changed, and every Must fix answered?", [
            (S, "Write Version n+1; resolve the requests"),
            ("?", "Policy?", [(S, "Reset ONLY the asking parties' clearances; keep every other")],
             [(S, "Reset every office's clearance")], ("clearance-aware", "restart-all")),
            (S, "Reopen the asking parties' Seats"),
            ("Reviewer", "Review the new Version"),
        ], [(S, "Refuse, saying what is missing"), "end"]),
    ]),
    "A-3.5-doc-request": fig("3.5", "3.2.3.5", "a document request", "apps/documents/requests.py, ADR-022", [
        ("Reviewer", "Ask for missing documents"),
        (S, "Open the request; awaiting_document; pause this party's clock"),
        ("Owner", "Upload each item"),
        ("Reviewer", "Accept or reject each item, with a reason"),
        ("?", "All accepted?", [(S, "Fulfil the request; restart the clock")], [("Owner", "Upload again")]),
    ]),
    "A-3.6-thread": fig("3.6", "3.2.3.6", "a review thread", "apps/reviews/threads.py, ADR-032 §7", [
        ("Reviewer", "Select a passage; open a thread (Must fix or Suggestion)"),
        ("Owner", "Answer it: Addressed or Declined"),
        ("?", "Reviewer satisfied?", [("Reviewer", "Resolve it")], [("Reviewer", "Reopen it")]),
        ("?", "New Version submitted?", [(S, "Place the thread on the new text (found, changed, removed)")], []),
    ]),
    "A-3.7-reminders": fig("3.7", "3.2.3.7", "reminders and escalation", "apps/reviews/reminders.py, tasks.py, ADR-043", [
        (S, "Hourly: find assignments with a due date"),
        ("?", "Two working days before, or on, the due date?", [(S, "Remind the Seat holders (or coordinators)")], []),
        ("?", "Overdue?", [
            ("?", "An office?", [(S, "Escalate to its coordinators; repeat every 5 working days")],
             [(S, "Show the owner 'Waiting on your Adviser · N days overdue'")]),
        ], []),
        ("?", "Coordinator extends?", [(S, "Move the due date later; audit; re-arm reminders")], []),
    ]),
    "A-3.8-ip": fig("3.8", "3.2.3.8", "tag and release IP", "RecordViewSet.tags, records/ip_release.py", [
        ("Staff", "Tag the IP type on the paper"),
        (S, "Mark it IP; keep it from AI"),
        ("KTTO", "Release the IP mark (audited)"),
        ("?", "Embargo released and consent given?", [(S, "Paper may reach AI once published")],
         [(S, "Still kept from AI")]),
    ]),
    # ---------------------------------------------------------------- Module 4
    "A-4.1-notify": fig("4.1", "3.2.4.1", "notify and resolve", "apps/notifications/services.py, settling.py, ADR-069", [
        (S, "A workflow act commits"),
        (S, "Pick recipients the visibility rule admits"),
        ("||", [(S, "Create the in-app Notification")], [("Email service", "Send email, for some events")]),
        (S, "Publish a live hint"),
        ("?", "Did the notice ask for action, and has that task ended?", [
            (S, "Set resolved_at and resolved_label; drop it from unread")], []),
    ]),
    "A-4.2-live": fig("4.2", "3.2.4.2", "a live update", "apps/live, frontend/src/lib/live.ts, ADR-073", [
        ("Person", "Open a page; the tab opens one stream"),
        (S, "Authenticate once; subscribe to the server's channels"),
        (S, "A change commits; publish a hint"),
        ("Browser", "Receive the hint; refetch through the API"),
        ("?", "Stream dropped, or tab refocused?", [("Browser", "Reconnect, then refetch")], []),
    ]),
    # ---------------------------------------------------------------- Module 5
    "A-5.1-extract": fig("5.1", "3.2.5.1", "extract a published manuscript", "apps/documents/tasks.py, apps/ai/extraction, ADR-067", [
        ("RDCO", "Publish the paper"),
        (S, "Queue extract_manuscript_text (extraction queue)"),
        ("?", "Gate passes?", [
            (S, "Admit the paid read (when admission enforces)"),
            ("Unstructured", "Read the PDF (hi_res)"),
            ("?", "Read complete?", [(S, "Store PdfExtraction and Figures; queue chunking")],
             [(S, "Mark failed"), ("Owner", "Retry from Publish"), "end"]),
        ], [(S, "Send nothing"), "end"]),
    ]),
    "A-5.2-index": fig("5.2", "3.2.5.2", "chunk and embed", "apps/ai/tasks.py, chunking/, indexing.py", [
        (S, "chunk_extraction: build chunks (target 700 tokens)"),
        (S, "Swap in the new ChunkSet atomically"),
        (S, "embed_chunk_set: pick chunks whose text changed"),
        ("Voyage AI", "Contextualized embeddings (1024-d)"),
        (S, "Store ChunkEmbedding in pgvector (HNSW)"),
        (S, "Queue the AI Overview"),
    ]),
    "A-5.3-gate": fig("5.3", "3.2.5.3", "the disclosure gate", "apps/ai/policy/disclosure.py, ADR-052, ADR-054", [
        (S, "An AI path asks to send a paper"),
        ("?", "Published and not deleted?", [
            ("?", "Embargo released?", [
                ("?", "IP mark absent or released by KTTO?", [
                    ("?", "Contact person said Yes?", [(S, "Allow")], [(S, "Refuse: no_consent (may be shown)"), "end"]),
                ], [(S, "Refuse: unreleased_ip"), "end"]),
            ], [(S, "Refuse: embargoed"), "end"]),
        ], [(S, "Refuse: unpublished"), "end"]),
    ]),
    "A-5.4-ask": fig("5.4", "3.2.5.4", "answer an Ask IRIS question", "ai/runs, ai/agent, ai/research, ADR-049", [
        ("Person", "Ask a question"),
        (S, "nginx edge: Django issues a reader grant"),
        ("ai-gateway", "Store the run as queued; wake a worker"),
        ("ai-runs-worker", "Claim the run (lease)"),
        ("ai-runs-worker", "Search and read passages the reader may read"),
        ("Language model", "Draft the answer"),
        ("?", "Every cited sentence supported?", [], [("ai-runs-worker", "Repair once")]),
        ("ai-runs-worker", "Recheck sources; commit the Turn and citations"),
        ("Person", "Read the streamed answer; open a citation"),
    ]),
    "A-5.5-paper-chat": fig("5.5", "3.2.5.5", "Paper Chat", "PaperChatDock.tsx, apps/ai/grants", [
        ("Reader", "Open Paper Chat on a paper"),
        ("?", "Paper passes the gate?", [
            (S, "Issue a grant scoped to this record"),
            ("AI runtime", "Answer from this paper only (as A-5.4)"),
        ], [("Reader", "See why (consent only is named)"), "end"]),
    ]),
    "A-5.6-overview": fig("5.6", "3.2.5.6", "the AI Overview", "apps/ai/overview, tasks.generate_record_overview", [
        (S, "Indexing finishes"),
        ("Language model", "Write a cited summary from the passages"),
        (S, "Store RecordOverview with its citations"),
        ("Reader", "Open the paper"),
        ("?", "Overview stored and the gate passes?", [("Reader", "Read the overview")],
         [("Reader", "See why none is available")]),
    ]),
    "A-5.7-degrade": fig("5.7", "3.2.5.7", "degrade when AI is unavailable", "GET /ai/status/, apps/ai/resilience, ADR-008", [
        ("Person", "Use IRIS"),
        ("?", "AI available?", [("Person", "Ask IRIS and Paper Chat work")], [
            ("Person", "See 'AI is unavailable'"),
            (S, "Keyword search still answers"),
            (S, "Uploads accepted; indexing retried later"),
        ]),
    ]),
    "A-5.8-reembed": fig("5.8", "3.2.5.8", "re-embed records", "apps/ai/views/embedding.py", [
        ("Staff", "Ask to re-embed one record, or all"),
        (S, "Queue an EmbeddingJob per record"),
        (S, "Embed through Voyage (gate applies)"),
        ("?", "Succeeded?", [(S, "Mark the job done")], [(S, "Mark it failed with the error")]),
        ("Staff", "Read the job log"),
    ]),
    # ---------------------------------------------------------------- Module 6
    "A-6.1-save": fig("6.1", "3.2.6.1", "save and read", "apps/library, ADR-044", [
        ("Reader", "Save a paper; set a reading status"),
        ("Reader", "Read; the position is kept on the account"),
        ("?", "Same manuscript bytes later?", [("Reader", "Resume where I left off")], [("Reader", "Start from the top")]),
    ]),
    "A-6.2-folders": fig("6.2", "3.2.6.2", "file a save in a folder", "apps/library/folders.py, ADR-070", [
        ("Reader", "Create a folder"),
        ("Reader", "Add saved papers to it"),
        ("?", "Unsave a paper?", [(S, "Remove it from every folder")], []),
    ]),
    "A-6.3-note": fig("6.3", "3.2.6.3", "a private note", "apps/library notes, ADR-064 (proposed)", [
        ("Reader", "Type a note on a paper"),
        (S, "Autosave with the note's revision"),
        ("?", "Saved from another tab meanwhile?", [(S, "Keep both texts; ask the reader to merge")],
         [(S, "Save")]),
    ]),
    "A-6.4-call": fig("6.4", "3.2.6.4", "post a call", "apps/opportunities, ADR-050", [
        ("Adviser", "Post a call for papers"),
        ("?", "Posted by RDCO?", [(S, "List it at once")], [
            (S, "Hold it as waiting for RDCO"),
            ("?", "RDCO confirms?", [(S, "List it; notify the Adviser")],
             [(S, "Reject it with a reason, or let it lapse")]),
        ]),
        (S, "Audit every change"),
    ]),
    "A-6.5-for-you": fig("6.5", "3.2.6.5", "personal discovery", "apps/records/discovery.py, ADR-062", [
        ("Reader", "Choose Areas of interest"),
        (S, "Add Areas from saved papers the reader may still read"),
        (S, "Rank by the transparent recipe; freeze a feed snapshot"),
        ("?", "Not interested?", [(S, "Hide it (Undo available)")], []),
    ]),
    # ---------------------------------------------------------------- Module 7
    "A-7.1-audit": fig("7.1", "3.2.7.1", "write and read the audit log", "apps/audit, NFR-S5", [
        ("Person", "Perform an act"),
        (S, "Open the act's transaction"),
        (S, "Change the data and write the AuditEvent"),
        ("?", "Commit succeeds?", [(S, "Both are stored")], [(S, "Neither is stored"), "end"]),
        ("System Admin", "Filter and export the audit log (read-only)"),
    ]),
    "A-7.2-console": fig("7.2", "3.2.7.2", "the consoles", "features/admin, ADR-051", [
        ("Person", "Sign in"),
        ("?", "Role?", [("System Admin", "Administration: audit log, settings, retention, deletions, office roles")],
         [("RDCO", "RDCO: users, requests, sessions, Setup, analytics")], ("System Admin", "RDCO")),
    ]),
    "A-7.3-help": fig("7.3", "3.2.7.3", "Settings and Help", "features/settings, features/help", [
        ("Person", "Open Settings"),
        ("?", "Which tab?", [("Person", "Profile, password, AI answer, data")], [("Person", "Help (/help redirects here)")],
         ("account", "help")),
    ]),
}
