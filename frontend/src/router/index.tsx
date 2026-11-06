import { lazy } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ReviewAccessRoute } from "@/components/auth/ReviewAccessRoute";
import { pathFor, rolesFor } from "@/lib/access";
import { redirectRoutes } from "./redirects";

// Auth pages
import LoginPage         from "@/features/auth/LoginPage";
import SignupPage        from "@/features/auth/SignupPage";
import EmailVerifyPage   from "@/features/auth/EmailVerifyPage";
import ForgotPasswordPage from "@/features/auth/ForgotPasswordPage";
import ResetPasswordPage  from "@/features/auth/ResetPasswordPage";

// App shell (sidebar + header wrapper)
import { AppShell } from "@/components/layout/AppShell";

// Feature pages
import HomePage             from "@/features/dashboard/HomePage";
import { CallsAndConferencesPage } from "@/features/opportunities/CallsAndConferencesPage";
import MyLibraryPage        from "@/features/library/MyLibraryPage";
import MyReviewsPage        from "@/features/review/MyReviewsPage";
import ReviewAnalyticsPage  from "@/features/review/ReviewAnalyticsPage";
import OfficeConsolePage    from "@/features/review/OfficeConsolePage";

import NotificationsPage    from "@/features/notifications/NotificationsPage";
import SettingsPage         from "@/features/settings/SettingsPage";
import ProfilePage          from "@/features/profile/ProfilePage";
import EditProfilePage      from "@/features/profile/EditProfilePage";
import HelpPage             from "@/features/help/HelpPage";

// Error screens (IR-745)
import { NotFoundScreen }   from "@/features/errors/NotFoundScreen";
import { RouteErrorScreen } from "@/features/errors/RouteErrorScreen";
import { DeferredPage } from "./DeferredPage";

// IR-749: defer the screens with the heaviest route-level dependencies.
// These imports do not start until the authenticated/authorized route renders.
const PaperViewPage = lazy(() => import("@/features/records/paper-view/PaperViewPage"));
const RAGChatPage = lazy(() => import("@/features/ai/RAGChatPage"));
const ImportRecordsPage = lazy(() => import("@/features/records/ImportRecordsPage"));
const UserListPage = lazy(() => import("@/features/accounts/UserListPage"));
const RoleRequestsPage = lazy(() => import("@/features/accounts/RoleRequestsPage"));
const DownloadRequestsPage = lazy(() => import("@/features/admin/DownloadRequestsPage"));
const DeleteRequestsPage = lazy(() => import("@/features/admin/DeleteRequestsPage"));
const AuditLogPage = lazy(() => import("@/features/audit/AuditLogPage"));

