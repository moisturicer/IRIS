/**
 * The Publish dialog (IR-408; spec §4.4, Appendix F · F3).
 *
 * Rendered against a mocked API that returns contract-shaped payloads, and
 * driven through the accessible tree. Each `describe` is one acceptance
 * criterion; the browser checks (viewports, keyboard-only run) are recorded on
 * the PR, because jsdom has no layout.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { pretendLaidOut } from "@/test/layout";
import { fireEvent, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";

import { PublishDialog } from "./PublishDialog";

vi.mock("@/api/records", () => ({
  recordsApi: {
    recordTypes: vi.fn(),
    classifications: vi.fn(),
    pscedList: vi.fn(),
    create: vi.fn(),
    answerEmbargo: vi.fn(),
    update: vi.fn(),
    uploadManuscript: vi.fn(),
    submit: vi.fn(),
    detail: vi.fn(),
    metadataSuggestions: vi.fn(),
    retryExtraction: vi.fn(),
    duplicateMatches: vi.fn(),
    acknowledgeDuplicates: vi.fn(),
  },
}));

vi.mock("@/features/records/paper-view/PaperPdfReader", () => ({
  PaperPdfReader: ({ scrollToPage, highlightRegions }: { scrollToPage: number | null; highlightRegions: unknown[] }) => (
    <>
      <p>Shared authenticated PDF reader</p>
      {scrollToPage != null && <p>Reader at page {scrollToPage}, {highlightRegions.length} highlighted</p>}
    </>
  ),
}));

vi.mock("@/api/accounts", () => ({
  accountsApi: { listAdvisers: vi.fn() },
}));

vi.mock("@/api/documents", () => ({
  documentsApi: { slots: vi.fn() },
}));

const { recordsApi } = await import("@/api/records");
const { accountsApi } = await import("@/api/accounts");
const { documentsApi } = await import("@/api/documents");

const SELF_ID = 7;

function page<T>(results: T[]) {
  return { data: { count: results.length, next: null, previous: null, results } };
}

const TYPES = [
  { id: 1, name: "Proposal" },
  { id: 2, name: "Thesis / Research" },
  { id: 3, name: "Project" },
];

const ADVISERS = [
  makeUser({ id: 21, first_name: "Maria", middle_initial: "C.", last_name: "Santos", role_name: ROLES.ADVISER, department_name: "Computer Science" }),
  makeUser({ id: SELF_ID, first_name: "Ada", middle_initial: "", last_name: "Reyes", role_name: ROLES.ADVISER }),
];

function pdf(name = "My_Clearance-Study.pdf", bytes = 2048) {
  return new File([new Uint8Array(bytes)], name, { type: "application/pdf" });
}

/** A promise the test settles by hand, to hold an upload mid-flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function draftDetail(overrides: Record<string, unknown> = {}) {
  return {
    id: 42,
    title: "My Clearance Study",
    abstract: "",
    abstract_file: "/api/v1/records/42/manuscript/",
    year_accomplished: null,
    record_type: "Thesis / Research",
    classification: null,
    psced: null,
    adviser: null,
    authors: [],
    is_ip: false,
    requires_ethics_review: false,
    for_commercialization: false,
    pipeline_status: "draft",
    current_holders: [],
    embargo: { state: "none", until: null },
    ...overrides,
  };
}

const COMPLETE = {
  title: "Clearance-aware resubmission in a research office",
  abstract: "An abstract that is comfortably longer than the thirty-character minimum.",
  year_accomplished: 2026,
  adviser: 21,
  authors: [{ id: 1, name: "Ada Reyes", role: null }],
};

/** A `metadata-suggestions` reply (IR-406's contract). */
function suggestions(state: string, found: { title?: string; abstract?: string } = {}) {
  return {
    data: {
      state,
      suggestions: { title: found.title ?? null, abstract: found.abstract ?? null },
      source: "pdf_structure",
    },
  };
}

beforeEach(() => {
  vi.mocked(recordsApi.recordTypes).mockResolvedValue(page(TYPES) as never);
  vi.mocked(recordsApi.classifications).mockResolvedValue(page([{ id: 5, name: "Computing" }]) as never);
  vi.mocked(recordsApi.pscedList).mockResolvedValue(page([{ id: 9, name: "Information Technology" }]) as never);
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue(page(ADVISERS) as never);
  vi.mocked(recordsApi.create).mockResolvedValue({ data: { id: 42 } } as never);
  vi.mocked(recordsApi.answerEmbargo).mockResolvedValue({ data: { state: "none", until: null } } as never);
  vi.mocked(recordsApi.update).mockResolvedValue({ data: { id: 42 } } as never);
  vi.mocked(recordsApi.uploadManuscript).mockResolvedValue({ data: { id: 42 } } as never);
  vi.mocked(recordsApi.submit).mockResolvedValue({ data: { detail: "Submitted." } } as never);
  vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail() } as never);
  // Ready with nothing found: no chip and no line, so tests of other criteria see
  // Details exactly as before prefill existed.
  vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(suggestions("ready") as never);
  vi.mocked(recordsApi.duplicateMatches).mockResolvedValue({ data: { exact: [], likely: [], acknowledged: false } } as never);
  vi.mocked(recordsApi.acknowledgeDuplicates).mockResolvedValue({ data: { acknowledged: true, matches: [] } } as never);
  useAuthStore.setState({
    user: makeUser({ id: SELF_ID, first_name: "Ada", last_name: "Reyes", role_name: ROLES.ADVISER }),
  });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

function openAtQuestion() {
  return renderScreen(<PublishDialog />, { route: "/?publish=new" });
}

/** A new submission past its first question, answered No: at the manuscript step. */
async function openNew() {
  const view = openAtQuestion();
  fireEvent.click(await screen.findByRole("radio", { name: /^No/ }));
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("radio", { name: /Proposal/ });
  return view;
}

it.each(["draft", "types"])("announces a rate limit while loading Publish %s", async (source) => {
  const failure = { response: { status: 429, headers: { "retry-after": "61" } } };
  if (source === "draft") vi.mocked(recordsApi.detail).mockRejectedValueOnce(failure);
  else vi.mocked(recordsApi.recordTypes).mockRejectedValueOnce(failure);
  renderScreen(<PublishDialog />, { route: "/?publish=42" });
  expect(await screen.findByRole("alert")).toHaveTextContent("Too many requests — try again in about 2 minutes.");
});

it("opens a continuation in Publish, requires its manuscript, and keeps copied details editable", async () => {
  vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({
    ...COMPLETE, abstract_file: null,
    keywords: ["clearance"], owners: [{ user: SELF_ID, email: "ada@cit.edu" }],
    lineage: { derived_from: { id: 12, title: "Proposal", record_type_name: "Proposal" }, continued_as: null },
  }) } as never);
  const user = userEvent.setup();
  renderScreen(<PublishDialog />, { route: "/?publish=42" });
  await screen.findByRole("button", { name: "Upload manuscript" });
  expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  dropFile(pdf("full-thesis.pdf"));
  await screen.findByText(/uploaded/i, { selector: "p" });
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(screen.getByRole("textbox", { name: /^Title/ })).toHaveValue(COMPLETE.title);
  expect(screen.getByRole("textbox", { name: /^Abstract/ })).toHaveValue(COMPLETE.abstract);
  expect(screen.getByRole("textbox", { name: "Keywords" })).toHaveValue("clearance");
  expect(screen.getByRole("textbox", { name: "Owner emails" })).toHaveValue("ada@cit.edu");
  await user.clear(screen.getByRole("textbox", { name: "Keywords" }));
  await user.type(screen.getByRole("textbox", { name: "Keywords" }), "workflow, review");
  await user.type(screen.getByRole("textbox", { name: "Owner emails" }), ", coauthor@cit.edu");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(recordsApi.update).toHaveBeenCalledWith(42, expect.objectContaining({
    keywords: ["workflow", "review"], owner_emails: ["ada@cit.edu", "coauthor@cit.edu"],
  }));
  expect(recordsApi.create).not.toHaveBeenCalled();
  expect(recordsApi.uploadManuscript).toHaveBeenCalledWith(42, expect.any(File), expect.any(Object));
});

