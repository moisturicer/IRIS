/**
 * The font-size guard's allowance (IR-1037): how many arbitrary font sizes each
 * file may still contain. See `fontSize.test.ts` for the rule.
 *
 * It only shrinks. A file may use fewer than its allowance, and the test then
 * fails until the number is lowered here, so a cleaned file cannot slip back.
 * Remove a file's entry when it reaches zero. Adding a file or raising a number
 * needs a reason in the PR.
 */

/** Sizes of 12 px or more, by file. */
export const FONT_SIZE_ALLOWANCE: Record<string, number> = {
  "src/components/layout/Breadcrumbs.tsx": 1,
  "src/components/layout/NotificationBell.tsx": 7,
  "src/components/shared/RequestStatusChip.tsx": 1,
  "src/features/discover/DiscoverFilterBar.tsx": 2,
  "src/features/discover/DiscoverFilterDropdown.tsx": 1,
  "src/features/discover/DiscoverPage.tsx": 2,
  "src/features/discover/DiscoverResultCard.tsx": 3,
  "src/features/discover/MyFeeds.tsx": 1,
  "src/features/discover/PaperCiteModal.tsx": 1,
  "src/features/library/LibraryRecordTable.tsx": 7,
  "src/features/notifications/NotificationsPage.tsx": 2,
  "src/features/profile/PersonProfileView.tsx": 1,
  "src/features/records/paper-view/AddReviewerDialog.tsx": 1,
  "src/features/records/paper-view/DecisionDialog.tsx": 4,
  "src/features/records/paper-view/NewVersionDialog.tsx": 4,
  "src/features/records/paper-view/OfficeReviewDialog.tsx": 2,
  "src/features/records/paper-view/RequestRevisionDialog.tsx": 2,
  "src/features/records/paper-view/RouteDialog.tsx": 7,
  "src/features/records/paper-view/threads/FinishReviewDialog.tsx": 3,
  "src/features/review/AssignReviewerDialog.tsx": 1,
};

/**
 * Sizes under 12 px, by file: below the spec's floor, so kept apart. When this
 * is empty the floor holds everywhere and the test needs no exceptions.
 */
export const SUB_12PX_ALLOWANCE: Record<string, number> = {
  "src/components/layout/NotificationBell.tsx": 1,
  "src/features/discover/DiscoverFilterDropdown.tsx": 1,
  "src/features/discover/DiscoverResultCard.tsx": 1,
  "src/features/discover/MyFeeds.tsx": 2,
  "src/features/discover/PaperCiteModal.tsx": 1,
  "src/features/discover/discoverUtils.ts": 1,
  "src/features/library/LibraryRecordTable.tsx": 6,
  "src/features/records/paper-view/RouteDialog.tsx": 2,
  "src/features/records/paper-view/threads/ReviewThreads.tsx": 2,
};
