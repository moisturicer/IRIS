import { lazy } from "react";
import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ReviewAccessRoute } from "@/components/auth/ReviewAccessRoute";
import { RouteTitle } from "@/components/layout/RouteTitle";
import { pathFor, rolesFor } from "@/lib/access";
import { redirectRoutes } from "./redirects";

// Auth pages
import LoginPage         from "@/features/auth/LoginPage";
import SignupPage        from "@/features/auth/SignupPage";
import VerifyEmailPage from "@/features/auth/VerifyEmailPage";
import ResendVerificationPage from "@/features/auth/ResendVerificationPage";
import ForgotPasswordPage from "@/features/auth/ForgotPasswordPage";
import ResetPasswordPage  from "@/features/auth/ResetPasswordPage";

// App shell (sidebar + header wrapper)
import { AppShell } from "@/components/layout/AppShell";

// Feature pages
import HomePage             from "@/features/dashboard/HomePage";
import { CallsAndConferencesPage } from "@/features/opportunities/CallsAndConferencesPage";
import { MyCallsPage } from "@/features/opportunities/MyCallsPage";
import MyLibraryPage        from "@/features/library/MyLibraryPage";
import MyReviewsPage        from "@/features/review/MyReviewsPage";
import ReviewAnalyticsPage  from "@/features/review/ReviewAnalyticsPage";
import OfficeConsolePage    from "@/features/review/OfficeConsolePage";

import NotificationsPage    from "@/features/notifications/NotificationsPage";
import SettingsPage         from "@/features/settings/SettingsPage";
import ProfilePage          from "@/features/profile/ProfilePage";
import EditProfilePage      from "@/features/profile/EditProfilePage";
import PersonProfilePage    from "@/features/profile/PersonProfilePage";
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
const CallRequestsPage = lazy(() => import("@/features/opportunities/CallRequestsPage"));
const SetupPage = lazy(() => import("@/features/setup/SetupPage"));
const MyTemplatesPage = lazy(() => import("@/features/myTemplates/MyTemplatesPage"));
const DeleteRequestsPage = lazy(() => import("@/features/admin/DeleteRequestsPage"));
const ReportedCommentsPage = lazy(() => import("@/features/admin/ReportedCommentsPage"));
const AuditLogPage = lazy(() => import("@/features/audit/AuditLogPage"));
const AccountDeletionRequestsPage = lazy(() => import("@/features/admin/AccountDeletionRequestsPage"));
const RetentionPage = lazy(() => import("@/features/admin/RetentionPage"));