async function chooseType(user: ReturnType<typeof userEvent.setup>, name: RegExp) {
  await user.click(await screen.findByRole("radio", { name }));
}

function dropFile(file: File) {
  fireEvent.drop(screen.getByRole("button", { name: "Upload manuscript" }), {
    dataTransfer: { files: [file] },
  });
}

/** Step 1 done: a type chosen and a manuscript uploaded. */
async function completeManuscript(user: ReturnType<typeof userEvent.setup>) {
  await chooseType(user, /Thesis \/ Research/);
  dropFile(pdf());
  await screen.findByText(/uploaded/i, { selector: "p" });
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("textbox", { name: /^Title/ });
}

async function chooseAdviser(user: ReturnType<typeof userEvent.setup>, name: string) {
  const combobox = screen.getByRole("combobox", { name: /Adviser/ });
  await user.click(combobox);
  await user.type(combobox, name.split(" ")[0]);
  await user.click(await screen.findByRole("option", { name: new RegExp(name) }));
}

/** Step 2 filled with valid values and continued to the review. */
async function completeDetails(user: ReturnType<typeof userEvent.setup>) {
  const title = screen.getByRole("textbox", { name: /^Title/ });
  await user.clear(title);
  await user.type(title, COMPLETE.title);
  await user.type(screen.getByRole("textbox", { name: /^Abstract/ }), COMPLETE.abstract);
  await chooseAdviser(user, "Maria C. Santos");
  await user.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("heading", { name: "Manuscript" });
}

describe("opening", () => {
  it("is a labelled dialog, and step 1 of 3 follows the embargo question", async () => {
    await openNew();

    const dialog = await screen.findByRole("dialog", { name: "Publish your research" });
    expect(await within(dialog).findByRole("list", { name: "Publish steps" })).toBeInTheDocument();
    expect(await screen.findByRole("radio", { name: /Proposal/ })).toBeInTheDocument();
  });

  it("does not open for someone who cannot author a record", async () => {
    useAuthStore.setState({ user: makeUser({ role_name: ROLES.KTTO }) });
    openAtQuestion();

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("passes axe on the first step", async () => {
    const { container } = await openNew();
    await screen.findByRole("radio", { name: /Proposal/ });

    await expectNoBlockingA11yViolations(container);
  });
});

describe("record types (invariant 7)", () => {
  it("offers Thesis / Research and Project directly, with no Proposal behind them", async () => {
    const user = userEvent.setup();
    await openNew();

    await chooseType(user, /Project/);
    expect(screen.getByRole("radio", { name: /Project/ })).toBeChecked();
    await chooseType(user, /Thesis \/ Research/);
    expect(screen.getByRole("radio", { name: /Thesis \/ Research/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Thesis \/ Research/ })).toBeEnabled();
  });
});

describe("a file drop", () => {
  it("creates exactly one draft, titled from the file name and typed", async () => {
    const user = userEvent.setup();
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());

    await screen.findByText(/uploaded/i, { selector: "p" });
    expect(recordsApi.create).toHaveBeenCalledTimes(1);
    // The title made from the file name is saved as a placeholder (IR-833).
    expect(recordsApi.create).toHaveBeenCalledWith({
      title: "My Clearance Study", record_type: 2, metadata_sources: { title: { state: "placeholder" } },
    });
    expect(recordsApi.uploadManuscript).toHaveBeenCalledWith(42, expect.any(File), expect.any(Object));
  });

  it("is not possible before a type is chosen", async () => {
    await openNew();
    const zone = await screen.findByRole("button", { name: "Upload manuscript" });

    expect(zone).toHaveAttribute("aria-disabled", "true");
    dropFile(pdf());
    expect(recordsApi.create).not.toHaveBeenCalled();
  });

  it("refuses a file that is not a PDF before anything is sent", async () => {
    const user = userEvent.setup();
    await openNew();

    await chooseType(user, /Project/);
    dropFile(new File(["x"], "notes.docx", { type: "application/msword" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/not an accepted file/);
    expect(recordsApi.create).not.toHaveBeenCalled();
  });
});

describe("upload progress", () => {
  it("is announced and shown as a progress bar", async () => {
    const user = userEvent.setup();
    const upload = deferred<unknown>();
    // A holder, not a `let`: TypeScript does not see an assignment made inside
    // a callback, and would type a bare variable as never-assigned.
    const progress: { report?: (percent: number) => void } = {};
    vi.mocked(recordsApi.uploadManuscript).mockImplementation((_id, _file, options) => {
      progress.report = options?.onProgress;
      return upload.promise as never;
    });
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());

    expect(await screen.findByText("Uploading My_Clearance-Study.pdf", { selector: "[role=status]" })).toBeInTheDocument();
    await waitFor(() => expect(progress.report).toBeDefined());
    progress.report?.(40);
    await waitFor(() =>
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40"),
    );

    upload.resolve({ data: { id: 42 } });
    expect(await screen.findByText("My_Clearance-Study.pdf uploaded", { selector: "[role=status]" })).toBeInTheDocument();
  });
});

describe("a failed upload", () => {
  it("offers the matching draft when renamed bytes conflict and keeps the new draft for retry", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.uploadManuscript).mockRejectedValueOnce({
      response: { status: 409, data: { code: "exact_duplicate", detail: "Already attached.", matches: [
        { id: 17, title: "My earlier draft", url: "/records/17", action: "resume_draft" },
      ] } },
    });
    await openNew();
    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf("renamed.pdf"));
    const resume = await screen.findByRole("link", { name: "Resume draft: My earlier draft" });
    expect(resume).toHaveAttribute("href", "/?publish=17");
    resume.focus();
    expect(resume).toHaveFocus();
    expect(screen.getByRole("radio", { name: /Thesis \/ Research/ })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Retry upload" }));
    expect(recordsApi.create).toHaveBeenCalledTimes(1);
  });

  it("retries with the same file and type, without creating a second draft", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.uploadManuscript)
      .mockRejectedValueOnce({ response: { status: 500, data: { detail: "Storage is unavailable." } } })
      .mockResolvedValueOnce({ data: { id: 42 } } as never);
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());

    expect(await screen.findByRole("alert")).toHaveTextContent("Storage is unavailable.");
    await user.click(screen.getByRole("button", { name: "Retry upload" }));

    await screen.findByText(/uploaded/i, { selector: "p" });
    expect(recordsApi.create).toHaveBeenCalledTimes(1);
    expect(recordsApi.uploadManuscript).toHaveBeenCalledTimes(2);
    const [[, first], [, second]] = vi.mocked(recordsApi.uploadManuscript).mock.calls;
    expect(second).toBe(first);
    expect(screen.getByRole("radio", { name: /Thesis \/ Research/ })).toBeChecked();
  });

  it("shows the server's reason for refusing the file", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.uploadManuscript).mockRejectedValueOnce({
      response: { status: 400, data: { abstract_file: ["Only PDF files are accepted."] } },
    });
    await openNew();

    await chooseType(user, /Project/);
    dropFile(pdf());

    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files are accepted.");
  });
});

describe("Continue on step 1", () => {
  it("stays disabled until the upload succeeds", async () => {
    const user = userEvent.setup();
    const upload = deferred<unknown>();
    vi.mocked(recordsApi.uploadManuscript).mockReturnValue(upload.promise as never);
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    dropFile(pdf());
    await screen.findByRole("progressbar");
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();

    upload.resolve({ data: { id: 42 } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled());
  });

  it("saves a changed type onto the draft", async () => {
    const user = userEvent.setup();
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());
    await screen.findByText(/uploaded/i, { selector: "p" });
    await chooseType(user, /Project/);
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await screen.findByRole("textbox", { name: /^Title/ });
    expect(recordsApi.update).toHaveBeenCalledWith(42, { record_type: 3 });
    expect(recordsApi.create).toHaveBeenCalledTimes(1);
  });
});

