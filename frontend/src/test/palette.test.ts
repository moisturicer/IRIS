/**
 * The palette guard (IR-358): no off-palette colour class anywhere in the
 * frontend source, except in files not yet converted.
 *
 * It reads every `.ts`, `.tsx` and `.css` file under `src/` as text and fails
 * naming each file and class. This file is the one exception, because its
 * fixtures are off-palette on purpose.
 */
import { describe, expect, it } from "vitest";

import { offPaletteClasses } from "./palette";

/**
 * IR-357: files not yet converted to the white, black, grey and maroon
 * palette. **This list must only shrink.** Each IR-357 subtask removes its own
 * files as it converts them, and IR-366 deletes the list. Never add a file to
 * it: convert the colour instead. A file that no longer has an off-palette
 * colour fails the guard until it is taken off.
 *
 * Grouped by the subtask whose scope names the file. It started with the 48
 * files found on 2026-09-25.
 */
const NOT_YET_CONVERTED: readonly string[] = [
  // IR-360 -- the submission wizard
  "src/features/records/AddRecordPage.tsx",
  "src/features/records/EditRecordPage.tsx",
  "src/features/records/steps/PaperDetailsStep.tsx",
  "src/features/records/steps/RecordDetailsStep.tsx",
  "src/features/records/steps/TitleAbstractStep.tsx",
  "src/features/records/steps/TypeRouteStep.tsx",
  "src/features/records/steps/UploadsStep.tsx",
  // IR-361 -- My Workspace, review and clearance
  "src/features/records/MyWorkspacePage.tsx",
  "src/features/records/WorkspaceOfficePills.tsx",
  "src/features/review/ApprovedProposalsPage.tsx",
  "src/features/review/EvaluationPage.tsx",
  "src/features/review/PeerClearanceStrip.tsx",
  "src/features/review/queueFilters.ts",
  "src/features/review/ReviewQueuePage.tsx",
  // IR-362 -- Discover, My Library, Calls & Conferences, Notifications
  "src/features/discover/DiscoverPage.tsx",
  "src/features/discover/DiscoverRecordCard.tsx",
  "src/features/discover/discoverUtils.ts",
  "src/features/library/MyLibraryPage.tsx",
  "src/features/notifications/NotificationsPage.tsx",
  "src/features/opportunities/CallsAndConferencesPage.tsx",
  "src/features/opportunities/opportunityUtils.ts",
  // IR-363 -- Documents and the admin screens
  "src/features/accounts/RoleRequestsPage.tsx",
  "src/features/admin/DeleteRequestsPage.tsx",
  "src/features/admin/DownloadRequestsPage.tsx",
  "src/features/admin/SessionsPage.tsx",
  "src/features/documents/DocumentsPage.tsx",
  "src/features/download/DownloadTokenPage.tsx",
  "src/features/requests/AccessRequestsPage.tsx",
  // IR-364 -- sign-up, account and error screens
  "src/features/auth/EmailVerifyPage.tsx",
  "src/features/auth/PendingApprovalPage.tsx",
  "src/features/auth/SignupPage.tsx",
  "src/features/errors/ForbiddenPage.tsx",
  "src/features/settings/SettingsPage.tsx",
  // IR-365 -- the Ask IRIS hub and chat page
  "src/features/ai/AIHubPage.tsx",
  "src/features/ai/components/ConversationSidebar.tsx",
  "src/features/ai/RAGChatPage.tsx",
];

const THIS_FILE = "src/test/palette.test.ts";

/** Every source file, keyed `src/...`, read as text. */
const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.{ts,tsx,css}", {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  ).map(([path, text]) => [path.replace(/^\//, ""), text]),
);

describe("what counts as off-palette", () => {
  it("catches a hue family on any colour utility, with variants and opacity", () => {
    expect(
      offPaletteClasses(
        'className="bg-red-50 hover:text-emerald-700 md:border-t-amber-200 ring-sky-500/40 !from-violet-950"',
      ),
    ).toEqual([
      "bg-red-50", "text-emerald-700", "border-t-amber-200", "ring-sky-500", "from-violet-950",
    ]);
  });

  it("catches brand-400 to brand-600, the bright reds, and no other brand shade", () => {
    expect(
      offPaletteClasses("bg-brand-400 text-brand-500 ring-brand-600 bg-brand-50 ring-brand-200 text-brand-700"),
    ).toEqual(["bg-brand-400", "text-brand-500", "ring-brand-600"]);
  });

  it("lets white, black, grey and maroon through", () => {
    expect(
      offPaletteClasses(
        "bg-white text-black bg-stone-100 text-stone-700 border-gray-200 text-slate-500 " +
        "bg-brand text-brand-light bg-brand-dark bg-brand-50 ring-brand/40",
      ),
    ).toEqual([]);
  });

  it("does not mistake a word that merely contains a hue for a class", () => {
    expect(offPaletteClasses("redirect-500 skyline-100 prefix-bg-red-500 bg-red-5000")).toEqual([]);
  });
});

describe("the palette guard", () => {
  it("reads the whole source tree, not an empty one", () => {
    // A broken glob would make both guards below pass by reading nothing.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(100);
    expect(SOURCES["src/components/shared/StatusBadge.tsx"]).toContain("StatusBadge");
    expect(SOURCES["src/index.css"]).toBeDefined();
  });

  it("finds no off-palette colour outside the not-yet-converted files", () => {
    const allowed = new Set([...NOT_YET_CONVERTED, THIS_FILE]);
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => !allowed.has(path))
        .map(([path, text]) => [path, offPaletteClasses(text)])
        .filter(([, classes]) => classes.length > 0),
    );

    expect(
      offenders,
      "Off-palette colours (01-design-system.md section 0). Use stone, brand or a TONES entry " +
      "from components/ui/statusTones.ts; do not add the file to NOT_YET_CONVERTED.",
    ).toEqual({});
  });

  it("finds an off-palette colour in every not-yet-converted file, so the list only shrinks", () => {
    const converted = NOT_YET_CONVERTED.filter(
      (path) => offPaletteClasses(SOURCES[path] ?? "").length === 0,
    );

    expect(
      converted,
      "Converted, renamed or deleted: take these off NOT_YET_CONVERTED in src/test/palette.test.ts.",
    ).toEqual([]);
  });

  it("lists each not-yet-converted file once", () => {
    expect(new Set(NOT_YET_CONVERTED).size).toBe(NOT_YET_CONVERTED.length);
  });
});
