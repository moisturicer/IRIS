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
import RoleRequestsPage     from "@/features/accounts/RoleRequestsPage";
import FolderBrowserPage    from "@/features/storage/FolderBrowserPage";
import AIHubPage            from "@/features/ai/AIHubPage";
import HelpPage             from "@/features/help/HelpPage";

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
          { index: true, element: <DashboardPage />, handle: { crumb: "Discover" } },
          { path: "records", element: <PublishedRecordsPage />, handle: { crumb: "Published Records" } },
          { path: "records/:id", element: <RecordDetailPage />, handle: { crumb: "Record Detail" } },
          { path: "records/add", element: <AddRecordPage />, handle: { crumb: "Add Record" } },
          { path: "records/mine", element: <MyRecordsPage />, handle: { crumb: "My Records" } },
          { path: "records/:id/edit", element: <EditRecordPage />, handle: { crumb: "Edit Record" } },
          { path: "records/:id/documents", element: <DocumentsPage />, handle: { crumb: "Documents" } },

          {
            element: <RoleRoute allowed={[ROLES.ADVISER, ROLES.KTTO, ROLES.RDCO, ROLES.ITSO, ROLES.TBI]} />,
            children: [
              { path: "records/import", element: <ImportRecordsPage />, handle: { crumb: "Import Records" } },
            ],
          },

          {
            element: <RoleRoute allowed={REVIEWER_ROLES} />,
            children: [
              { path: "review/pending", element: <PendingRecordsPage />, handle: { crumb: "Pending Review" } },
              { path: "review/approved", element: <ApprovedRecordsPage />, handle: { crumb: "Approved" } },
              { path: "review/declined", element: <DeclinedRecordsPage />, handle: { crumb: "Declined" } },
              { path: "review/:id/evaluate", element: <EvaluationPage />, handle: { crumb: "Evaluate" } },
            ],
          },

          {
            element: <RoleRoute allowed={STAFF_ROLES} />,
            children: [
              { path: "admin/users",        element: <UserListPage />,      handle: { crumb: "Manage Users" } },
              { path: "admin/role-requests",element: <RoleRequestsPage />,  handle: { crumb: "Role Requests" } },
              { path: "admin/audit",        element: <AuditLogPage />,      handle: { crumb: "Audit Log" } },
              { path: "admin/sessions",     element: <div className="p-6 text-[13px] text-gray-500">Active sessions — coming soon.</div>, handle: { crumb: "Sessions" } },
            ],
          },

          { path: "notifications", element: <NotificationsPage />, handle: { crumb: "Notifications" } },
          { path: "storage", element: <FolderBrowserPage />, handle: { crumb: "Storage" } },
          { path: "storage/:folderId", element: <FolderBrowserPage />, handle: { crumb: "Storage" } },
          { path: "ai", element: <AIHubPage />, handle: { crumb: "AI Research Hub" } },
          { path: "help", element: <HelpPage />, handle: { crumb: "Help" } },
        ],
      },
    ],
  },
]);