describe("the adviser", () => {
  it("cannot be yourself, and the list says why", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    const combobox = screen.getByRole("combobox", { name: /Adviser/ });
    await user.click(combobox);
    await user.type(combobox, "Ada");
    const self = await screen.findByRole("option", { name: /Ada Reyes/ });

    expect(self).toHaveAttribute("aria-disabled", "true");
    expect(self).toHaveTextContent("You can't be your own adviser");
    await user.click(self);
    expect(combobox).toHaveValue("Ada");
  });

  it("skips yourself when moving through the list by keyboard", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    const combobox = screen.getByRole("combobox", { name: /Adviser/ });
    await user.click(combobox);
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(combobox).toHaveValue("Maria C. Santos");
  });

  it("is required for every type", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    await user.type(screen.getByRole("textbox", { name: /^Abstract/ }), COMPLETE.abstract);
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Choose your adviser.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("combobox", { name: /Adviser/ })).toHaveFocus());
    expect(recordsApi.update).not.toHaveBeenCalled();
  });
});

describe("IR-834 manuscript preview", () => {
  it("shows the accepted Manuscript beside Details and fetches it through the authenticated reader", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    expect(await screen.findByRole("region", { name: /Manuscript preview/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Details" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toBeInTheDocument();
    expect(screen.getByText("Shared authenticated PDF reader")).toBeInTheDocument();
  });

  it("keeps the preceding accepted Manuscript when a replacement is rejected", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    await user.click(screen.getByRole("button", { name: "Back" }));
    await user.click(screen.getByRole("button", { name: "Replace file" }));

    vi.mocked(recordsApi.uploadManuscript).mockRejectedValueOnce({
      response: { status: 400, data: { abstract_file: ["This replacement PDF was rejected."] } },
    });
    dropFile(pdf("rejected-replacement.pdf"));

    expect(await screen.findByRole("alert")).toHaveTextContent("This replacement PDF was rejected.");
    expect(screen.getByText("My_Clearance-Study.pdf", { exact: true })).toBeInTheDocument();

    const continueButton = screen.getByRole("button", { name: "Continue" });
    expect(continueButton).toBeEnabled();

    await user.click(continueButton);
    expect(await screen.findByRole("region", { name: /Manuscript preview/i })).toBeInTheDocument();
    expect(screen.getByText("Shared authenticated PDF reader")).toBeInTheDocument();
  });
});

describe("Details", () => {
  it("starts with the provisional title and the author's own name", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    expect(screen.getByRole("textbox", { name: /^Title/ })).toHaveValue("My Clearance Study");
    expect(screen.getByRole("list", { name: "Authors added" })).toHaveTextContent("Ada Reyes");
  });

  it("patches the draft on Continue", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await user.click(screen.getByText("More details"));
    await user.click(screen.getByRole("checkbox", { name: /human participants/ }));
    await completeDetails(user);

    expect(recordsApi.update).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        title: COMPLETE.title,
        abstract: COMPLETE.abstract,
        adviser: 21,
        authors: ["Ada Reyes"],
        year_accomplished: new Date().getFullYear(),
        requires_ethics_review: true,
        is_ip: false,
      }),
    );
    // Rule change, 2026-10-06 (lead): hints are hints. The author picks no
    // office (ADR-032), so Publish writes no requested_* flag.
    const [, payload] = vi.mocked(recordsApi.update).mock.calls[0];
    expect(Object.keys(payload).filter((key) => key.startsWith("requested_"))).toEqual([]);
  });

  it("links each error to its field and focuses the first", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await user.clear(screen.getByRole("textbox", { name: /^Title/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const title = screen.getByRole("textbox", { name: /^Title/ });
    await waitFor(() => expect(title).toHaveFocus());
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(title).toHaveAccessibleDescription("Title must be at least 5 characters.");
  });

  it("Tab from a closed More details reaches Back, not the fields hidden inside it", async () => {
    // IR-516: the same MetadataForm and Modal trap as Edit details.
    const layout = pretendLaidOut();
    try {
      const user = userEvent.setup();
      await openNew();
      await completeManuscript(user);

      screen.getByText("More details").closest("summary")!.focus();
      await user.tab();

      expect(screen.getByRole("button", { name: "Back" })).toHaveFocus();
    } finally {
      layout.mockRestore();
    }
  });

  it("passes axe with More details open", async () => {
    const user = userEvent.setup();
    const { container } = await openNew();
    await completeManuscript(user);
    await user.click(screen.getByText("More details"));

    await expectNoBlockingA11yViolations(container);
  });
});

describe("the review", () => {
  it("shows every value entered, and Edit returns to its step", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);

    const dialog = screen.getByRole("dialog");
    for (const text of [
      "Thesis / Research",
      "My_Clearance-Study.pdf",
      COMPLETE.title,
      COMPLETE.abstract,
      "Maria C. Santos",
      "Ada Reyes",
      String(new Date().getFullYear()),
    ]) {
      expect(within(dialog).getByText(text)).toBeInTheDocument();
    }

    await user.click(screen.getByRole("button", { name: "Edit details" }));
    expect(await screen.findByRole("textbox", { name: /^Title/ })).toHaveValue(COMPLETE.title);

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("radio", { name: /Thesis \/ Research/ })).toBeChecked();
  });

  it("opens More details from Edit hints", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);

    await user.click(screen.getByRole("button", { name: "Edit hints" }));

    expect(await screen.findByRole("checkbox", { name: /intellectual property/ })).toBeVisible();
  });

  it("asks for no supporting documents anywhere", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);

    expect(documentsApi.slots).not.toHaveBeenCalled();
    expect(screen.queryByText(/supporting document/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/required documents/i)).not.toBeInTheDocument();
  });

  it("passes axe", async () => {
    const user = userEvent.setup();
    const { container } = await openNew();
    await completeManuscript(user);
    await completeDetails(user);

    await expectNoBlockingA11yViolations(container);
  });
});

describe("submitting", () => {
  it("offers Check again when likely-match lookup fails on a resumed draft", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail(COMPLETE) } as never);
    vi.mocked(recordsApi.duplicateMatches).mockRejectedValueOnce(new Error("offline"));
    const user = userEvent.setup();
    renderScreen(<PublishDialog />, { route: "/?publish=42" });
    const retry = await screen.findByRole("button", { name: "Check again" });
    await user.click(retry);
    await waitFor(() => expect(recordsApi.duplicateMatches).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Check again" })).not.toBeInTheDocument());
  });

  it("shows a likely match and lets a keyboard user acknowledge it without losing Review", async () => {
    const match = { id: 17, title: "Related Cebu research", url: "/records/17", action: "open_record", reason: "same_title" };
    vi.mocked(recordsApi.duplicateMatches).mockResolvedValue({ data: { exact: [], likely: [match], acknowledged: false } } as never);
    vi.mocked(recordsApi.acknowledgeDuplicates).mockResolvedValue({ data: { acknowledged: true, matches: [match] } } as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);
    expect(await screen.findByRole("heading", { name: "Likely manuscript matches" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Related Cebu research" })).toHaveAttribute("href", "/records/17");
    const acknowledge = screen.getByRole("button", { name: "Acknowledge matches" });
    acknowledge.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(recordsApi.acknowledgeDuplicates).toHaveBeenCalledWith(42, [17]));
    expect(screen.getByRole("button", { name: "Matches acknowledged" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Submit for review" })).toBeInTheDocument();
  });

  it("needs consent, and sends the DPA flag", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);

    const submit = screen.getByRole("button", { name: "Submit for review" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(submit);

    await waitFor(() => expect(recordsApi.submit).toHaveBeenCalledWith(42, true));
  });

  it("keeps step 3 on a 400 and shows the field errors", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.submit).mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: "This record can't be submitted yet.", title: ["A record with this title already exists."] },
      },
    });
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);

    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This record can't be submitted yet.");
    expect(alert).toHaveTextContent("Title: A record with this title already exists.");
    expect(screen.getByRole("heading", { name: "Manuscript" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit for review" })).toBeInTheDocument();
  });
});

describe("a network failure", () => {
  it("on submit offers Try again, and trying again submits", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.submit)
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({ data: { detail: "Submitted." } } as never);
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({ pipeline_status: "in_review", current_holders: [] }),
    } as never);
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach IRIS/);
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Submitted for review" })).toBeInTheDocument();
    expect(recordsApi.submit).toHaveBeenCalledTimes(2);
  });
});

