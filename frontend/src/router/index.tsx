import { createBrowserRouter, type RouteObject } from "react-router-dom";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { ReviewAccessRoute } from "@/components/auth/ReviewAccessRoute";
import { RouteTitle } from "@/components/layout/RouteTitle";
import { pathFor, rolesFor } from "@/lib/access";
import { redirectRoutes } from "./redirects";

// The two screens a visit can open on stay in the main bundle (IR-1248):
// deferring the first screen would add a second download before anything is drawn.
import LoginPage from "@/features/auth/LoginPage";
import HomePage  from "@/features/dashboard/HomePage";

// App shell (sidebar + header wrapper)
import { AppShell } from "@/components/layout/AppShell";

// Error screens (IR-745)
import { NotFoundScreen }   from "@/features/errors/NotFoundScreen";
import { RouteErrorScreen } from "@/features/errors/RouteErrorScreen";
import { DeferredPage } from "./DeferredPage";

// Every other screen loads on demand, from one registry that also lets the
// sidebar prefetch it (IR-749, IR-1248).
import {
  AccountDeletionRequestsPage, AuditLogPage, CallRequestsPage, CallsAndConferencesPage,
  DeleteRequestsPage, DownloadRequestsPage, EditProfilePage, ForgotPasswordPage, GuidelinesPage,
  ImportRecordsPage, MyCallsPage, MyLibraryPage, MyReviewsPage, MyTemplatesPage, NotificationsPage,
  OfficeConsolePage, PaperViewPage, PersonProfilePage, ProfilePage, RAGChatPage, ReportedCommentsPage,
  ResendVerificationPage, ResetPasswordPage, RetentionPage, ReviewAnalyticsPage, RoleRequestsPage,
  SettingsPage, SetupPage, SignupPage, UserListPage, VerifyEmailPage,
} from "./lazyScreens";