export const routes: RouteObject[] = [{
  // The last resort (IR-745): a crash outside the shell's own boundary below,
  // in a public page or in the shell itself, is drawn with no shell at all.
  errorElement: <RouteErrorScreen standalone />,
  // Names the browser tab for every page below, public or not (IR-1073): from
  // the deepest `handle.title`, else `handle.crumb`.
  element: <RouteTitle />,
  children: [
  { path: "/login",  element: <LoginPage />,  handle: { title: "Sign in" } },
  { path: "/signup", element: <SignupPage />, handle: { title: "Create account" } },
  // ADR-045 (IR-643). Public: verifying never requires signing in.
  { path: "/verify-email", element: <VerifyEmailPage />, handle: { title: "Verify your email" } },
  { path: "/verify-email/resend", element: <ResendVerificationPage />, handle: { title: "Send a new verification email" } },
  // Retired link shapes (IR-643, ADR-045 §8): the same page, which strips the
  // address and offers a new email. Nothing on them verifies.
  { path: "/activate", element: <VerifyEmailPage />, handle: { title: "Verify your email" } },
  { path: "/activate/:uidb64/:token", element: <VerifyEmailPage />, handle: { title: "Verify your email" } },
  // ADR-045 (IR-642). Public: recovery must never require signing in.
  { path: "/password/forgot", element: <ForgotPasswordPage />, handle: { title: "Reset your password" } },
  { path: "/password/reset",  element: <ResetPasswordPage />,  handle: { title: "Choose a new password" } },

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
          // The tab reads the paper's own title once it loads (IR-1073).
          {
            path: "records/:id",
            element: <DeferredPage message="Opening the paper"><PaperViewPage /></DeferredPage>,
            handle: { title: "Paper", width: "full" },
          },
          { path: "records/mine",          element: <MyLibraryPage />,   handle: { crumb: "My Library" } },
          { path: "opportunities",         element: <CallsAndConferencesPage />, handle: { crumb: "Calls & Conferences" } },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("myCalls")} />,
            children: [
              { path: pathFor("myCalls"), element: <MyCallsPage />, handle: { crumb: "My Calls" } },
            ],
          },
          {
            // An Adviser's own proposal Templates (ADR-063 decision 8, IR-975).
            element: <ProtectedRoute allowedRoles={rolesFor("myTemplates")} />,
            children: [
              {
                path: pathFor("myTemplates"),
                element: <DeferredPage message="Loading your Templates"><MyTemplatesPage /></DeferredPage>,
                handle: { crumb: "My Templates" },
              },
            ],
          },
          { path: "notifications",         element: <NotificationsPage />, handle: { crumb: "Notifications" } },
          {
            // `/ai` picks a conversation and replaces itself with that
            // conversation's own address (IR-548). Both render the same page,
            // in the same position, so moving between them keeps its state.
            path: "ai", handle: { crumb: "Ask IRIS" },
            children: [
              {
                index: true,
                element: <DeferredPage message="Opening Ask IRIS"><RAGChatPage /></DeferredPage>,
              },
              {
                path: "conversations/:conversationId",
                element: <DeferredPage message="Opening Ask IRIS"><RAGChatPage /></DeferredPage>,
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
          // Another person's Profile (IR-700); its breadcrumb is Discover / People (IR-1133).
          { path: "people/:id",            element: <PersonProfilePage />, handle: { crumb: "People" } },

          {
            element: <ProtectedRoute allowedRoles={rolesFor("reviewQueue")} />,
            children: [
              {
                // Only a user with review work (IR-413); anyone else goes to Discover.
                element: <ReviewAccessRoute />,
                children: [
                  { path: "review",          element: <MyReviewsPage />,       handle: { crumb: "My Reviews" } },
                ],
              },
            ],
          },
          {
            // A coordinator's console (IR-623). The server refuses anyone else.
            // Gated by its own entry in the access map, the one the sidebar
            // lists it from (IR-1085), and still only with review work.
            element: <ProtectedRoute allowedRoles={rolesFor("reviewOffice")} />,
            children: [
              {
                element: <ReviewAccessRoute />,
                children: [
                  { path: "review/office", element: <OfficeConsolePage />, handle: { crumb: "Office console" } },
                ],
              },
            ],
          },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("reviewAnalytics")} />,
            children: [
              { path: pathFor("reviewAnalytics"), element: <ReviewAnalyticsPage />, handle: { crumb: "Workflow analytics", width: "full" } },
            ],
          },

          {
            // RDCO coordination. `Import Records` is the "file on behalf of"
            // path -- which is why RDCO does not also get the submission wizard.
            element: <ProtectedRoute allowedRoles={rolesFor("importRecords")} />,
            children: [
              {
                path: pathFor("importRecords"),
                element: <DeferredPage message="Loading the import page"><ImportRecordsPage /></DeferredPage>,
                handle: { crumb: "Import records" },
              },
              {
                path: pathFor("roleRequests"),
                element: <DeferredPage message="Loading role requests"><RoleRequestsPage /></DeferredPage>,
                handle: { crumb: "Role requests", width: "full" },
              },
              {
                path: pathFor("downloadRequests"),
                element: <DeferredPage message="Loading download requests"><DownloadRequestsPage /></DeferredPage>,
                handle: { crumb: "Download requests", width: "full" },
              },
              {
                path: pathFor("callRequests"),
                element: <DeferredPage message="Loading call requests"><CallRequestsPage /></DeferredPage>,
                handle: { crumb: "Call requests" },
              },
              {
                path: pathFor("deleteRequests"),
                element: <DeferredPage message="Loading delete requests"><DeleteRequestsPage /></DeferredPage>,
                handle: { crumb: "Delete requests", width: "full" },
              },
              {
                path: pathFor("setup"),
                element: <DeferredPage message="Loading setup"><SetupPage /></DeferredPage>,
                handle: { crumb: "Setup" },
              },
            ],
          },
          {
            // RDCO gives Student and Adviser at its own Users address.
            element: <ProtectedRoute allowedRoles={rolesFor("users")} />,
            children: [
              {
                path: pathFor("users"),
                element: <DeferredPage message="Loading users"><UserListPage /></DeferredPage>,
                handle: { crumb: "Users", width: "full" },
              },
            ],
          },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("adminUsers")} />,
            children: [{
              path: pathFor("adminUsers"),
              element: <DeferredPage message="Loading users"><UserListPage /></DeferredPage>,
              handle: { crumb: "Users", width: "full" },
            }],
          },
          {
            // The System Admin alone (ADR-051 §3).
            element: <ProtectedRoute allowedRoles={rolesFor("audit")} />,
            children: [
              {
                path: pathFor("audit"),
                element: <DeferredPage message="Loading the audit log"><AuditLogPage /></DeferredPage>,
                handle: { crumb: "Audit Log", width: "full" },
              },
            ],
          },
          {
            // The System Admin alone (ADR-051 §8, IR-788).
            element: <ProtectedRoute allowedRoles={rolesFor("accountDeletionRequests")} />,
            children: [{
              path: pathFor("accountDeletionRequests"),
              element: <DeferredPage message="Loading account deletion requests"><AccountDeletionRequestsPage /></DeferredPage>,
              handle: { crumb: "Account Deletions", width: "full" },
            }],
          },
          {
            // The System Admin alone (ADR-051 §3 and §19, IR-795).
            element: <ProtectedRoute allowedRoles={rolesFor("retention")} />,
            children: [{
              path: pathFor("retention"),
              element: <DeferredPage message="Loading retention"><RetentionPage /></DeferredPage>,
              handle: { crumb: "Retention" },
            }],
          },
          {
            // RDCO and the System Admin share it (IR-693, decision 2026-11-15).
            element: <ProtectedRoute allowedRoles={[...rolesFor("reportedComments"), ...rolesFor("adminReportedComments")]} />,
            children: [{
              path: pathFor("reportedComments"),
              element: <DeferredPage message="Loading reported comments"><ReportedCommentsPage /></DeferredPage>,
              handle: { crumb: "Reported comments" },
            }],
          },

          // Any other address (IR-745). Behind sign-in like every app
          // address, so a signed-out visitor learns nothing about which
          // paths exist, and inside the shell so the way out is in reach.
          { path: "*", element: <NotFoundScreen />, handle: { title: "Page not found" } },
        ],
        }],
      },
    ],
  },
  ],
}];

export const router = createBrowserRouter(routes);