export const routes: RouteObject[] = [{
  // The last resort (IR-745): a crash outside the shell's own boundary below,
  // in a public page or in the shell itself, is drawn with no shell at all.
  errorElement: <RouteErrorScreen standalone />,
  children: [
  { path: "/login",  element: <LoginPage /> },
  { path: "/signup", element: <SignupPage /> },
  { path: "/activate/:uidb64/:token", element: <EmailVerifyPage /> },
  // ADR-045 (IR-642). Public: recovery must never require signing in.
  { path: "/password/forgot", element: <ForgotPasswordPage /> },
  { path: "/password/reset",  element: <ResetPasswordPage /> },

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
        children: [{
        // A page that crashes is replaced by the error screen inside the
        // shell, so the sidebar and in-memory state survive it (IR-745).
        errorElement: <RouteErrorScreen />,
        children: [
          { index: true, element: <HomePage />, handle: { crumb: "Discover" } },
          // Retired URLs (spec §4.1). Outside the role gates: a redirect only
          // moves the address, and the page it lands on applies its own.
          ...redirectRoutes,
          // No crumb: the reading header is this page's navigation (IR-569).
          {
            path: "records/:id",
            element: <DeferredPage name="Paper View"><PaperViewPage /></DeferredPage>,
            handle: { width: "full" },
          },
          { path: "records/mine",          element: <MyLibraryPage />,   handle: { crumb: "My Library" } },
          { path: "opportunities",         element: <CallsAndConferencesPage />, handle: { crumb: "Calls & Conferences" } },
          { path: "notifications",         element: <NotificationsPage />, handle: { crumb: "Notifications" } },
          {
            // `/ai` picks a conversation and replaces itself with that
            // conversation's own address (IR-548). Both render the same page,
            // in the same position, so moving between them keeps its state.
            path: "ai", handle: { crumb: "Ask IRIS" },
            children: [
              {
                index: true,
                element: <DeferredPage name="Ask IRIS"><RAGChatPage /></DeferredPage>,
              },
              {
                path: "conversations/:conversationId",
                element: <DeferredPage name="Ask IRIS"><RAGChatPage /></DeferredPage>,
              },
            ],
          },
          { path: "help",                  element: <HelpPage />,        handle: { crumb: "Help" } },
          {
            // Edit profile sits under Profile, so its breadcrumb reads Profile > Edit profile.
            path: "profile", handle: { crumb: "Profile" },
            children: [
              { index: true,  element: <ProfilePage /> },
              { path: "edit", element: <EditProfilePage />, handle: { crumb: "Edit profile" } },
            ],
          },
          { path: "settings",              element: <SettingsPage />,    handle: { crumb: "Settings" } },

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
            ],
          },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("reviewAnalytics")} />,
            children: [
              { path: "review/analytics", element: <ReviewAnalyticsPage />, handle: { crumb: "Workflow Analytics", width: "full" } },
            ],
          },

          {
            // RDCO coordination. `Import Records` is the "file on behalf of"
            // path -- which is why RDCO does not also get the submission wizard.
            element: <ProtectedRoute allowedRoles={rolesFor("importRecords")} />,
            children: [
              {
                path: pathFor("importRecords"),
                element: <DeferredPage name="Import Records"><ImportRecordsPage /></DeferredPage>,
                handle: { crumb: "Import Records" },
              },
              {
                path: pathFor("roleRequests"),
                element: <DeferredPage name="Role Requests"><RoleRequestsPage /></DeferredPage>,
                handle: { crumb: "Role Requests", width: "full" },
              },
              {
                path: pathFor("downloadRequests"),
                element: <DeferredPage name="Download Requests"><DownloadRequestsPage /></DeferredPage>,
                handle: { crumb: "Download Requests", width: "full" },
              },
              {
                path: pathFor("deleteRequests"),
                element: <DeferredPage name="Delete Requests"><DeleteRequestsPage /></DeferredPage>,
                handle: { crumb: "Delete Requests", width: "full" },
              },
            ],
          },
          {
            // RDCO gives Student and Adviser at its own Users address.
            element: <ProtectedRoute allowedRoles={rolesFor("users")} />,
            children: [
              {
                path: pathFor("users"),
                element: <DeferredPage name="Users"><UserListPage /></DeferredPage>,
                handle: { crumb: "Users", width: "full" },
              },
            ],
          },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("adminUsers")} />,
            children: [{
              path: pathFor("adminUsers"),
              element: <DeferredPage name="Users"><UserListPage /></DeferredPage>,
              handle: { crumb: "Users", width: "full" },
            }],
          },
          {
            // The System Admin alone (ADR-051 §3).
            element: <ProtectedRoute allowedRoles={rolesFor("audit")} />,
            children: [
              {
                path: pathFor("audit"),
                element: <DeferredPage name="Audit Log"><AuditLogPage /></DeferredPage>,
                handle: { crumb: "Audit Log", width: "full" },
              },
            ],
          },

          // Any other address (IR-745). Behind sign-in like every app
          // address, so a signed-out visitor learns nothing about which
          // paths exist, and inside the shell so the way out is in reach.
          { path: "*", element: <NotFoundScreen /> },
        ],
        }],
      },
    ],
  },
  ],
}];

export const router = createBrowserRouter(routes);
