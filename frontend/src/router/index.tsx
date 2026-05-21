import { createBrowserRouter } from "react-router-dom";
import { PrivateRoute } from "./PrivateRoute";
import { RoleRoute } from "./RoleRoute";
import { ROLES, STAFF_ROLES, REVIEWER_ROLES } from "@/lib/constants";

// Auth pages
import LoginPage         from "@/features/auth/LoginPage";
import SignupPage        from "@/features/auth/SignupPage";
import EmailVerifyPage   from "@/features/auth/EmailVerifyPage";

// App shell (sidebar + header wrapper)
import { AppShell } from "@/components/layout/AppShell";

// Feature pages
import DashboardPage        from "@/features/dashboard/DashboardPage";
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
  // Public routes
  { path: "/login",  element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },
  { path: "/activate/:uidb64/:token", element: <EmailVerifyPage /> },

  // All authenticated routes wrapped in AppShell
  {
    element: <PrivateRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true,          element: <DashboardPage /> },
          { path: "records",      element: <PublishedRecordsPage /> },
          { path: "records/:id",  element: <RecordDetailPage /> },
          { path: "records/add",       element: <AddRecordPage /> },
          { path: "records/mine",      element: <MyRecordsPage /> },
          { path: "records/:id/edit",  element: <EditRecordPage /> },
          { path: "records/:id/documents", element: <DocumentsPage /> },

          // Import -- reviewer+ only
          {
            element: <RoleRoute allowed={[ROLES.ADVISER, ROLES.KTTO, ROLES.RDCO, ROLES.ITSO, ROLES.TBI]} />,
            children: [
              { path: "records/import", element: <ImportRecordsPage /> },
            ],
          },

          // Review pipeline -- reviewer+ only
          {
            element: <RoleRoute allowed={REVIEWER_ROLES} />,
            children: [
              { path: "review/pending",         element: <PendingRecordsPage /> },
              { path: "review/approved",        element: <ApprovedRecordsPage /> },
              { path: "review/declined",        element: <DeclinedRecordsPage /> },
              { path: "review/:id/evaluate",    element: <EvaluationPage /> },
            ],
          },

          // Admin / staff -- KTTO, RDCO, ITSO, TBI
          {
            element: <RoleRoute allowed={STAFF_ROLES} />,
            children: [
              { path: "admin/users",    element: <UserListPage /> },
              { path: "admin/audit",    element: <AuditLogPage /> },
              { path: "admin/sessions", element: <div>TODO: ActiveSessionsPage</div> },
              // TODO: add RoleRequestsPage, LockedAccountsPage routes
            ],
          },

          { path: "notifications", element: <NotificationsPage /> },
          { path: "storage",             element: <FolderBrowserPage /> },
          { path: "storage/:folderId",   element: <FolderBrowserPage /> },
          { path: "ai",            element: <AIHubPage /> },
          { path: "help",          element: <div>TODO: HelpPage (static manual content)</div> },
        ],
      },
    ],
  },
]);