describe("success", () => {
  it("passes axe", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({
        pipeline_status: "in_review",
        current_holders: [{ party: "intake", label: "Intake", opened_at: null, opened_by: null }],
      }),
    } as never);
    const { container } = await openNew();
    await completeManuscript(user);
    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await screen.findByRole("heading", { name: "Submitted for review" });

    await expectNoBlockingA11yViolations(container);
  });

  // Rule change, 2026-10-06 (lead): Intake is retired (ADR-032 invariant 1)
  // and is never named, though the server reports it until IR-260.
  it("never names Intake, though the server reports it", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({
        pipeline_status: "in_review",
        current_holders: [{ party: "intake", label: "Intake", opened_at: null, opened_by: null }],
      }),
    } as never);
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByRole("heading", { name: "Submitted for review" })).toBeInTheDocument();
    expect(screen.queryByText(/Intake/)).not.toBeInTheDocument();
    expect(screen.queryByText(/your adviser reads it/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open paper" })).toHaveAttribute("href", "/records/42");
    expect(screen.getByRole("button", { name: "Publish another" })).toBeInTheDocument();
    // Announced politely, so a screen reader hears the outcome without moving focus.
    const announced = screen.getAllByRole("status").map((region) => region.textContent).join(" ");
    expect(announced).toMatch(/Submitted for review\./);
    expect(announced).not.toMatch(/Intake/);
  });

  it("names the adviser when the server says the adviser holds it", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({
        pipeline_status: "in_review",
        adviser: 21,
        current_holders: [{ party: "adviser", label: "Adviser", opened_at: null, opened_by: null }],
      }),
    } as never);
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByRole("heading", { name: "Sent to Maria C. Santos for review" })).toBeInTheDocument();
  });

  it("starts over on Publish another", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({ pipeline_status: "in_review", current_holders: [] }),
    } as never);
    await openNew();
    await completeManuscript(user);
    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await user.click(await screen.findByRole("button", { name: "Publish another" }));

    // From nothing, so the new paper is asked its own embargo question.
    expect(await screen.findByRole("radio", { name: /^No/ })).not.toBeChecked();
    await user.click(screen.getByRole("radio", { name: /^No/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByRole("radio", { name: /Proposal/ })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });
});

describe("resuming a draft from /?publish=<id>", () => {
  it("opens at Details when the manuscript is there but the details are not", async () => {
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    expect(await screen.findByRole("textbox", { name: /^Title/ })).toHaveValue("My Clearance Study");
    expect(recordsApi.detail).toHaveBeenCalledWith(42);
    expect(recordsApi.create).not.toHaveBeenCalled();
  });

  it("opens at the review when everything is filled in", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail(COMPLETE) } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    expect(await screen.findByRole("heading", { name: "Manuscript" })).toBeInTheDocument();
    expect(screen.getByText("Maria C. Santos")).toBeInTheDocument();
  });

  it("opens at the manuscript when no file was uploaded", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ abstract_file: null }) } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    expect(await screen.findByRole("radio", { name: /Thesis \/ Research/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
  });

  it("does not erase a saved field of research when that list failed to load", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.classifications).mockRejectedValue(new Error("Network Error"));
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({ ...COMPLETE, abstract: "", classification: "Computing" }),
    } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    await user.type(await screen.findByRole("textbox", { name: /^Abstract/ }), COMPLETE.abstract);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("heading", { name: "Manuscript" });

    const calls = vi.mocked(recordsApi.update).mock.calls;
    const payload = calls[calls.length - 1][1];
    expect(payload).not.toHaveProperty("classification");
    expect(payload).toHaveProperty("psced", null);
  });

  it("says so when the record has already been submitted", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({ pipeline_status: "in_review" }),
    } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    expect(await screen.findByText(/already been submitted/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open paper" })).toHaveAttribute("href", "/records/42");
  });

  it("says so when the draft cannot be found", async () => {
    vi.mocked(recordsApi.detail).mockRejectedValue({ response: { status: 404, data: { detail: "Not found." } } });
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    expect(await screen.findByText(/couldn't find that draft/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start a new submission" })).toBeInTheDocument();
  });
});