export const routes: RouteObject[] = [{
  // The last resort (IR-745): a crash outside the shell's own boundary below,
  // in a public page or in the shell itself, is drawn with no shell at all.
  errorElement: <RouteErrorScreen standalone />,
  // Names the browser tab for every page below, public or not (IR-1073): from
  // the deepest `handle.title`.
  element: <RouteTitle />,
  children: [
  { path: "/login",  element: <LoginPage />,  handle: { title: "Sign in" } },
  { path: "/signup", element: <DeferredPage message="Loading sign-up"><SignupPage /></DeferredPage>, handle: { title: "Create account" } },
  // ADR-045 (IR-643). Public: verifying never requires signing in.
  { path: "/verify-email", element: <DeferredPage message="Loading email verification"><VerifyEmailPage /></DeferredPage>, handle: { title: "Verify your email" } },
  { path: "/verify-email/resend", element: <DeferredPage message="Loading email verification"><ResendVerificationPage /></DeferredPage>, handle: { title: "Send a new verification email" } },
  // Retired link shapes (IR-643, ADR-045 §8): the same page, which strips the
  // address and offers a new email. Nothing on them verifies.
  { path: "/activate", element: <DeferredPage message="Loading email verification"><VerifyEmailPage /></DeferredPage>, handle: { title: "Verify your email" } },
  { path: "/activate/:uidb64/:token", element: <DeferredPage message="Loading email verification"><VerifyEmailPage /></DeferredPage>, handle: { title: "Verify your email" } },
  // ADR-045 (IR-642). Public: recovery must never require signing in.
  { path: "/password/forgot", element: <DeferredPage message="Loading password reset"><ForgotPasswordPage /></DeferredPage>, handle: { title: "Reset your password" } },
  { path: "/password/reset",  element: <DeferredPage message="Loading password reset"><ResetPasswordPage /></DeferredPage>,  handle: { title: "Choose a new password" } },

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
          { index: true, element: <HomePage />, handle: { title: "Discover" } },
          // Retired URLs (spec §4.1). Outside the role gates: a redirect only
          // moves the address, and the page it lands on applies its own.
          ...redirectRoutes,
          // The reading header is this page's navigation (IR-569).
          // The tab reads the paper's own title once it loads (IR-1073).
          {
            path: "records/:id",
            element: <DeferredPage message="Opening the paper"><PaperViewPage /></DeferredPage>,
            handle: { title: "Paper", width: "full" },
          },
          { path: "records/mine",          element: <DeferredPage message="Loading your Library"><MyLibraryPage /></DeferredPage>,   handle: { title: "My Library" } },
          { path: "opportunities",         element: <DeferredPage message="Loading calls and conferences"><CallsAndConferencesPage /></DeferredPage>, handle: { title: "Calls & Conferences" } },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("myCalls")} />,
            children: [
              { path: pathFor("myCalls"), element: <DeferredPage message="Loading your calls"><MyCallsPage /></DeferredPage>, handle: { title: "My Calls" } },
            ],
          },
          {
            // An Adviser's own proposal Templates (ADR-063 decision 8, IR-975).
            element: <ProtectedRoute allowedRoles={rolesFor("myTemplates")} />,
            children: [
              {
                path: pathFor("myTemplates"),
                element: <DeferredPage message="Loading your Templates"><MyTemplatesPage /></DeferredPage>,
                handle: { title: "My Templates" },
              },
            ],
          },
          {
            // What each record type needs (ADR-063 decision 7, IR-974): everyone's.
            path: pathFor("guidelines"),
            element: <DeferredPage message="Loading the guidelines"><GuidelinesPage /></DeferredPage>,
            handle: { title: "Guidelines" },
          },
          { path: "notifications",         element: <DeferredPage message="Loading notifications"><NotificationsPage /></DeferredPage>, handle: { title: "Notifications" } },
          {
            // `/ai` picks a conversation and replaces itself with that
            // conversation's own address (IR-548). Both render the same page,
            // in the same position, so moving between them keeps its state.
            path: "ai", handle: { title: "Ask IRIS" },
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
          {
            // Edit profile sits under Profile; its Cancel returns there.
            path: "profile", handle: { title: "Profile" },
            children: [
              { index: true,  element: <DeferredPage message="Loading your profile"><ProfilePage /></DeferredPage> },
              { path: "edit", element: <DeferredPage message="Loading your profile"><EditProfilePage /></DeferredPage>, handle: { title: "Edit profile" } },
            ],
          },
          { path: "settings",              element: <DeferredPage message="Loading settings"><SettingsPage /></DeferredPage>,    handle: { title: "Settings" } },
          // Another person's Profile (IR-700, IR-1133).
          { path: "people/:id",            element: <DeferredPage message="Loading the profile"><PersonProfilePage /></DeferredPage>, handle: { title: "People" } },

          {
            element: <ProtectedRoute allowedRoles={rolesFor("reviewQueue")} />,
            children: [
              {
                // Only a user with review work (IR-413); anyone else goes to Discover.
                element: <ReviewAccessRoute />,
                children: [
                  { path: "review",          element: <DeferredPage message="Loading My Reviews"><MyReviewsPage /></DeferredPage>,       handle: { title: "My Reviews" } },
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
                  { path: "review/office", element: <DeferredPage message="Loading the office console"><OfficeConsolePage /></DeferredPage>, handle: { title: "Office console" } },
                ],
              },
            ],
          },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("reviewAnalytics")} />,
            children: [
              { path: pathFor("reviewAnalytics"), element: <DeferredPage message="Loading workflow analytics"><ReviewAnalyticsPage /></DeferredPage>, handle: { title: "Workflow analytics", width: "full" } },
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
                handle: { title: "Import records" },
              },
              {
                path: pathFor("roleRequests"),
                element: <DeferredPage message="Loading role requests"><RoleRequestsPage /></DeferredPage>,
                handle: { title: "Role requests", width: "full" },
              },
              {
                path: pathFor("downloadRequests"),
                element: <DeferredPage message="Loading download requests"><DownloadRequestsPage /></DeferredPage>,
                handle: { title: "Download requests", width: "full" },
              },
              {
                path: pathFor("callRequests"),
                element: <DeferredPage message="Loading call requests"><CallRequestsPage /></DeferredPage>,
                handle: { title: "Call requests" },
              },
              {
                path: pathFor("deleteRequests"),
                element: <DeferredPage message="Loading delete requests"><DeleteRequestsPage /></DeferredPage>,
                handle: { title: "Delete requests", width: "full" },
              },
              {
                path: pathFor("setup"),
                element: <DeferredPage message="Loading setup"><SetupPage /></DeferredPage>,
                handle: { title: "Setup" },
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
                handle: { title: "Users", width: "full" },
              },
            ],
          },
          {
            element: <ProtectedRoute allowedRoles={rolesFor("adminUsers")} />,
            children: [{
              path: pathFor("adminUsers"),
              element: <DeferredPage message="Loading users"><UserListPage /></DeferredPage>,
              handle: { title: "Users", width: "full" },
            }],
          },
          {
            // The System Admin alone (ADR-051 §3).
            element: <ProtectedRoute allowedRoles={rolesFor("audit")} />,
            children: [
              {
                path: pathFor("audit"),
                element: <DeferredPage message="Loading the audit log"><AuditLogPage /></DeferredPage>,
                handle: { title: "Audit Log", width: "full" },
              },
            ],
          },
          {
            // The System Admin alone (ADR-051 §8, IR-788).
            element: <ProtectedRoute allowedRoles={rolesFor("accountDeletionRequests")} />,
            children: [{
              path: pathFor("accountDeletionRequests"),
              element: <DeferredPage message="Loading account deletion requests"><AccountDeletionRequestsPage /></DeferredPage>,
              handle: { title: "Account Deletions", width: "full" },
            }],
          },
          {
            // The System Admin alone (ADR-051 §3 and §19, IR-795).
            element: <ProtectedRoute allowedRoles={rolesFor("retention")} />,
            children: [{
              path: pathFor("retention"),
              element: <DeferredPage message="Loading retention"><RetentionPage /></DeferredPage>,
              handle: { title: "Retention" },
            }],
          },
          {
            // RDCO and the System Admin share it (IR-693, decision 2026-11-15).
            element: <ProtectedRoute allowedRoles={[...rolesFor("reportedComments"), ...rolesFor("adminReportedComments")]} />,
            children: [{
              path: pathFor("reportedComments"),
              element: <DeferredPage message="Loading reported comments"><ReportedCommentsPage /></DeferredPage>,
              handle: { title: "Reported comments" },
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
