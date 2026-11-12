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
  "src/components/auth/AuthAlert.tsx": 3,
  "src/components/auth/LoginForm.tsx": 1,
  "src/components/layout/Breadcrumbs.tsx": 1,
  "src/components/layout/NotificationBell.tsx": 7,
  "src/components/records/DownloadRequestModal.tsx": 5,
  "src/components/shared/ConfirmDialog.tsx": 1,
  "src/components/shared/DataTable.tsx": 5,
  "src/components/shared/RequestStatusChip.tsx": 1,
  "src/components/shared/ResearchCard.tsx": 1,
  "src/components/ui/Badge.tsx": 1,
  "src/components/ui/Button.tsx": 3,
  "src/components/ui/Card.tsx": 2,
  "src/components/ui/FieldError.tsx": 1,
  "src/components/ui/Input.tsx": 3,
  "src/components/ui/Modal.tsx": 2,
  "src/components/ui/Select.tsx": 3,
  "src/components/ui/Toast.tsx": 2,
  "src/components/ui/fieldClasses.ts": 3,
  "src/features/accounts/RoleRequestsPage.tsx": 5,
  "src/features/accounts/UserListPage.tsx": 2,
  "src/features/admin/AccountDeletionRequestsPage.tsx": 10,
  "src/features/admin/DeleteRequestsPage.tsx": 7,
  "src/features/admin/DownloadRequestsPage.tsx": 9,
  "src/features/admin/RetentionPage.tsx": 4,
  "src/features/admin/SessionsPage.tsx": 5,
  "src/features/ai/AIHubPage.tsx": 6,
  "src/features/ai/components/AskIrisNotice.tsx": 1,
  "src/features/ai/components/AssistantMessageSkeleton.tsx": 1,
  "src/features/ai/components/ChatInput.tsx": 1,
  "src/features/ai/components/ChatMessageBubble.tsx": 1,
  "src/features/ai/components/ChatMessageList.tsx": 2,
  "src/features/ai/components/ChatToolbar.tsx": 3,
  "src/features/ai/components/ConversationSidebar.tsx": 5,
  "src/features/ai/components/CopyButton.tsx": 2,
  "src/features/ai/components/ReasoningBar.tsx": 5,
  "src/features/ai/components/RuntimeReader.tsx": 3,
  "src/features/ai/components/SourceContextPanel.tsx": 7,
  "src/features/ai/components/StreamStatusRow.tsx": 2,
  "src/features/ai/components/TokenUsageMeter.tsx": 4,
  "src/features/auth/EmailRequestForm.tsx": 7,
  "src/features/auth/ResetPasswordPage.tsx": 7,
  "src/features/discover/DiscoverFilterBar.tsx": 2,
  "src/features/discover/DiscoverFilterDropdown.tsx": 1,
  "src/features/discover/DiscoverPage.tsx": 2,
  "src/features/discover/DiscoverResultCard.tsx": 4,
  "src/features/discover/MyFeeds.tsx": 1,
  "src/features/discover/PaperCiteModal.tsx": 1,
  "src/features/library/LibraryRecordTable.tsx": 7,
  "src/features/notifications/NotificationsPage.tsx": 2,
  "src/features/profile/PersonProfileView.tsx": 1,
  "src/features/records/ImportRecordsPage.tsx": 8,
  "src/features/records/paper-view/AddReviewerDialog.tsx": 1,
  "src/features/records/paper-view/DecisionDialog.tsx": 4,
  "src/features/records/paper-view/NewVersionDialog.tsx": 4,
  "src/features/records/paper-view/OfficeReviewDialog.tsx": 2,
  "src/features/records/paper-view/RequestRevisionDialog.tsx": 2,
  "src/features/records/paper-view/RouteDialog.tsx": 7,
  "src/features/records/paper-view/threads/FinishReviewDialog.tsx": 3,
  "src/features/review/AssignReviewerDialog.tsx": 1,
  "src/features/settings/AiAnswerPanel.tsx": 5,
  "src/features/settings/SettingsPage.tsx": 19,
  "src/features/settings/YourDataPanels.tsx": 14,
  "src/features/settings/settingsParts.tsx": 1,
};

/**
 * Sizes under 12 px, by file: below the spec's floor, so kept apart. When this
 * is empty the floor holds everywhere and the test needs no exceptions.
 */
export const SUB_12PX_ALLOWANCE: Record<string, number> = {
  "src/components/layout/NotificationBell.tsx": 1,
  "src/features/ai/AIHubPage.tsx": 2,
  "src/features/ai/components/ChatMessageBubble.tsx": 2,
  "src/features/ai/components/ConversationSidebar.tsx": 2,
  "src/features/ai/components/ModelPill.tsx": 1,
  "src/features/ai/components/ReasoningBar.tsx": 2,
  "src/features/ai/components/RuntimeReader.tsx": 1,
  "src/features/ai/components/SourceContextPanel.tsx": 2,
  "src/features/ai/components/StreamStatusRow.tsx": 1,
  "src/features/discover/DiscoverFilterDropdown.tsx": 1,
  "src/features/discover/DiscoverPage.tsx": 1,
  "src/features/discover/DiscoverResultCard.tsx": 1,
  "src/features/discover/ManuscriptCover.tsx": 1,
  "src/features/discover/MyFeeds.tsx": 2,
  "src/features/discover/PaperCiteModal.tsx": 1,
  "src/features/discover/discoverUtils.ts": 1,
  "src/features/library/LibraryRecordTable.tsx": 6,
  "src/features/records/paper-view/RouteDialog.tsx": 2,
  "src/features/records/paper-view/threads/ReviewThreads.tsx": 2,
};
