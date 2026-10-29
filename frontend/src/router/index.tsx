import { createBrowserRouter, redirect } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ReviewAccessRoute } from "@/components/auth/ReviewAccessRoute";
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
import { CallsAndConferencesPage } from "@/features/opportunities/CallsAndConferencesPage";
import MyLibraryPage        from "@/features/library/MyLibraryPage";
import ImportRecordsPage    from "@/features/records/ImportRecordsPage";
import MyReviewsPage        from "@/features/review/MyReviewsPage";
import OfficeConsolePage    from "@/features/review/OfficeConsolePage";
import NotificationsPage    from "@/features/notifications/NotificationsPage";
import AuditLogPage         from "@/features/audit/AuditLogPage";
import RoleRequestsPage     from "@/features/accounts/RoleRequestsPage";
import UserListPage         from "@/features/accounts/UserListPage";
import RAGChatPage          from "@/features/ai/RAGChatPage";
import SettingsPage         from "@/features/settings/SettingsPage";
import HelpPage             from "@/features/help/HelpPage";
import DownloadRequestsPage  from "@/features/admin/DownloadRequestsPage";
import DeleteRequestsPage    from "@/features/admin/DeleteRequestsPage";

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
        // Every page is centred at the standard width unless its handle says
        // `width: "full"`: the PDF reader and the wide admin tables (IR-521).
        children: [
          { index: true, element: <HomePage />, handle: { crumb: "Discover" } },
          // Retired URLs (spec §4.1). Outside the role gates: a redirect only
          // moves the address, and the page it lands on applies its own.
          ...redirectRoutes,
          // No crumb: the reading header is this page's navigation (IR-569).
          { path: "records/:id",           element: <PaperViewPage />,   handle: { width: "full" } },
          { path: "records/mine",          element: <MyLibraryPage />,   handle: { crumb: "My Library" } },
          { path: "opportunities",         element: <CallsAndConferencesPage />, handle: { crumb: "Calls & Conferences" } },
          { path: "notifications",         element: <NotificationsPage />, handle: { crumb: "Notifications" } },
          {
            // `/ai` picks a conversation and replaces itself with that
            // conversation's own address (IR-548). Both render the same page,
            // in the same position, so moving between them keeps its state.
            path: "ai", handle: { crumb: "Ask IRIS" },
            children: [
              { index: true,                          element: <RAGChatPage /> },
              { path: "conversations/:conversationId", element: <RAGChatPage /> },
            ],
          },
          { path: "help",                  element: <HelpPage />,        handle: { crumb: "Help" } },
          { path: "settings",              element: <SettingsPage />,    handle: { crumb: "Settings & Profile" } },

          {
            element: <ProtectedRoute allowedRoles={rolesFor("reviewQueue")} />,
            children: [
              {
                // Only a user with review work (IR-413); anyone else goes to Discover.
                element: <ReviewAccessRoute />,
                children: [
                  { path: "review",          element: <MyReviewsPage />,       handle: { crumb: "My Reviews" } },
                  // A coordinator's console (IR-623). The server refuses anyone else.
                  { path: "review/office",   element: <OfficeConsolePage />,   handle: { crumb: "Office console" } },
                ],
              },
              { path: "review/:id/evaluate", loader: ({ params }) => redirect(`/records/${params.id}?section=review`) },
            ],
          },

          {
            // RDCO coordination. `Import Records` is the "file on behalf of"
            // path -- which is why RDCO does not also get the submission wizard.
            element: <ProtectedRoute allowedRoles={rolesFor("audit")} />,
            children: [
              { path: "records/import",            element: <ImportRecordsPage />,     handle: { crumb: "Import Records" } },
              { path: "admin/users",               element: <UserListPage />,          handle: { crumb: "Users", width: "full" } },
              { path: "admin/role-requests",       element: <RoleRequestsPage />,      handle: { crumb: "Role Requests", width: "full" } },
              { path: "admin/download-requests",   element: <DownloadRequestsPage />,  handle: { crumb: "Download Requests", width: "full" } },
              { path: "admin/delete-requests",     element: <DeleteRequestsPage />,    handle: { crumb: "Delete Requests", width: "full" } },
              { path: "admin/audit",               element: <AuditLogPage />,          handle: { crumb: "Audit Log", width: "full" } },
            ],
          },
        ],
      },
    ],
  },
]);
