import { createBrowserRouter } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import {
  ROLES,
  ALL_ROLES,
  APPROVAL_CHAIN_ROLES,
  REQUEST_QUEUE_ROLES,
  AUDIT_LOG_ROLES,
} from "@/lib/constants";

// Auth pages
import LoginPage         from "@/features/auth/LoginPage";
import SignupPage        from "@/features/auth/SignupPage";
import EmailVerifyPage   from "@/features/auth/EmailVerifyPage";

// App shell (sidebar + header wrapper)
import { AppShell } from "@/components/layout/AppShell";

// Feature pages
import HomePage             from "@/features/dashboard/HomePage";
import PublishedRecordsPage from "@/features/records/PublishedRecordsPage";
import RecordDetailPage     from "@/features/records/RecordDetailPage";
import AddRecordPage        from "@/features/records/AddRecordPage";
import MyRecordsPage        from "@/features/records/MyRecordsPage";
import EditRecordPage       from "@/features/records/EditRecordPage";
import ImportRecordsPage    from "@/features/records/ImportRecordsPage";
import PendingRecordsPage   from "@/features/review/PendingRecordsPage";
import ApprovedRecordsPage  from "@/features/review/ApprovedRecordsPage";
import DeclinedRecordsPage  from "@/features/review/DeclinedRecordsPage";
import EvaluationPage       from "@/features/review/EvaluationPage";
import DocumentsPage        from "@/features/documents/DocumentsPage";
import NotificationsPage    from "@/features/notifications/NotificationsPage";
import AuditLogPage         from "@/features/audit/AuditLogPage";
import UserListPage         from "@/features/accounts/UserListPage";
import FolderBrowserPage    from "@/features/storage/FolderBrowserPage";
import AIHubPage            from "@/features/ai/AIHubPage";

export const router = createBrowserRouter([
  { path: "/login",  element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },
  { path: "/activate/:uidb64/:token", element: <EmailVerifyPage /> },

  {
    element: <ProtectedRoute allowedRoles={ALL_ROLES} />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true,          element: <HomePage /> },
          { path: "records",      element: <PublishedRecordsPage /> },
          { path: "records/:id",  element: <RecordDetailPage /> },
          { path: "records/:id/edit",  element: <EditRecordPage /> },
          { path: "records/:id/documents", element: <DocumentsPage /> },
          { path: "notifications", element: <NotificationsPage /> },
          { path: "storage",             element: <FolderBrowserPage /> },
          { path: "storage/:folderId",   element: <FolderBrowserPage /> },
          { path: "ai",            element: <AIHubPage /> },
          { path: "help",          element: <div>TODO: HelpPage (static manual content)</div> },
          { path: "settings",      element: <div>TODO: SettingsPage</div> },
          { path: "ai/summarize",  element: <AIHubPage /> },

          {
            element: <ProtectedRoute allowedRoles={[ROLES.STUDENT]} />,
            children: [
              { path: "records/add",  element: <AddRecordPage /> },
              { path: "records/mine", element: <MyRecordsPage /> },
            ],
          },

          {
            element: (
              <ProtectedRoute
                allowedRoles={[ROLES.ADVISER, ROLES.KTTO, ROLES.RDCO, ROLES.ITSO, ROLES.TBI, ROLES.IERC]}
              />
            ),
            children: [
              { path: "records/import", element: <ImportRecordsPage /> },
            ],
          },

          {
            element: <ProtectedRoute allowedRoles={APPROVAL_CHAIN_ROLES} />,
            children: [
              { path: "review/pending",         element: <PendingRecordsPage /> },
              { path: "review/approved",        element: <ApprovedRecordsPage /> },
              { path: "review/declined",        element: <DeclinedRecordsPage /> },
              { path: "review/:id/evaluate",    element: <EvaluationPage /> },
            ],
          },

          {
            element: <ProtectedRoute allowedRoles={REQUEST_QUEUE_ROLES} />,
            children: [
              { path: "requests/access",   element: <div>TODO: AccessRequestsPage</div> },
              { path: "requests/deletion", element: <div>TODO: DeletionRequestsPage</div> },
            ],
          },

          {
            element: <ProtectedRoute allowedRoles={AUDIT_LOG_ROLES} />,
            children: [
              { path: "admin/audit", element: <AuditLogPage /> },
            ],
          },

          {
            element: <ProtectedRoute allowedRoles={[ROLES.ADMIN]} />,
            children: [
              { path: "admin/users",    element: <UserListPage /> },
              { path: "admin/sessions", element: <div>TODO: ActiveSessionsPage</div> },
            ],
          },
        ],
      },
    ],
  },
]);