describe("closing", () => {
  it("asks first while an upload is in flight", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.uploadManuscript).mockReturnValue(new Promise(() => {}) as never);
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());
    await screen.findByRole("progressbar");
    await user.click(screen.getByRole("button", { name: "Close" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("alertdialog", { name: "Stop the upload and close?" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Keep uploading" })).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "Keep uploading" }));
    expect(screen.queryByText(/Stop the upload and close/)).not.toBeInTheDocument();
  });

  it("closes at once when nothing is uploading", async () => {
    const user = userEvent.setup();
    await openNew();
    await screen.findByRole("radio", { name: /Proposal/ });

    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("autofill from the manuscript (IR-833; supersedes IR-409's chips)", () => {
  // IR-409 only offered title and abstract as chips and stopped asking after
  // 90 s. IR-833 fills a reliable title and abstract in, with Undo, offers
  // labelled authors, keywords and publication year, and keeps asking with a
  // backoff that ends in Check again. Every author decision survives.
  const FOUND_TITLE = "Clearance-Aware Resubmission in a University Research Office";
  const FOUND_ABSTRACT = "This study examines how a research office can preserve clearances across revisions.";
  const NEUTRAL = "We couldn't read details from this file — fill them in below.";

  const titleField = () => screen.getByRole("textbox", { name: /^Title/ });
  const abstractField = () => screen.getByRole("textbox", { name: /^Abstract/ });
  const chip = (field: string) => screen.queryByRole("group", { name: `Suggested ${field}` });
  const filled = (field: string) => screen.queryByRole("group", { name: `Filled in ${field}` });

  function entry<T>(value: T, more: Record<string, unknown> = {}) {
    return { value, basis: "labelled_front_matter", page: null, region: null, auto_apply: false, exceeds_limit: false, ...more };
  }

  /** A reply in IR-833's contract. */
  function reading(
    found: Record<string, unknown> = {},
    { state = "ready", revision = "rev-a", phase, retryable = false }: { state?: string; revision?: string; phase?: string; retryable?: boolean } = {},
  ) {
    const fields = { title: null, abstract: null, authors: null, keywords: null, publication_year: null, ...found } as Record<string, { value: unknown } | null>;
    return {
      data: {
        state,
        suggestions: { title: (fields.title?.value as string) ?? null, abstract: (fields.abstract?.value as string) ?? null },
        fields: state === "ready" ? fields : { title: null, abstract: null, authors: null, keywords: null, publication_year: null },
        source: "pdf_structure",
        manuscript_revision: revision,
        phase: phase ?? (state === "ready" ? "ready" : state === "pending" ? "reading" : state),
        retryable,
        message: null,
      },
    };
  }

  const TITLE = entry(FOUND_TITLE, { basis: "document_title", auto_apply: true, page: 1 });
  const ABSTRACT = entry(FOUND_ABSTRACT, { basis: "abstract_section", auto_apply: true, page: 2 });

  it("fills an empty abstract and the title made from the file name, and says where each came from", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ title: TITLE, abstract: ABSTRACT }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));
    expect(abstractField()).toHaveValue(FOUND_ABSTRACT);
    expect(within(filled("title")!).getByText("Found on page 1")).toBeInTheDocument();
    expect(within(filled("abstract")!).getByText("Found on page 2")).toBeInTheDocument();
    expect(chip("title")).not.toBeInTheDocument();
    expect(await screen.findByText(
      "Filled in the title and abstract from your PDF. You can undo this under each field.",
      { selector: "[role=status]" },
    )).toBeInTheDocument();
  });

  it("puts the previous values back on Undo and does not fill them in again", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ title: TITLE, abstract: ABSTRACT }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));

    await user.click(within(filled("title")!).getByRole("button", { name: "Undo" }));
    await user.click(within(filled("abstract")!).getByRole("button", { name: "Undo" }));

    expect(titleField()).toHaveValue("My Clearance Study");
    expect(abstractField()).toHaveValue("");
    expect(abstractField()).toHaveFocus();
    // Leaving and coming back reads the PDF again; a dismissed value stays out.
    await user.click(screen.getByRole("button", { name: "Back" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(recordsApi.metadataSuggestions).toHaveBeenCalledTimes(2));
    expect(titleField()).toHaveValue("My Clearance Study");
    expect(abstractField()).toHaveValue("");
    expect(chip("title")).not.toBeInTheDocument();
  });

  it("keeps what the author typed while the PDF was read, and offers Replace with suggestion", async () => {
    vi.mocked(recordsApi.metadataSuggestions)
      .mockResolvedValueOnce(reading({}, { state: "pending" }) as never)
      .mockResolvedValue(reading({ abstract: ABSTRACT }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await screen.findAllByText("Reading your PDF…");

    await user.type(abstractField(), "My own words about this study.");
    const offer = await screen.findByRole("group", { name: "Suggested abstract" }, { timeout: 4000 });

    expect(abstractField()).toHaveValue("My own words about this study.");
    await user.click(within(offer).getByRole("button", { name: "Replace with suggestion" }));
    expect(abstractField()).toHaveValue(FOUND_ABSTRACT);
  });

  it("keeps a field the author cleared while the PDF was read", async () => {
    vi.mocked(recordsApi.metadataSuggestions)
      .mockResolvedValueOnce(reading({}, { state: "pending" }) as never)
      .mockResolvedValue(reading({ title: TITLE }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await screen.findAllByText("Reading your PDF…");

    await user.clear(titleField());
    await screen.findByRole("group", { name: "Suggested title" }, { timeout: 4000 });

    expect(titleField()).toHaveValue("");
  });

  it("does not offer a value back once it was filled in and then edited", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ abstract: ABSTRACT }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await waitFor(() => expect(abstractField()).toHaveValue(FOUND_ABSTRACT));

    await user.type(abstractField(), " Plus a sentence of mine.");

    expect(chip("abstract")).not.toBeInTheDocument();
    expect(filled("abstract")).not.toBeInTheDocument();
    expect(abstractField()).toHaveValue(`${FOUND_ABSTRACT} Plus a sentence of mine.`);
  });

  it("offers labelled authors, keywords and publication year, and fills each only when accepted", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
      authors: entry(["Juan dela Cruz", "Maria Santos"]),
      keywords: entry(["irrigation", "solar pumps"], { page: 1 }),
      publication_year: entry(2024),
    }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    const authors = await screen.findByRole("group", { name: "Suggested authors" });
    expect(screen.getByRole("list", { name: "Authors added" })).toHaveTextContent("Ada Reyes");
    expect(screen.getByRole("textbox", { name: "Keywords" })).toHaveValue("");
    expect(screen.getByRole("spinbutton", { name: "Publication year" })).toHaveValue(null);
    expect(within(chip("keywords")!).getByText("Found on page 1")).toBeInTheDocument();

    // The signed-in author is the default; replacing them is spelled out.
    await user.click(within(authors).getByRole("button", { name: "Replace with suggestion" }));
    await user.click(within(chip("keywords")!).getByRole("button", { name: "Use" }));
    await user.click(within(chip("publication year")!).getByRole("button", { name: "Use" }));

    const added = screen.getByRole("list", { name: "Authors added" });
    expect(within(added).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Juan dela Cruz", "Maria Santos"]);
    expect(screen.getByRole("textbox", { name: "Keywords" })).toHaveValue("irrigation, solar pumps");
    expect(screen.getByRole("spinbutton", { name: "Publication year" })).toHaveValue(2024);
    // A publication year is not a completion year.
    expect(screen.getByRole("spinbutton", { name: /Year \(completed\)/ })).toHaveValue(new Date().getFullYear());
  });

  it("removes an offer on Dismiss and leaves the field alone", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ keywords: entry(["irrigation"]) }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    await user.click(within(await screen.findByRole("group", { name: "Suggested keywords" })).getByRole("button", { name: "Dismiss" }));

    expect(chip("keywords")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Keywords" })).toHaveValue("");
  });

  it("offers an overlong abstract for review rather than filling it in or cutting it", async () => {
    const long = "word ".repeat(1100).trim();
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
      abstract: entry(long, { basis: "abstract_section", auto_apply: false, exceeds_limit: true }),
    }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    const offer = await screen.findByRole("group", { name: "Suggested abstract" });
    expect(within(offer).getByText("This is longer than the field allows. Shorten it after using it.")).toBeInTheDocument();
    expect(abstractField()).toHaveValue("");
  });

  it("treats a resumed draft's saved title as the author's when no decision was saved", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ title: "A Title I Wrote" }) } as never);
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ title: TITLE }) as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    const offer = await screen.findByRole("group", { name: "Suggested title" });
    expect(within(offer).getByRole("button", { name: "Replace with suggestion" })).toBeInTheDocument();
    expect(titleField()).toHaveValue("A Title I Wrote");
  });

  it("restores saved decisions on reopening: a filled title keeps its Undo, a typed abstract stays the author's", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({
      title: FOUND_TITLE,
      abstract: "Words the author wrote last week, long enough to count.",
      metadata_sources: {
        title: { state: "automatic", source_revision: "rev-a", previous: "My Clearance Study" },
        abstract: { state: "authored" },
      },
    }) } as never);
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ title: TITLE, abstract: ABSTRACT }) as never);
    const user = userEvent.setup();
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    const note = await screen.findByRole("group", { name: "Filled in title" });
    expect(abstractField()).toHaveValue("Words the author wrote last week, long enough to count.");
    expect(within(screen.getByRole("group", { name: "Suggested abstract" })).getByRole("button", { name: "Replace with suggestion" })).toBeInTheDocument();

    await user.click(within(note).getByRole("button", { name: "Undo" }));
    expect(titleField()).toHaveValue("My Clearance Study");
  });

  it("lets a reopened placeholder title be filled in", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ metadata_sources: { title: { state: "placeholder" } } }) } as never);
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ title: TITLE }) as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    await screen.findByRole("group", { name: "Filled in title" });
    expect(titleField()).toHaveValue(FOUND_TITLE);
  });

  it("shows Reading your PDF… while pending, without disabling the fields", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({}, { state: "pending" }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    expect(await screen.findAllByText("Reading your PDF…")).not.toHaveLength(0);
    expect(titleField()).toBeEnabled();
    expect(abstractField()).toBeEnabled();
    await user.type(abstractField(), "Typed while it reads.");
    expect(abstractField()).toHaveValue("Typed while it reads.");
  });

  it("says when the read is being retried", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({}, { state: "pending", phase: "retrying" }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    expect(await screen.findAllByText("Reading your PDF didn't work the first time. Trying again…")).not.toHaveLength(0);
  });

  it("stops asking once the author leaves Details", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({}, { state: "pending" }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await screen.findAllByText("Reading your PDF…");
    const asked = vi.mocked(recordsApi.metadataSuggestions).mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Back" }));
    // Longer than the first 2 s interval: a poll still running would have fired.
    await new Promise((resolve) => setTimeout(resolve, 2500));

    expect(recordsApi.metadataSuggestions).toHaveBeenCalledTimes(asked);
  });

  it("says Still processing when its time is up, and Check again asks afresh", async () => {
    const start = Date.now();
    const clock = vi.spyOn(Date, "now");
    vi.mocked(recordsApi.metadataSuggestions)
      .mockImplementationOnce(async () => {
        // Two minutes pass while the first answer is on its way.
        clock.mockReturnValue(start + 121_000);
        return reading({}, { state: "pending" }) as never;
      })
      .mockResolvedValue(reading({ title: TITLE }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    expect(await screen.findByText(/Still processing your PDF/, { selector: "p" })).toBeInTheDocument();
    clock.mockRestore();
    await user.click(screen.getByRole("button", { name: "Check again" }));

    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));
    expect(screen.queryByText(/Still processing your PDF/, { selector: "p" })).not.toBeInTheDocument();
  });

  it.each(["failed", "unsupported"])("shows the neutral line, not an error, on %s", async (state) => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({}, { state }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    expect(await screen.findByText(NEUTRAL)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Reading your PDF…")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry extraction" })).not.toBeInTheDocument();
  });

  it("offers Retry extraction after a final failure, and reads again", async () => {
    vi.mocked(recordsApi.metadataSuggestions)
      .mockResolvedValueOnce(reading({}, { state: "failed", retryable: true }) as never)
      .mockResolvedValue(reading({ title: TITLE }) as never);
    vi.mocked(recordsApi.retryExtraction).mockResolvedValue(reading({}, { state: "pending" }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    await user.click(await screen.findByRole("button", { name: "Retry extraction" }));

    expect(recordsApi.retryExtraction).toHaveBeenCalledWith(42, "rev-a");
    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));
  });

  it("says when the PDF was read but held nothing to fill in", async () => {
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);

    expect(await screen.findByText("We read your PDF but found no details to fill in.")).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL)).not.toBeInTheDocument();
  });

  it("asks again when Details is re-entered after failed", async () => {
    vi.mocked(recordsApi.metadataSuggestions)
      .mockResolvedValueOnce(reading({}, { state: "failed" }) as never)
      .mockResolvedValue(reading({ keywords: entry(["irrigation"]) }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await screen.findByText(NEUTRAL);

    await user.click(screen.getByRole("button", { name: "Back" }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("group", { name: "Suggested keywords" })).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL)).not.toBeInTheDocument();
  });

  async function replaceManuscript(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: "Back" }));
    await user.click(screen.getByRole("button", { name: "Replace file" }));
    dropFile(pdf("Second_Draft.pdf"));
    await waitFor(() => expect(recordsApi.uploadManuscript).toHaveBeenCalledTimes(2));
  }

  it("replaces an untouched filled-in value with the new file's, and keeps what the author typed", async () => {
    vi.mocked(recordsApi.metadataSuggestions)
      .mockResolvedValueOnce(reading({ title: entry("The Old File's Title", { auto_apply: true }) }) as never)
      .mockResolvedValue(reading({ title: TITLE, abstract: ABSTRACT }, { revision: "rev-b" }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await waitFor(() => expect(titleField()).toHaveValue("The Old File's Title"));
    await user.type(abstractField(), "Typed against the old file, long enough to count.");

    await replaceManuscript(user);
    await screen.findByText(/uploaded/i, { selector: "p" });
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));
    expect(abstractField()).toHaveValue("Typed against the old file, long enough to count.");
    expect(screen.queryByText("The Old File's Title")).not.toBeInTheDocument();
  });

  it("marks a filled-in value the new file does not have, rather than dropping it", async () => {
    vi.mocked(recordsApi.metadataSuggestions)
      .mockResolvedValueOnce(reading({ title: TITLE }) as never)
      .mockResolvedValue(reading({}, { revision: "rev-b" }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));

    await replaceManuscript(user);
    await screen.findByText(/uploaded/i, { selector: "p" });
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("From your previous file. Check it still applies.")).toBeInTheDocument();
    expect(titleField()).toHaveValue(FOUND_TITLE);
  });

  it("ignores a reply about the old file that arrives after the replacement began", async () => {
    const late = deferred<unknown>();
    vi.mocked(recordsApi.metadataSuggestions)
      .mockImplementationOnce(() => late.promise as never)
      .mockResolvedValue(reading({}, { state: "pending", revision: "rev-b" }) as never);
    const upload = deferred<unknown>();
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    vi.mocked(recordsApi.uploadManuscript).mockImplementationOnce(() => upload.promise as never);

    await user.click(screen.getByRole("button", { name: "Back" }));
    await user.click(screen.getByRole("button", { name: "Replace file" }));
    dropFile(pdf("Second_Draft.pdf"));
    late.resolve(reading({ title: TITLE }));
    upload.resolve({ data: { id: 42 } });
    await screen.findByText(/uploaded/i, { selector: "p" });
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findAllByText("Reading your PDF…");

    expect(titleField()).toHaveValue("My Clearance Study");
    expect(filled("title")).not.toBeInTheDocument();
  });

  it("keeps the accepted file's values when a replacement is refused", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ title: TITLE }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));
    vi.mocked(recordsApi.uploadManuscript).mockRejectedValueOnce({
      response: { status: 400, data: { abstract_file: ["This PDF is encrypted."] } },
    });

    await replaceManuscript(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("This PDF is encrypted.");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("group", { name: "Filled in title" })).toBeInTheDocument();
    expect(titleField()).toHaveValue(FOUND_TITLE);
  });

  it("is never needed to submit: a failed suggestions request still lets the author finish", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockRejectedValue(new Error("Network Error"));
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await screen.findByText(NEUTRAL);

    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    await waitFor(() => expect(recordsApi.submit).toHaveBeenCalledWith(42, true));
  });

  it("shows no confidence value, and passes axe with notes and offers on screen", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
      title: TITLE, abstract: ABSTRACT, keywords: entry(["irrigation"]),
    }) as never);
    const user = userEvent.setup();
    const { container } = await openNew();
    await completeManuscript(user);
    await screen.findByRole("group", { name: "Suggested keywords" });

    expect(screen.getByRole("dialog")).not.toHaveTextContent(/confiden|certain|\d+\s?%/i);
    await expectNoBlockingA11yViolations(container);
  });

  it("saves decisions with the values on Continue, without touching owners, adviser or routing", async () => {
    vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({ title: TITLE, abstract: ABSTRACT }) as never);
    const user = userEvent.setup();
    await openNew();
    await completeManuscript(user);
    await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));
    await chooseAdviser(user, "Maria C. Santos");

    await user.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("heading", { name: "Manuscript" });

    const calls = vi.mocked(recordsApi.update).mock.calls;
    const body = calls[calls.length - 1][1];
    expect(body).toMatchObject({
      title: FOUND_TITLE,
      abstract: FOUND_ABSTRACT,
      adviser: 21,
      metadata_sources: {
        title: { state: "automatic", source_revision: "rev-a", previous: "My Clearance Study" },
        abstract: { state: "automatic", source_revision: "rev-a", previous: "" },
      },
    });
    expect(body).not.toHaveProperty("requested_itso");
  });

  describe("read by LlamaExtract (IR-846)", () => {
    const REGION = { page: 1, left: 72, top: 74, right: 194, bottom: 87 };
    const cited = <T,>(value: T, more: Record<string, unknown> = {}) => entry(value, {
      source: "llamaextract", basis: "cited_text", page: 1, region: REGION,
      matching_text: String(value), confidence: 0.97, low_confidence: false, ...more,
    });

    it("says which page each value is on, and quotes the PDF where its words differ", async () => {
      vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
        title: cited(FOUND_TITLE, { auto_apply: true }),
        authors: cited(["Ana Cruz", "Ben Reyes"], { matching_text: "Ana Cruz and Ben Reyes", page: 2 }),
      }) as never);
      const user = userEvent.setup();
      await openNew();
      await completeManuscript(user);

      await waitFor(() => expect(titleField()).toHaveValue(FOUND_TITLE));
      expect(within(filled("title")!).getByText("Found on page 1")).toBeInTheDocument();
      // The title is the PDF's words exactly, so they are not repeated.
      expect(within(filled("title")!).queryByRole("blockquote")).not.toBeInTheDocument();
      expect(within(chip("authors")!).getByText("Found on page 2")).toBeInTheDocument();
      expect(within(chip("authors")!).getByRole("blockquote")).toHaveTextContent("Ana Cruz and Ben Reyes");
    });

    it("asks the author to check a low-confidence value, in words and never as a number", async () => {
      vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
        abstract: cited(FOUND_ABSTRACT, { confidence: 0.62, low_confidence: true }),
        keywords: cited(["irrigation"], { confidence: 0.99 }),
      }) as never);
      const user = userEvent.setup();
      const view = await openNew();
      await completeManuscript(user);

      await waitFor(() => expect(chip("abstract")).toBeInTheDocument());
      expect(within(chip("abstract")!).getByText("Check this against your PDF.")).toBeInTheDocument();
      expect(within(chip("keywords")!).queryByText(/Check this/)).not.toBeInTheDocument();
      expect(screen.queryByText(/0\.62|0\.99|62%|99%/)).not.toBeInTheDocument();
      expect(abstractField()).toHaveValue("");
      await expectNoBlockingA11yViolations(view.container);
    });

    it("turns the preview to the page and highlights the lines on Show in PDF", async () => {
      vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
        authors: cited(["Ana Cruz"], { page: 2, region: { ...REGION, page: 2 } }),
      }) as never);
      const user = userEvent.setup();
      await openNew();
      await completeManuscript(user);

      await waitFor(() => expect(chip("authors")).toBeInTheDocument());
      await user.click(within(chip("authors")!).getByRole("button", { name: "Show the authors in your PDF, page 2" }));

      expect(await screen.findByText("Reader at page 2, 1 highlighted")).toBeInTheDocument();
    });

    it("keeps focus in the form on Show in PDF when both panes are on screen", async () => {
      vi.stubGlobal("matchMedia", (query: string) => ({
        matches: query === "(min-width: 1024px)", addEventListener: vi.fn(), removeEventListener: vi.fn(),
      }));
      vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
        authors: cited(["Ana Cruz"], { page: 2, region: { ...REGION, page: 2 } }),
      }) as never);
      const user = userEvent.setup();
      await openNew();
      await completeManuscript(user);

      await waitFor(() => expect(chip("authors")).toBeInTheDocument());
      const show = within(chip("authors")!).getByRole("button", { name: "Show the authors in your PDF, page 2" });
      await user.click(show);

      expect(await screen.findByText("Reader at page 2, 1 highlighted")).toBeInTheDocument();
      await new Promise((resolve) => requestAnimationFrame(resolve));
      expect(show).toHaveFocus();
    });

    it("offers no Show in PDF for a value with no page", async () => {
      vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(reading({
        keywords: cited(["irrigation"], { page: null, region: null, matching_text: null }),
      }) as never);
      const user = userEvent.setup();
      await openNew();
      await completeManuscript(user);

      await waitFor(() => expect(chip("keywords")).toBeInTheDocument());
      expect(within(chip("keywords")!).getByText("Found in your PDF")).toBeInTheDocument();
      expect(within(chip("keywords")!).queryByRole("button", { name: /Show the/ })).not.toBeInTheDocument();
    });
  });
});

