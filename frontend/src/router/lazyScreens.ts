/**
 * Every screen that loads on demand, and the paths that can prefetch it (IR-1248).
 *
 * IR-749 deferred the heaviest screens; IR-1248 defers the rest, so the main
 * bundle carries the shell and the two screens a visit can open on (Discover
 * and Sign in, imported by the router directly: deferring the first screen
 * would add a second download before anything is drawn).
 *
 * `preloadScreen(path)` starts a screen's download early: the sidebar and the
 * account menu call it on hover and focus, so a click usually finds the code
 * already here. The module system caches each `import()`, so preloading and
 * then rendering fetch a chunk once.
 */
import { lazy, type ComponentType } from "react";

import { pathFor } from "@/lib/access";

type Loader = () => Promise<{ default: ComponentType }>;

/** The loader for each prefetchable path. A path with a parameter is not listed. */
export const SCREEN_LOADERS = new Map<string, Loader>();

function screen(load: Loader, ...paths: string[]) {
  for (const path of paths) SCREEN_LOADERS.set(path, load);
  return lazy(load);
}

/** Start loading the screen at `path`, if it has one. Never rejects: a failed prefetch is retried by the route. */
export async function preloadScreen(path: string): Promise<void> {
  try {
    await SCREEN_LOADERS.get(path)?.();
  } catch {
    // The route's own lazy import tries again, and its error screen reports a real failure.
  }
}

/**
 * Preload the screens at `paths` once the browser has nothing else to do, and
 * return a cancel for an effect's cleanup. Sign in uses it for the two screens
 * it leads to, so Create an account opens without a spinner (IR-1262).
 */
export function preloadWhenIdle(paths: string[]): () => void {
  const run = () => {
    for (const path of paths) void preloadScreen(path);
  };
  if (typeof window.requestIdleCallback === "function") {
    const id = window.requestIdleCallback(run, { timeout: 2_000 });
    return () => window.cancelIdleCallback(id);
  }
  const id = window.setTimeout(run, 200);
  return () => window.clearTimeout(id);
}

// Sign-up and account recovery (public). Sign in preloads sign-up and password
// reset (IR-1262).
export const SignupPage = screen(() => import("@/features/auth/SignupPage"), "/signup");
export const VerifyEmailPage = screen(() => import("@/features/auth/VerifyEmailPage"));
export const ResendVerificationPage = screen(() => import("@/features/auth/ResendVerificationPage"));
export const ForgotPasswordPage = screen(() => import("@/features/auth/ForgotPasswordPage"), "/password/forgot");
export const ResetPasswordPage = screen(() => import("@/features/auth/ResetPasswordPage"));

// Everyone's screens.
export const MyLibraryPage = screen(() => import("@/features/library/MyLibraryPage"), pathFor("library"));
export const CallsAndConferencesPage = screen(
  () => import("@/features/opportunities/CallsAndConferencesPage").then((m) => ({ default: m.CallsAndConferencesPage })),
  pathFor("opportunities"),
);
export const MyCallsPage = screen(
  () => import("@/features/opportunities/MyCallsPage").then((m) => ({ default: m.MyCallsPage })),
  pathFor("myCalls"),
);
export const NotificationsPage = screen(() => import("@/features/notifications/NotificationsPage"), pathFor("notifications"));
export const SettingsPage = screen(() => import("@/features/settings/SettingsPage"), pathFor("settings"));
export const ProfilePage = screen(() => import("@/features/profile/ProfilePage"), pathFor("profile"));
export const PersonProfilePage = screen(() => import("@/features/profile/PersonProfilePage"));
export const GuidelinesPage = screen(() => import("@/features/guidelines/GuidelinesPage"), pathFor("guidelines"));
export const RAGChatPage = screen(() => import("@/features/ai/RAGChatPage"), pathFor("ai"));
export const PaperViewPage = screen(() => import("@/features/records/paper-view/PaperViewPage"));

// Review.
export const MyReviewsPage = screen(() => import("@/features/review/MyReviewsPage"), pathFor("reviewQueue"));
export const OfficeConsolePage = screen(() => import("@/features/review/OfficeConsolePage"), pathFor("reviewOffice"));
export const ReviewAnalyticsPage = screen(() => import("@/features/review/ReviewAnalyticsPage"), pathFor("reviewAnalytics"));
export const MyTemplatesPage = screen(() => import("@/features/myTemplates/MyTemplatesPage"), pathFor("myTemplates"));

// RDCO and the System Admin.
export const ImportRecordsPage = screen(() => import("@/features/records/ImportRecordsPage"), pathFor("importRecords"));
export const UserListPage = screen(() => import("@/features/accounts/UserListPage"), pathFor("users"), pathFor("adminUsers"));
export const RoleRequestsPage = screen(() => import("@/features/accounts/RoleRequestsPage"), pathFor("roleRequests"));
export const DownloadRequestsPage = screen(() => import("@/features/admin/DownloadRequestsPage"), pathFor("downloadRequests"));
export const CallRequestsPage = screen(() => import("@/features/opportunities/CallRequestsPage"), pathFor("callRequests"));
export const SetupPage = screen(() => import("@/features/setup/SetupPage"), pathFor("setup"));
export const DeleteRequestsPage = screen(() => import("@/features/admin/DeleteRequestsPage"), pathFor("deleteRequests"));
export const ReportedCommentsPage = screen(() => import("@/features/admin/ReportedCommentsPage"), pathFor("reportedComments"));
export const AuditLogPage = screen(() => import("@/features/audit/AuditLogPage"), pathFor("audit"));
export const AccountDeletionRequestsPage = screen(
  () => import("@/features/admin/AccountDeletionRequestsPage"),
  pathFor("accountDeletionRequests"),
);
export const RetentionPage = screen(() => import("@/features/admin/RetentionPage"), pathFor("retention"));
