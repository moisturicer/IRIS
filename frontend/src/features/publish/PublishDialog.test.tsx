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
    update: vi.fn(),
    uploadManuscript: vi.fn(),
    submit: vi.fn(),
    detail: vi.fn(),
  },
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

beforeEach(() => {
  vi.mocked(recordsApi.recordTypes).mockResolvedValue(page(TYPES) as never);
  vi.mocked(recordsApi.classifications).mockResolvedValue(page([{ id: 5, name: "Computing" }]) as never);
  vi.mocked(recordsApi.pscedList).mockResolvedValue(page([{ id: 9, name: "Information Technology" }]) as never);
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue(page(ADVISERS) as never);
  vi.mocked(recordsApi.create).mockResolvedValue({ data: { id: 42 } } as never);
  vi.mocked(recordsApi.update).mockResolvedValue({ data: { id: 42 } } as never);
  vi.mocked(recordsApi.uploadManuscript).mockResolvedValue({ data: { id: 42 } } as never);
  vi.mocked(recordsApi.submit).mockResolvedValue({ data: { detail: "Submitted." } } as never);
  vi.mocked(recordsApi.detail).mockResolvedValue({ data: draftDetail() } as never);
  useAuthStore.setState({
    user: makeUser({ id: SELF_ID, first_name: "Ada", last_name: "Reyes", role_name: ROLES.ADVISER }),
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

function openNew() {
  return renderScreen(<PublishDialog />, { route: "/?publish=new" });
}

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
  it("is a labelled dialog that starts at step 1 of 3", async () => {
    openNew();

    const dialog = await screen.findByRole("dialog", { name: "Publish your research" });
    expect(await within(dialog).findByRole("list", { name: "Publish steps" })).toBeInTheDocument();
    expect(await screen.findByRole("radio", { name: /Proposal/ })).toBeInTheDocument();
  });

  it("does not open for someone who cannot author a record", async () => {
    useAuthStore.setState({ user: makeUser({ role_name: ROLES.KTTO }) });
    openNew();

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("passes axe on the first step", async () => {
    const { container } = openNew();
    await screen.findByRole("radio", { name: /Proposal/ });

    await expectNoBlockingA11yViolations(container);
  });
});

describe("record types (invariant 7)", () => {
  it("offers Thesis / Research and Project directly, with no Proposal behind them", async () => {
    const user = userEvent.setup();
    openNew();

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
    openNew();

    await chooseType(user, /Thesis \/ Research/);
    dropFile(pdf());

    await screen.findByText(/uploaded/i, { selector: "p" });
    expect(recordsApi.create).toHaveBeenCalledTimes(1);
    expect(recordsApi.create).toHaveBeenCalledWith({ title: "My Clearance Study", record_type: 2 });
    expect(recordsApi.uploadManuscript).toHaveBeenCalledWith(42, expect.any(File), expect.any(Object));
  });

  it("is not possible before a type is chosen", async () => {
    openNew();
    const zone = await screen.findByRole("button", { name: "Upload manuscript" });

    expect(zone).toHaveAttribute("aria-disabled", "true");
    dropFile(pdf());
    expect(recordsApi.create).not.toHaveBeenCalled();
  });

  it("refuses a file that is not a PDF before anything is sent", async () => {
    const user = userEvent.setup();
    openNew();

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
    openNew();

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
  it("retries with the same file and type, without creating a second draft", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.uploadManuscript)
      .mockRejectedValueOnce({ response: { status: 500, data: { detail: "Storage is unavailable." } } })
      .mockResolvedValueOnce({ data: { id: 42 } } as never);
    openNew();

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
    openNew();

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
    openNew();

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
    openNew();

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
    openNew();
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
    openNew();
    await completeManuscript(user);

    const combobox = screen.getByRole("combobox", { name: /Adviser/ });
    await user.click(combobox);
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");

    expect(combobox).toHaveValue("Maria C. Santos");
  });

  it("is required for every type", async () => {
    const user = userEvent.setup();
    openNew();
    await completeManuscript(user);

    await user.type(screen.getByRole("textbox", { name: /^Abstract/ }), COMPLETE.abstract);
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Choose your adviser.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("combobox", { name: /Adviser/ })).toHaveFocus());
    expect(recordsApi.update).not.toHaveBeenCalled();
  });
});

describe("Details", () => {
  it("starts with the provisional title and the author's own name", async () => {
    const user = userEvent.setup();
    openNew();
    await completeManuscript(user);

    expect(screen.getByRole("textbox", { name: /^Title/ })).toHaveValue("My Clearance Study");
    expect(screen.getByRole("list", { name: "Authors added" })).toHaveTextContent("Ada Reyes");
  });

  it("patches the draft on Continue", async () => {
    const user = userEvent.setup();
    openNew();
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
    openNew();
    await completeManuscript(user);
    await user.clear(screen.getByRole("textbox", { name: /^Title/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    const title = screen.getByRole("textbox", { name: /^Title/ });
    await waitFor(() => expect(title).toHaveFocus());
    expect(title).toHaveAttribute("aria-invalid", "true");
    expect(title).toHaveAccessibleDescription("Title must be at least 5 characters.");
  });

  it("passes axe with More details open", async () => {
    const user = userEvent.setup();
    const { container } = openNew();
    await completeManuscript(user);
    await user.click(screen.getByText("More details"));

    await expectNoBlockingA11yViolations(container);
  });
});

describe("the review", () => {
  it("shows every value entered, and Edit returns to its step", async () => {
    const user = userEvent.setup();
    openNew();
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
    openNew();
    await completeManuscript(user);
    await completeDetails(user);

    await user.click(screen.getByRole("button", { name: "Edit hints" }));

    expect(await screen.findByRole("checkbox", { name: /intellectual property/ })).toBeVisible();
  });

  it("asks for no supporting documents anywhere", async () => {
    const user = userEvent.setup();
    openNew();
    await completeManuscript(user);
    await completeDetails(user);

    expect(documentsApi.slots).not.toHaveBeenCalled();
    expect(screen.queryByText(/supporting document/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/required documents/i)).not.toBeInTheDocument();
  });

  it("passes axe", async () => {
    const user = userEvent.setup();
    const { container } = openNew();
    await completeManuscript(user);
    await completeDetails(user);

    await expectNoBlockingA11yViolations(container);
  });
});

describe("submitting", () => {
  it("needs consent, and sends the DPA flag", async () => {
    const user = userEvent.setup();
    openNew();
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
    openNew();
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
      data: draftDetail({ pipeline_status: "rdco_intake", current_holders: [] }),
    } as never);
    openNew();
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
        pipeline_status: "rdco_intake",
        current_holders: [{ party: "intake", label: "Intake", opened_at: null, opened_by: null }],
      }),
    } as never);
    const { container } = openNew();
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
        pipeline_status: "rdco_intake",
        current_holders: [{ party: "intake", label: "Intake", opened_at: null, opened_by: null }],
      }),
    } as never);
    openNew();
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
        pipeline_status: "adviser_review",
        adviser: 21,
        current_holders: [{ party: "adviser", label: "Adviser", opened_at: null, opened_by: null }],
      }),
    } as never);
    openNew();
    await completeManuscript(user);
    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByRole("heading", { name: "Sent to Maria C. Santos for review" })).toBeInTheDocument();
  });

  it("starts over on Publish another", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.detail).mockResolvedValue({
      data: draftDetail({ pipeline_status: "rdco_intake", current_holders: [] }),
    } as never);
    openNew();
    await completeManuscript(user);
    await completeDetails(user);
    await user.click(screen.getByRole("checkbox", { name: /I have read/i }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await user.click(await screen.findByRole("button", { name: "Publish another" }));

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
      data: draftDetail({ pipeline_status: "adviser_review" }),
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
    openNew();

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
    openNew();
    await screen.findByRole("radio", { name: /Proposal/ });

    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