describe("saving Details as the author works (IR-833)", () => {
  const titleField = () => screen.getByRole("textbox", { name: /^Title/ });

  async function resumeAtDetails(overrides: Record<string, unknown> = {}) {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({
      details_revision: 3, owners: [{ user: SELF_ID, email: "ktto@cit.edu" }], ...overrides,
    }) } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });
    await screen.findByRole("textbox", { name: /^Title/ });
  }

  it("saves a change a moment after typing stops, naming the revision it was made from", async () => {
    vi.mocked(recordsApi.update).mockResolvedValue({ data: { id: 42, details_revision: 4 } } as never);
    const user = userEvent.setup();
    await resumeAtDetails();

    await user.clear(titleField());
    await user.type(titleField(), "A Title Typed Today");

    await waitFor(() => expect(recordsApi.update).toHaveBeenCalled(), { timeout: 4000 });
    expect(vi.mocked(recordsApi.update).mock.calls[0][1]).toMatchObject({
      title: "A Title Typed Today",
      expected_details_revision: 3,
      metadata_sources: { title: { state: "authored" } },
    });
    expect(await screen.findByText("All changes saved.")).toBeInTheDocument();
  });

  it("does not save a field that would be refused, and says it is unsaved", async () => {
    vi.mocked(recordsApi.update).mockResolvedValue({ data: { id: 42, details_revision: 4 } } as never);
    const user = userEvent.setup();
    await resumeAtDetails();

    await user.clear(titleField());
    await user.type(titleField(), "Abc");

    await waitFor(() => expect(recordsApi.update).toHaveBeenCalled(), { timeout: 4000 });
    expect(vi.mocked(recordsApi.update).mock.calls[0][1]).not.toHaveProperty("title");
  });

  it("stops saving when a newer edit was saved elsewhere, and offers to reload", async () => {
    vi.mocked(recordsApi.update).mockRejectedValue({
      response: { status: 409, data: { code: "stale_edit", details_revision: 5, detail: "Changed elsewhere." } },
    });
    const user = userEvent.setup();
    await resumeAtDetails();

    await user.clear(titleField());
    await user.type(titleField(), "An Older Tab's Title");

    const alert = await screen.findByRole("alert", {}, { timeout: 4000 });
    expect(alert).toHaveTextContent("This draft was changed somewhere else");
    const tries = vi.mocked(recordsApi.update).mock.calls.length;
    await user.type(titleField(), " Again");
    await new Promise((resolve) => setTimeout(resolve, 2000));
    expect(recordsApi.update).toHaveBeenCalledTimes(tries);

    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ title: "The Newer Title", details_revision: 5 }) } as never);
    await user.click(within(alert).getByRole("button", { name: "Reload draft" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: /^Title/ })).toHaveValue("The Newer Title"));
  });

  it("reports a stale Continue instead of overwriting the newer draft", async () => {
    vi.mocked(recordsApi.update).mockRejectedValue({
      response: { status: 409, data: { code: "stale_edit", details_revision: 5, detail: "Changed elsewhere." } },
    });
    const user = userEvent.setup();
    await resumeAtDetails({ ...COMPLETE, adviser: null });
    await chooseAdviser(user, "Maria C. Santos");

    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This draft was changed somewhere else");
    expect(screen.queryByRole("heading", { name: "Manuscript" })).not.toBeInTheDocument();
    expect(vi.mocked(recordsApi.update).mock.calls[0][1]).toMatchObject({ expected_details_revision: 3 });
  });

  it("says when a save failed, and Try again saves", async () => {
    vi.mocked(recordsApi.update)
      .mockRejectedValueOnce({ response: { status: 503, data: {} } })
      .mockResolvedValue({ data: { id: 42, details_revision: 4 } } as never);
    const user = userEvent.setup();
    await resumeAtDetails();

    await user.clear(titleField());
    await user.type(titleField(), "A Title Typed Today");

    expect(await screen.findByText("Your latest changes couldn't be saved.", {}, { timeout: 4000 })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(recordsApi.update).toHaveBeenCalledTimes(2));
  });
});

