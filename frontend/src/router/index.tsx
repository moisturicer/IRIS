import { createBrowserRouter } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { rolesFor } from "@/lib/access";
import { redirectRoutes } from "./redirects";

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
import MyWorkspacePage      from "@/features/records/MyWorkspacePage";
import { CallsAndConferencesPage } from "@/features/opportunities/CallsAndConferencesPage";
import MyLibraryPage        from "@/features/library/MyLibraryPage";
import ImportRecordsPage    from "@/features/records/ImportRecordsPage";
import MyReviewsPage        from "@/features/review/MyReviewsPage";
import EvaluationPage       from "@/features/review/EvaluationPage";
import NotificationsPage    from "@/features/notifications/NotificationsPage";
import AuditLogPage         from "@/features/audit/AuditLogPage";
import RoleRequestsPage     from "@/features/accounts/RoleRequestsPage";
import RAGChatPage          from "@/features/ai/RAGChatPage";
import SettingsPage         from "@/features/settings/SettingsPage";
import HelpPage             from "@/features/help/HelpPage";
import DownloadRequestsPage  from "@/features/admin/DownloadRequestsPage";
import DeleteRequestsPage    from "@/features/admin/DeleteRequestsPage";
import ApprovedProposalsPage from "@/features/review/ApprovedProposalsPage";

export const router = createBrowserRouter([
  { path: "/login",  element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },
  { path: "/activate/:uidb64/:token", element: <EmailVerifyPage /> },
  { path: "/download", element: <DownloadTokenPage /> },

  {
    // Every gate below comes from `lib/access.ts`, which the sidebar reads too.
    // Client-side gating is UX only -- the Django API is the boundary. See
    // access.ts and ProtectedRoute for why that distinction matters.
    element: <ProtectedRoute allowedRoles={rolesFor("discover")} />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <HomePage />, handle: { crumb: "Discover" } },
          // Retired URLs (spec §4.1). Outside the role gates: a redirect only
          // moves the address, and the page it lands on applies its own.
          ...redirectRoutes,
          { path: "records/:id",           element: <PaperViewPage />,   handle: { crumb: "Paper" } },
          { path: "records/mine",          element: <MyLibraryPage />,   handle: { crumb: "My Library" } },
          { path: "opportunities",         element: <CallsAndConferencesPage />, handle: { crumb: "Calls & Conferences" } },
          { path: "notifications",         element: <NotificationsPage />, handle: { crumb: "Notifications" } },
          { path: "ai",                    element: <RAGChatPage />,     handle: { crumb: "Ask IRIS" } },
          { path: "help",                  element: <HelpPage />,        handle: { crumb: "Help" } },
          { path: "settings",              element: <SettingsPage />,    handle: { crumb: "Settings & Profile" } },

          {
            // Authoring. SRS M2-2.1/M2-2.2 name the actor "Record Owner
            // (Student or Adviser)"; the clearing offices must not author what
            // they later clear.
            element: <ProtectedRoute allowedRoles={rolesFor("submit")} />,
            children: [
              { path: "workspace",        element: <MyWorkspacePage />, handle: { crumb: "My Workspace" } },
            ],
          },

          {
            element: <ProtectedRoute allowedRoles={rolesFor("reviewQueue")} />,
            children: [
              { path: "review",              element: <MyReviewsPage />,       handle: { crumb: "My Reviews" } },
              { path: "review/:id/evaluate", element: <EvaluationPage />,      handle: { crumb: "Evaluate" } },
            ],
          },

          {
            // RDCO coordination. `Import Records` is the "file on behalf of"
            // path -- which is why RDCO does not also get the submission wizard.
            element: <ProtectedRoute allowedRoles={rolesFor("audit")} />,
            children: [
              { path: "review/approved-proposals", element: <ApprovedProposalsPage />, handle: { crumb: "Approved Proposals" } },
              { path: "records/import",            element: <ImportRecordsPage />,     handle: { crumb: "Import Records" } },
              { path: "admin/role-requests",       element: <RoleRequestsPage />,      handle: { crumb: "Role Requests" } },
              { path: "admin/download-requests",   element: <DownloadRequestsPage />,  handle: { crumb: "Download Requests" } },
              { path: "admin/delete-requests",     element: <DeleteRequestsPage />,    handle: { crumb: "Delete Requests" } },
              { path: "admin/audit",               element: <AuditLogPage />,          handle: { crumb: "Audit Log" } },
            ],
          },
        ],
      },
    ],
  },
]);
