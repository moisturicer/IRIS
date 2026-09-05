import { createBrowserRouter } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import {
  ROLES,
  ALL_ROLES,
  REVIEWER_ROLES,
  REQUEST_QUEUE_ROLES,
} from "@/lib/constants";

// Auth pages
import LoginPage         from "@/features/auth/LoginPage";
import SignupPage        from "@/features/auth/SignupPage";
import EmailVerifyPage   from "@/features/auth/EmailVerifyPage";
import DownloadTokenPage from "@/features/download/DownloadTokenPage";

// App shell (sidebar + header wrapper)
import { AppShell } from "@/components/layout/AppShell";

// Feature pages
import HomePage             from "@/features/dashboard/HomePage";
import PaperViewPage        from "@/features/records/paper-view/PaperViewPage";
import AddRecordPage        from "@/features/records/AddRecordPage";
import MyWorkspacePage      from "@/features/records/MyWorkspacePage";
import { CallsAndConferencesPage } from "@/features/opportunities/CallsAndConferencesPage";
import MyLibraryPage        from "@/features/library/MyLibraryPage";
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
import RoleRequestsPage     from "@/features/accounts/RoleRequestsPage";
import RAGChatPage          from "@/features/ai/RAGChatPage";
import SettingsPage         from "@/features/settings/SettingsPage";
import HelpPage             from "@/features/help/HelpPage";
import SessionsPage          from "@/features/admin/SessionsPage";
import DownloadRequestsPage  from "@/features/admin/DownloadRequestsPage";
import DeleteRequestsPage    from "@/features/admin/DeleteRequestsPage";
import ApprovedProposalsPage from "@/features/review/ApprovedProposalsPage";

export const router = createBrowserRouter([
  { path: "/login",  element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },
  { path: "/activate/:uidb64/:token", element: <EmailVerifyPage /> },
  { path: "/download", element: <DownloadTokenPage /> },

  {
    element: <ProtectedRoute allowedRoles={ALL_ROLES} />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <HomePage />, handle: { crumb: "Discover" } },
          { path: "records/:id",          element: <PaperViewPage />,                  handle: { crumb: "Paper" } },
          { path: "records/add",          element: <AddRecordPage />,                  handle: { crumb: "Add Record" } },
          { path: "records/mine",         element: <MyLibraryPage />,                  handle: { crumb: "My Library" } },
          { path: "workspace",            element: <MyWorkspacePage />,                 handle: { crumb: "My Workspace" } },
          { path: "opportunities",        element: <CallsAndConferencesPage />,         handle: { crumb: "Calls & Conferences" } },
          { path: "records/:id/edit",     element: <EditRecordPage />,                 handle: { crumb: "Edit Record" } },
          { path: "records/:id/documents",element: <DocumentsPage />,                  handle: { crumb: "Documents" } },
          { path: "notifications",        element: <NotificationsPage />,              handle: { crumb: "Notifications" } },
          // Storage routes removed -- apps/storage is slated for deletion (SC-01/FE-03,
          // IR-62) and overlapped DocumentsPage. StoragePage.tsx stays in the tree,
          // unrouted, per IR-86's "no component is deleted from the repository".
          { path: "ai",                   element: <RAGChatPage />,                    handle: { crumb: "Ask IRIS" } },
          { path: "help",                 element: <HelpPage />,                       handle: { crumb: "Help" } },
          { path: "settings",             element: <SettingsPage />,                   handle: { crumb: "Settings & Profile" } },

          {
            element: <ProtectedRoute allowedRoles={[ROLES.ADVISER, ROLES.KTTO, ROLES.RDCO, ROLES.ITSO, ROLES.IERC]} />,
            children: [
              { path: "records/import", element: <ImportRecordsPage />, handle: { crumb: "Import Records" } },
            ],
          },

          {
            element: <ProtectedRoute allowedRoles={REVIEWER_ROLES} />,
            children: [
              { path: "review/pending",            element: <PendingRecordsPage />,     handle: { crumb: "Pending Review" } },
              { path: "review/approved",           element: <ApprovedRecordsPage />,    handle: { crumb: "Approved" } },
              { path: "review/declined",           element: <DeclinedRecordsPage />,    handle: { crumb: "Declined" } },
              { path: "review/approved-proposals", element: <ApprovedProposalsPage />,  handle: { crumb: "Approved Proposals" } },
              { path: "review/:id/evaluate",       element: <EvaluationPage />,         handle: { crumb: "Evaluate" } },
            ],
          },

          {
            element: <ProtectedRoute allowedRoles={REQUEST_QUEUE_ROLES} />,
            children: [
              { path: "admin/users",             element: <UserListPage />,         handle: { crumb: "Manage Users" } },
              { path: "admin/role-requests",     element: <RoleRequestsPage />,     handle: { crumb: "Role Requests" } },
              { path: "admin/audit",             element: <AuditLogPage />,         handle: { crumb: "Audit Log" } },
              { path: "admin/sessions",          element: <SessionsPage />,         handle: { crumb: "Sessions" } },
              { path: "admin/download-requests", element: <DownloadRequestsPage />, handle: { crumb: "Download Requests" } },
              { path: "admin/delete-requests",   element: <DeleteRequestsPage />,   handle: { crumb: "Delete Requests" } },
            ],
          },
        ],
      },
    ],
  },
]);