describe("the embargo question (ADR-052 decision 2)", () => {
  afterEach(() => vi.useRealTimers());

  const inDays = (days: number) => {
    // The form validates Manila's calendar date, regardless of the runner's timezone.
    const day = new Date(Date.now() + 8 * 60 * 60 * 1000);
    day.setUTCDate(day.getUTCDate() + days);
    return day.toISOString().slice(0, 10);
  };
  const question = () => screen.findByRole("radiogroup", { name: /Is this paper under an embargo/ });
  const continueButton = () => screen.getByRole("button", { name: "Continue" });
  const dateField = () => screen.getByLabelText(/Date to review the embargo/);

  /** Answer Yes with this date and continue to the manuscript step. */
  async function answerYes(user: ReturnType<typeof userEvent.setup>, until: string) {
    await question();
    await user.click(screen.getByRole("radio", { name: /^Yes/ }));
    fireEvent.change(dateField(), { target: { value: until } });
    await user.click(continueButton());
    await screen.findByRole("radio", { name: /Proposal/ });
  }

  it("is asked first and alone: no type, no file and no steps until it is answered", async () => {
    const { container } = openAtQuestion();

    await question();
    expect(screen.queryByRole("radio", { name: /Proposal/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload manuscript" })).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Publish steps" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("starts unanswered, says what an embargo does, and has no default", async () => {
    openAtQuestion();

    const group = await question();
    expect(screen.getByRole("radio", { name: /^No/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /^Yes/ })).not.toBeChecked();
    expect(group).toHaveTextContent(/outside AI companies/);
    expect(group).toHaveTextContent(/doesn't hide the paper/);
    expect(group).toHaveTextContent(/can't be recalled/);
    // The author protects possible IP by answering Yes, so Yes has to say it covers that.
    expect(screen.getByRole("radio", { name: /may want to patent or protect/ })).not.toBeChecked();
  });

  it("refuses to continue with no answer, in words, and moves focus to it", async () => {
    const user = userEvent.setup();
    const { container } = openAtQuestion();
    await question();

    await user.click(continueButton());

    expect(await screen.findByText("Say whether this paper is under embargo.")).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Proposal/ })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("radio", { name: /^No/ })).toHaveFocus());
    await expectNoBlockingA11yViolations(container);
  });

  it("says under Yes who ends an embargo, because its date doesn't", async () => {
    const user = userEvent.setup();
    openAtQuestion();
    await question();

    await user.click(screen.getByRole("radio", { name: /^Yes/ }));

    expect(dateField()).toHaveAccessibleDescription(/doesn't end the embargo/);
    expect(dateField()).toHaveAccessibleDescription(/only your Adviser or RDCO can/);
  });

  it.each([
    { now: "2026-11-02T15:59:00Z", yesterday: "2026-11-01", today: "2026-11-02" },
    { now: "2026-11-02T16:01:00Z", yesterday: "2026-11-02", today: "2026-11-03" },
  ])("asks for a date only under Yes, and requires one that has not passed at $now", async ({ now, yesterday, today }) => {
    vi.setSystemTime(new Date(now));
    expect(inDays(-1)).toBe(yesterday);
    expect(inDays(0)).toBe(today);
    const user = userEvent.setup();
    const { container } = openAtQuestion();
    await question();
    expect(screen.queryByLabelText(/Date to review the embargo/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /^Yes/ }));
    await user.click(continueButton());
    expect(await screen.findByText("Choose the date to review this embargo.")).toBeInTheDocument();
    expect(dateField()).toHaveAttribute("aria-invalid", "true");

    fireEvent.change(dateField(), { target: { value: inDays(-1) } });
    await user.click(continueButton());
    expect(await screen.findByText("The date to review this embargo cannot be in the past.")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);

    fireEvent.change(dateField(), { target: { value: inDays(0) } });
    await user.click(continueButton());
    expect(await screen.findByRole("radio", { name: /Proposal/ })).toBeInTheDocument();
  });

  it("saves the answer before the file is sent, on the draft it creates", async () => {
    const user = userEvent.setup();
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());
    await screen.findByText(/uploaded/i, { selector: "p" });

    expect(recordsApi.answerEmbargo).toHaveBeenCalledWith(42, { embargoed: false, embargoed_until: null });
    const [created] = vi.mocked(recordsApi.create).mock.invocationCallOrder;
    const [answered] = vi.mocked(recordsApi.answerEmbargo).mock.invocationCallOrder;
    const [uploaded] = vi.mocked(recordsApi.uploadManuscript).mock.invocationCallOrder;
    expect(created).toBeLessThan(answered);
    expect(answered).toBeLessThan(uploaded);
  });

  it("sends a Yes with its date", async () => {
    const user = userEvent.setup();
    const until = inDays(90);
    openAtQuestion();
    await answerYes(user, until);

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());
    await screen.findByText(/uploaded/i, { selector: "p" });

    expect(recordsApi.answerEmbargo).toHaveBeenCalledWith(42, { embargoed: true, embargoed_until: until });
  });

  it("does not send the file when the answer could not be saved, and a retry saves it first", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.answerEmbargo).mockRejectedValueOnce(new Error("Network Error"));
    await openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());

    await screen.findByText(/couldn't reach IRIS/i);
    expect(recordsApi.uploadManuscript).not.toHaveBeenCalled();
    expect(recordsApi.create).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Retry upload" }));
    await screen.findByText(/uploaded/i, { selector: "p" });
    expect(recordsApi.answerEmbargo).toHaveBeenCalledTimes(2);
    expect(recordsApi.create).toHaveBeenCalledTimes(1);
    expect(recordsApi.uploadManuscript).toHaveBeenCalledTimes(1);
  });

  it("is not asked again on a draft that has an answer", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ ...COMPLETE }) } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    await screen.findByRole("heading", { name: "Manuscript" });
    expect(screen.queryByRole("radiogroup", { name: /embargo/ })).not.toBeInTheDocument();
  });

  it.each([
    ["no answer yet", { state: "unknown", until: null }],
    ["a release to answer again", { state: "released", until: "2027-01-01" }],
    ["nothing the API disclosed", null],
  ])("asks first on a draft with %s, and saves the answer at once", async (_label, embargo) => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ ...COMPLETE, embargo }) } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    await question();
    await user.click(screen.getByRole("radio", { name: /^No/ }));
    await user.click(continueButton());

    await waitFor(() =>
      expect(recordsApi.answerEmbargo).toHaveBeenCalledWith(42, { embargoed: false, embargoed_until: null }),
    );
    await screen.findByRole("radio", { name: /Proposal/ });
  });

  it("shows the answer on the review, and Edit goes back to the question", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({ ...COMPLETE, embargo: { state: "active", until: "2099-03-01" } }),
    } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    const group = await screen.findByRole("region", { name: "Embargo" });
    expect(group).toHaveTextContent("Mar 1, 2099");
    await user.click(screen.getByRole("button", { name: "Edit embargo answer" }));

    await question();
    expect(screen.getByRole("radio", { name: /^Yes/ })).toBeChecked();
    expect(dateField()).toHaveValue("2099-03-01");
  });

  it("lets a draft whose date has since passed through unchanged, not stuck on the question", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({ ...COMPLETE, embargo: { state: "active", until: "2020-01-01" } }),
    } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    await screen.findByRole("region", { name: "Embargo" });
    await user.click(screen.getByRole("button", { name: "Edit embargo answer" }));
    await question();
    await user.click(continueButton());

    await screen.findByRole("radio", { name: /Proposal/ });
    expect(recordsApi.answerEmbargo).not.toHaveBeenCalled();
  });

  it("says No on the review when the answer is no", async () => {
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ ...COMPLETE }) } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });

    expect(await screen.findByRole("region", { name: "Embargo" })).toHaveTextContent(/No/);
  });

  it("saves a changed answer once, and saves nothing when it did not change", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ ...COMPLETE }) } as never);
    renderScreen(<PublishDialog />, { route: "/?publish=42" });
    await screen.findByRole("region", { name: "Embargo" });

    await user.click(screen.getByRole("button", { name: "Edit embargo answer" }));
    await question();
    await user.click(continueButton());
    await screen.findByRole("radio", { name: /Proposal/ });
    expect(recordsApi.answerEmbargo).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Back" }));
    await question();
    const until = inDays(30);
    await answerYes(user, until);
    expect(recordsApi.answerEmbargo).toHaveBeenCalledTimes(1);
    expect(recordsApi.answerEmbargo).toHaveBeenCalledWith(42, { embargoed: true, embargoed_until: until });
  });

  it("puts the server's refusal on the date and stays on the question", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail({ ...COMPLETE, embargo: null }) } as never);
    vi.mocked(recordsApi.answerEmbargo).mockRejectedValueOnce({
      response: { status: 400, data: { embargoed_until: ["That date has already passed."] } },
    });
    renderScreen(<PublishDialog />, { route: "/?publish=42" });
    await question();

    await user.click(screen.getByRole("radio", { name: /^Yes/ }));
    fireEvent.change(dateField(), { target: { value: inDays(5) } });
    await user.click(continueButton());

    expect(await screen.findByText("That date has already passed.")).toBeInTheDocument();
    expect(dateField()).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("radio", { name: /Proposal/ })).not.toBeInTheDocument();
  });

  describe("suggestions from the PDF", () => {
    it("are not offered under an embargo, and the author fills the fields in", async () => {
      const user = userEvent.setup();
      vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(
        suggestions("ready", { title: "A found title that is long enough" }) as never,
      );
      openAtQuestion();
      await answerYes(user, inDays(30));

      await completeManuscript(user);

      expect(recordsApi.metadataSuggestions).not.toHaveBeenCalled();
      expect(screen.queryByText(/A found title/)).not.toBeInTheDocument();
      expect(screen.queryByText(/couldn't read details/)).not.toBeInTheDocument();
    });

    it("are offered with no embargo", async () => {
      const user = userEvent.setup();
      vi.mocked(recordsApi.metadataSuggestions).mockResolvedValue(
        suggestions("ready", { title: "A found title that is long enough" }) as never,
      );
      await openNew();

      await completeManuscript(user);

      await waitFor(() => expect(recordsApi.metadataSuggestions).toHaveBeenCalled());
      await waitFor(() => expect(screen.getByRole("textbox", { name: /^Title/ })).toHaveValue("A found title that is long enough"));
    });
  });
});
