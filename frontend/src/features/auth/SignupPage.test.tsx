/**
 * The register screen, asserted through the accessible tree (IR-539, IR-707).
 *
 * Before IR-539 no label on this screen was associated with its control, so
 * nine controls had no accessible name, every error was a paragraph tied to no
 * field, and the role choice was two buttons that announced no state. These
 * tests hold the repair: every query goes by role and name, or by label, as in
 * `LoginPage.test.tsx` -- a test that can find a control after its label
 * association breaks cannot catch the bug this file exists for.
 *
 * IR-707 split the one long form into three steps in the Dossier frame, so the
 * tests walk the steps the way a registrant does. Validation messages and the
 * register request were left alone on purpose, so they stay pinned below.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { useLocation } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { authApi } from "@/api/auth";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import SignupPage from "./SignupPage";

type User = ReturnType<typeof userEvent.setup>;

const page = <T,>(results: T[]) => ({ data: { count: results.length, next: null, previous: null, results } });

const COLLEGES = [
  { id: 1, name: "College of Computer Studies", code: "CCS" },
  { id: 2, name: "College of Engineering and Architecture", code: "CEA" },
];
const DEPARTMENTS = [
  { id: 10, name: "Computer Science", college: 1 },
  { id: 11, name: "Information Technology", college: 1 },
  { id: 20, name: "Civil Engineering", college: 2 },
];
const COURSES = [
  { id: 100, name: "BS Computer Science", department: 10 },
  { id: 110, name: "BS Information Technology", department: 11 },
  { id: 200, name: "BS Civil Engineering", department: 20 },
];

/** Shows the router's location key, which changes on any navigation, even to the same path. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Router location">{`${location.pathname}#${location.key}`}</output>;
}

function stubOptions() {
  vi.spyOn(accountsApi, "colleges").mockResolvedValue(page(COLLEGES) as never);
  vi.spyOn(accountsApi, "departments").mockResolvedValue(page(DEPARTMENTS) as never);
  vi.spyOn(accountsApi, "courses").mockResolvedValue(page(COURSES) as never);
}

function renderSignup() {
  stubOptions();
  return renderScreen(<><SignupPage /><LocationProbe /></>, { route: "/signup" });
}

const steps = () => screen.getByRole("navigation", { name: "Registration steps" });
const tab = (name: RegExp) => within(steps()).getByRole("link", { name });
const stepHeading = () => screen.getByRole("heading", { level: 3, name: /^Step \d of 3/ });

const firstName = () => screen.getByRole("textbox", { name: "First Name" });
const lastName  = () => screen.getByRole("textbox", { name: "Last Name" });
const initial   = () => screen.getByRole("textbox", { name: "M.I." });
const email     = () => screen.getByRole("textbox", { name: "CIT-U Email" });
const college   = () => screen.getByRole("combobox", { name: "College" });
const program   = () => screen.getByRole("combobox", { name: "Program" });
const department = () => screen.getByRole("combobox", { name: "Department" });
/** The consent box's name refers to the data notice (IR-540). */
const CONSENT = /I have read the data notice/;

/** The options are loaded once the college select is enabled. */
async function optionsLoaded() {
  await waitFor(() => expect(college()).toBeEnabled());
}

function acceptRegistration() {
  return vi.spyOn(authApi, "register").mockResolvedValue({ data: {} } as never);
}

async function fillIdentity(user: User, role: "Student" | "Adviser" = "Student") {
  if (role === "Adviser") await user.click(screen.getByRole("radio", { name: "Adviser" }));
  await user.type(firstName(), " Juan ");
  await user.type(lastName(), "Dela Cruz");
  await user.type(initial(), "S.");
  await user.type(email(), "juan@cit.edu");
  await user.click(screen.getByRole("button", { name: "Continue to affiliation" }));
}

async function fillAffiliation(user: User, role: "Student" | "Adviser" = "Student") {
  await optionsLoaded();
  await user.selectOptions(college(), "College of Computer Studies");
  if (role === "Student") await user.selectOptions(program(), "BS Computer Science");
  else await user.selectOptions(department(), "Information Technology");
  await user.click(screen.getByRole("button", { name: "Continue to security" }));
}

async function finish(user: User) {
  await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
  await user.type(screen.getByLabelText("Confirm Password"), "IrisDemo123!");
  await user.click(screen.getByRole("checkbox", { name: CONSENT }));
  await user.click(screen.getByRole("button", { name: "Register" }));
}

/** A complete registration, submitted with consent. */
async function submit(user: User, role: "Student" | "Adviser" = "Student") {
  await fillIdentity(user, role);
  await fillAffiliation(user, role);
  await finish(user);
}

afterEach(() => {
  vi.restoreAllMocks();
});

// Each walk through the steps types key by key, which took close to the 15s
// default in the dev container, so the blocks get room rather than a flaky edge.
describe("the register steps", { timeout: 30_000 }, () => {
  it("opens on Identity in the folder, under the register headline", async () => {
    renderSignup();

    expect(screen.getByRole("heading", { level: 2, name: "Create an Account" })).toBeInTheDocument();
    expect(screen.getByText(/research identity\./)).toBeInTheDocument();
    expect(stepHeading()).toHaveTextContent("Step 1 of 3 · Identity");

    expect(tab(/^Identity, current step$/)).toHaveAttribute("aria-current", "step");
    for (const name of [/^Affiliation, not started$/, /^Security & agreement, not started$/]) {
      expect(tab(name)).toHaveAttribute("aria-disabled", "true");
      expect(tab(name)).not.toHaveAttribute("href");
    }
  });

  it("starts with every field empty", async () => {
    renderSignup();

    for (const field of [firstName(), lastName(), initial(), email()]) {
      expect(field).toHaveValue("");
      // No sample name or address sits in a field as a placeholder either (IR-704 story 25).
      expect(field).not.toHaveAttribute("placeholder");
    }
  });

  it("names the role group, and reads the role as Adviser", async () => {
    renderSignup();

    const roles = screen.getByRole("radiogroup", { name: "I am registering as" });
    expect(within(roles).getByRole("radio", { name: "Student" })).toBeChecked();
    expect(within(roles).getByRole("radio", { name: "Adviser" })).not.toBeChecked();
    expect(screen.queryByText(/Faculty/)).not.toBeInTheDocument();
  });

  it("checks only Identity on Continue, with today's messages", async () => {
    const user = userEvent.setup();
    renderSignup();

    await user.type(initial(), "S");
    await user.click(screen.getByRole("button", { name: "Continue to affiliation" }));

    expect(stepHeading()).toHaveTextContent("Step 1 of 3 · Identity");
    expect(firstName()).toHaveAccessibleDescription("First name is required.");
    expect(lastName()).toHaveAccessibleDescription("Last name is required.");
    expect(initial()).toHaveAccessibleDescription("Missing (.).");
    expect(email()).toHaveAccessibleDescription("Email is required.");
    expect(email()).toHaveAttribute("aria-invalid", "true");
    // Nothing from a step not yet seen is mentioned.
    expect(screen.queryByText("Please select your college.")).not.toBeInTheDocument();
    expect(screen.queryByText("Password is required.")).not.toBeInTheDocument();

    await user.type(email(), "not-an-email");
    expect(email()).toHaveAccessibleDescription("Enter a valid email address.");
  });

  it("moves focus to the step heading, and marks the finished step completed", async () => {
    const user = userEvent.setup();
    renderSignup();

    await fillIdentity(user);

    expect(stepHeading()).toHaveTextContent("Step 2 of 3 · Affiliation");
    expect(stepHeading()).toHaveFocus();
    expect(tab(/^Identity, completed$/)).toHaveAttribute("href", "/signup");
    expect(tab(/^Affiliation, current step$/)).toHaveAttribute("aria-current", "step");
    expect(tab(/^Security & agreement, not started$/)).toHaveAttribute("aria-disabled", "true");
  });

  it("keeps every answer across Back, the tabs and Continue, without changing the URL", async () => {
    const user = userEvent.setup();
    renderSignup();
    const before = screen.getByRole("status", { name: "Router location" }).textContent;

    await fillIdentity(user);
    await fillAffiliation(user);
    expect(stepHeading()).toHaveTextContent("Step 3 of 3 · Security & agreement");
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(stepHeading()).toHaveFocus();
    expect(college()).toHaveDisplayValue("College of Computer Studies");
    expect(program()).toHaveDisplayValue("BS Computer Science");

    await user.click(tab(/^Identity, completed$/));
    expect(stepHeading()).toHaveTextContent("Step 1 of 3 · Identity");
    expect(firstName()).toHaveValue(" Juan ");
    expect(email()).toHaveValue("juan@cit.edu");

    // Security is not finished (no confirmation, no consent), so its tab cannot be chosen.
    expect(tab(/^Security & agreement, not started$/)).toHaveAttribute("aria-disabled", "true");
    await user.click(tab(/^Affiliation, completed$/));
    await user.click(screen.getByRole("button", { name: "Continue to security" }));
    expect(screen.getByLabelText("Password")).toHaveValue("IrisDemo123!");

    expect(screen.getByRole("status", { name: "Router location" }).textContent).toBe(before);
  });

  it("cannot reach a step not started, by mouse or by keyboard", async () => {
    const user = userEvent.setup();
    renderSignup();

    await user.click(tab(/^Affiliation, not started$/));
    expect(stepHeading()).toHaveTextContent("Step 1 of 3 · Identity");

    // Tab from the start of the page never lands on a tab that is not a link to a step.
    const reached: Element[] = [];
    for (let i = 0; i < 6; i++) {
      await user.tab();
      reached.push(document.activeElement!);
    }
    expect(reached).not.toContain(tab(/^Affiliation, not started$/));
    expect(reached).not.toContain(tab(/^Security & agreement, not started$/));
    expect(reached).not.toContain(tab(/^Identity, current step$/));
  });

  it("keeps the college, clears the program and says why when the role changes", async () => {
    const user = userEvent.setup();
    renderSignup();
    await fillIdentity(user);
    await fillAffiliation(user);

    await user.click(tab(/^Identity, completed$/));
    await user.click(screen.getByRole("radio", { name: "Adviser" }));

    // The Affiliation tab is not finished any more.
    expect(tab(/^Affiliation, not started$/)).toHaveAttribute("aria-disabled", "true");

    await user.click(screen.getByRole("button", { name: "Continue to affiliation" }));
    const note = screen.getAllByRole("status").find((s) => /Your role changed/.test(s.textContent ?? ""));
    expect(note).toHaveTextContent("Your role changed to Adviser");
    expect(note).toHaveTextContent(/Choose a department/);
    expect(college()).toHaveDisplayValue("College of Computer Studies");
    expect(department()).toHaveValue("");
    expect(screen.queryByRole("combobox", { name: "Program" })).not.toBeInTheDocument();

    await user.selectOptions(department(), "Computer Science");
    expect(screen.queryByText("Your role changed to Adviser")).not.toBeInTheDocument();
  });

  it("cannot jump to a finished step past one a change has reopened", async () => {
    const user = userEvent.setup();
    renderSignup();
    await fillIdentity(user);
    await fillAffiliation(user);
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
    await user.type(screen.getByLabelText("Confirm Password"), "IrisDemo123!");
    await user.click(screen.getByRole("checkbox", { name: CONSENT }));

    await user.click(tab(/^Identity, completed$/));
    expect(tab(/^Security & agreement, completed$/)).toHaveAttribute("href", "/signup");
    await user.click(screen.getByRole("radio", { name: "Adviser" }));

    // Security's answers still pass, but Affiliation now has no department.
    const security = tab(/^Security & agreement, not started$/);
    expect(security).toHaveAttribute("aria-disabled", "true");
    expect(security).not.toHaveAttribute("href");
    await user.click(security);
    expect(stepHeading()).toHaveTextContent("Step 1 of 3 · Identity");
  });

  it("marks each step's required fields, in words and as a state, and leaves M.I. optional", async () => {
    const user = userEvent.setup();
    renderSignup();

    for (const field of [firstName(), lastName(), email()]) expect(field).toBeRequired();
    expect(initial()).not.toBeRequired();
    // The word is on screen once per required field, not only a colour.
    expect(screen.getAllByText("(required)")).toHaveLength(3);

    await fillIdentity(user);
    await optionsLoaded();
    expect(college()).toBeRequired();
    expect(program()).toBeRequired();
    expect(screen.getAllByText("(required)")).toHaveLength(2);

    await fillAffiliation(user);
    expect(screen.getByLabelText("Password")).toBeRequired();
    expect(screen.getByLabelText("Confirm Password")).toBeRequired();
    expect(screen.getAllByText("(required)")).toHaveLength(2);
  });

  it("keeps each step's fields in their order, the forward action after them", async () => {
    const user = userEvent.setup();
    renderSignup();
    const inOrder = (els: Element[]) => {
      for (let i = 1; i < els.length; i++) {
        expect(els[i - 1].compareDocumentPosition(els[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      }
    };

    inOrder([
      screen.getByRole("radio", { name: "Student" }),
      firstName(), lastName(), initial(), email(),
      screen.getByRole("button", { name: "Continue to affiliation" }),
    ]);
    await fillIdentity(user);
    await optionsLoaded();
    inOrder([college(), program(), screen.getByRole("button", { name: "Continue to security" })]);
    await fillAffiliation(user);
    inOrder([
      screen.getByLabelText("Password"),
      screen.getByLabelText("Confirm Password"),
      screen.getByRole("checkbox", { name: CONSENT }),
      screen.getByRole("button", { name: "Register" }),
    ]);
  });

  it("clears the program when the college changes, and reopens Affiliation", async () => {
    const user = userEvent.setup();
    renderSignup();
    await fillIdentity(user);
    await fillAffiliation(user);
    await user.click(tab(/^Affiliation, completed$/));

    await user.selectOptions(college(), "College of Engineering and Architecture");

    expect(program()).toHaveValue("");
    await user.click(tab(/^Identity, completed$/));
    expect(tab(/^Affiliation, not started$/)).toHaveAttribute("aria-disabled", "true");
  });

  it("narrows programs to the chosen college, grouped by department", async () => {
    const user = userEvent.setup();
    renderSignup();
    await fillIdentity(user);
    await optionsLoaded();

    expect(program()).toBeDisabled();
    await user.selectOptions(college(), "College of Computer Studies");

    expect(program()).toBeEnabled();
    const cs = within(program()).getByRole("group", { name: "Computer Science" });
    expect(within(cs).getByRole("option", { name: "BS Computer Science" })).toBeInTheDocument();
    expect(within(program()).queryByRole("option", { name: "BS Civil Engineering" })).not.toBeInTheDocument();
  });

  it("asks an Adviser for a department, narrowed to the college", async () => {
    const user = userEvent.setup();
    renderSignup();
    await fillIdentity(user, "Adviser");
    await optionsLoaded();
    await user.selectOptions(college(), "College of Computer Studies");

    expect(department()).toBeRequired();
    expect(within(department()).getByRole("option", { name: "Computer Science" })).toBeInTheDocument();
    expect(within(department()).queryByRole("option", { name: "Civil Engineering" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue to security" }));
    expect(department()).toHaveAccessibleDescription("Please select your department.");
  });

  it("moves between the roles with the arrow keys, as one group", async () => {
    const user = userEvent.setup();
    renderSignup();

    screen.getByRole("radio", { name: "Student" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("radio", { name: "Adviser" })).toBeChecked();
  });

  it("has no serious or critical accessibility violations on any step", async () => {
    const user = userEvent.setup();
    const { container } = renderSignup();
    await expectNoBlockingA11yViolations(container);

    await user.click(screen.getByRole("button", { name: "Continue to affiliation" }));
    await expectNoBlockingA11yViolations(container);

    await fillIdentity(user);
    await optionsLoaded();
    await expectNoBlockingA11yViolations(container);

    await fillAffiliation(user);
    await expectNoBlockingA11yViolations(container);
  });
});

describe("Security & agreement", { timeout: 30_000 }, () => {
  async function reachSecurity(user: User) {
    await fillIdentity(user);
    await fillAffiliation(user);
  }

  it("gives password feedback in words", async () => {
    const user = userEvent.setup();
    renderSignup();
    await reachSecurity(user);

    const password = screen.getByLabelText("Password");
    expect(password).toBeRequired();
    expect(password).toHaveAccessibleDescription("At least 8 characters");

    await user.type(password, "short");
    expect(password).toHaveAccessibleDescription("Password must be at least 8 characters.");

    await user.type(password, "-enough");
    expect(password).toHaveAccessibleDescription("At least 8 characters");
    expect(password).not.toHaveAttribute("aria-invalid");

    const confirm = screen.getByLabelText("Confirm Password");
    await user.type(confirm, "short-enougX");
    expect(confirm).toHaveAccessibleDescription("Passwords do not match.");
    await user.clear(confirm);
    await user.type(confirm, "short-enough");
    expect(confirm).toHaveAccessibleDescription("Passwords match");
  });

  it("shows and hides each password from a named toggle", async () => {
    const user = userEvent.setup();
    renderSignup();
    await reachSecurity(user);

    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show confirmed password" }));
    expect(screen.getByLabelText("Confirm Password")).toHaveAttribute("type", "text");
  });

  it("says what happens next before anything is sent", async () => {
    const user = userEvent.setup();
    renderSignup();
    await reachSecurity(user);

    const next = within(screen.getByRole("list", { name: "What happens next" })).getAllByRole("listitem");
    expect(next.map((s) => s.textContent)).toEqual([
      expect.stringMatching(/verify your email/i),
      expect.stringMatching(/RDCO/),
    ]);
  });

  it("refuses Register without consent, on the checkbox itself", async () => {
    const user = userEvent.setup();
    const register = acceptRegistration();
    renderSignup();
    await reachSecurity(user);
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
    await user.type(screen.getByLabelText("Confirm Password"), "IrisDemo123!");

    const action = screen.getByRole("button", { name: "Register" });
    expect(action).toBeEnabled();
    await user.click(action);

    const consent = screen.getByRole("checkbox", { name: CONSENT });
    expect(consent).toHaveAttribute("aria-invalid", "true");
    expect(consent).toHaveAccessibleDescription("Agree to the data notice to register.");
    expect(register).not.toHaveBeenCalled();

    await user.click(consent);
    expect(consent).not.toHaveAttribute("aria-invalid");
  });

  it("opens and closes the data notice from the keyboard, keeping what was typed", async () => {
    const user = userEvent.setup();
    renderSignup();
    await reachSecurity(user);
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");

    const notice = () => screen.getByRole("button", { name: "Read the data notice" });
    notice().focus();
    expect(notice()).toHaveAttribute("aria-expanded", "false");
    await user.keyboard("{Enter}");
    expect(notice()).toHaveAttribute("aria-expanded", "true");

    const text = screen.getByRole("region", { name: "Read the data notice" }).textContent ?? "";
    for (const item of ["name", "CIT-U email", "college", "program or department", "the role you ask for", "hash"]) {
      expect(text).toContain(item);
    }
    expect(text).toMatch(/RDCO/);
    expect(text).toMatch(/interim/i);
    expect(text).toMatch(/Terms of Service and Data Privacy Policy/);

    await user.keyboard("{Enter}");
    expect(screen.queryByRole("region", { name: "Read the data notice" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue("IrisDemo123!");
    await expectNoBlockingA11yViolations(document.body);
  });

  it("links to no page that does not exist", async () => {
    const user = userEvent.setup();
    renderSignup();
    await reachSecurity(user);

    const dead = screen.queryAllByRole("link").filter((a) => a.getAttribute("href") === "#");
    expect(dead).toEqual([]);
  });

});

/**
 * What IR-539 did not change, and IR-707 did not either. The request and its
 * fields are pinned. One deliberate change since IR-539 (IR-540): the request
 * carries `consent_given: true`, which the serializer always required.
 */
describe("what the register screen sends", { timeout: 30_000 }, () => {
  it("sends a Student's registration unchanged", async () => {
    const user = userEvent.setup();
    const register = acceptRegistration();
    renderSignup();

    await submit(user);

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1));
    const payload = register.mock.calls[0][0];
    expect(payload).toEqual({
      email: "juan@cit.edu",
      first_name: "Juan",
      middle_initial: "S.",
      last_name: "Dela Cruz",
      password: "IrisDemo123!",
      confirm_password: "IrisDemo123!",
      consent_given: true,
      role_name: "Student",
      course_id: 100,
    });
    expect(Object.keys(payload)).toEqual([
      "email", "first_name", "middle_initial", "last_name",
      "password", "confirm_password", "consent_given", "role_name", "course_id",
    ]);
  });

  it("sends an Adviser's registration unchanged", async () => {
    const user = userEvent.setup();
    const register = acceptRegistration();
    renderSignup();

    await submit(user, "Adviser");

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1));
    expect(register.mock.calls[0][0]).toEqual({
      email: "juan@cit.edu",
      first_name: "Juan",
      middle_initial: "S.",
      last_name: "Dela Cruz",
      password: "IrisDemo123!",
      confirm_password: "IrisDemo123!",
      consent_given: true,
      role_name: "Adviser",
      college_id: 1,
      department_id: 11,
    });
  });

  it("disables Register and says it is working, so a second press sends nothing", async () => {
    const user = userEvent.setup();
    let settle: (value: unknown) => void = () => {};
    const register = vi.spyOn(authApi, "register").mockReturnValue(
      new Promise((resolve) => { settle = resolve; }) as never,
    );
    renderSignup();
    await submit(user);

    const working = await screen.findByRole("button", { name: "Creating account…" });
    expect(working).toBeDisabled();
    await user.click(working);
    expect(register).toHaveBeenCalledTimes(1);

    settle({ data: {} });
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
  });

  it("writes nothing to localStorage or sessionStorage", async () => {
    const user = userEvent.setup();
    acceptRegistration();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    renderSignup();

    await submit(user);
    await screen.findByRole("heading", { name: "Check your email" });

    expect(setItem).not.toHaveBeenCalled();
  });
});

/**
 * What happens after Register (IR-540), now inside the folder (IR-707).
 */
describe("the register screen's finish", { timeout: 30_000 }, () => {
  it("confirms in place, naming the exact address entered, with every tab completed and none clickable", async () => {
    const user = userEvent.setup();
    const register = acceptRegistration();
    const { container } = renderSignup();

    await submit(user);

    const confirmation = await screen.findByRole("heading", { level: 2, name: "Check your email" });
    expect(register).toHaveBeenCalledTimes(1);
    expect(confirmation).toHaveFocus();
    expect(screen.getByText("juan@cit.edu")).toBeInTheDocument();
    expect(screen.getByText(/RDCO reviews your request to join as a Student/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute("href", "/login");

    const nav = steps();
    expect(within(nav).queryAllByRole("link")).toEqual([]);
    expect(nav).toHaveTextContent(/Identity, completed.*Affiliation, completed.*Security & agreement, completed/);

    // The form is gone: the confirmation replaces it rather than sitting under it.
    expect(screen.queryByRole("textbox", { name: "First Name" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });
});

/**
 * A refused registration says why, where it applies (IR-540). These are the
 * refusals that belong to Security & agreement itself; IR-708 routes the rest.
 */
describe("a refused registration", { timeout: 30_000 }, () => {
  const refuse = (data: unknown, status = 400) =>
    vi.spyOn(authApi, "register").mockRejectedValue({ response: { status, data } });

  it("shows every reason the server refused a password, not just the first (IR-647)", async () => {
    const user = userEvent.setup();
    refuse({ password: ["This password is too common.", "This password is entirely numeric."] });
    const { container } = renderSignup();
    await submit(user);

    await waitFor(() =>
      expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(
        "This password is too common. This password is entirely numeric.",
      ),
    );
    await expectNoBlockingA11yViolations(container);
  });

  it("says a refusal on an earlier step's field on Security, and keeps it on that field", async () => {
    const user = userEvent.setup();
    refuse({ email: ["This email address is already registered."] });
    renderSignup();
    await submit(user);

    // Email is not on screen here, so the message is said where the registrant is.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This email address is already registered.");
    expect(stepHeading()).toHaveTextContent("Step 3 of 3 · Security & agreement");

    await user.click(tab(/^Identity, completed$/));
    expect(email()).toHaveAccessibleDescription("This email address is already registered.");
    expect(email()).toHaveAttribute("aria-invalid", "true");
    expect(email()).toHaveValue("juan@cit.edu");
  });

  it("puts errors named the server's way on the field they mean", async () => {
    const user = userEvent.setup();
    refuse({ confirm_password: ["Passwords do not match."] });
    renderSignup();
    await submit(user);

    await waitFor(() =>
      expect(screen.getByLabelText("Confirm Password")).toHaveAccessibleDescription("Passwords do not match."),
    );
  });

  it("shows an error that belongs to no field as an alert above Register", async () => {
    const user = userEvent.setup();
    refuse({ non_field_errors: ["Registration is closed for now."] });
    renderSignup();
    await submit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Registration is closed for now.");
    const register = screen.getByRole("button", { name: "Register" });
    expect(alert.compareDocumentPosition(register) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("says IRIS could not be reached when no reply came, and blames no field", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "register").mockRejectedValue(new Error("Network Error"));
    renderSignup();
    await submit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/IRIS can't be reached right now/);
    expect(screen.getByLabelText("Password")).not.toHaveAttribute("aria-invalid");
  });
});

/**
 * The college, program and department lists failing to load (IR-540). Before,
 * a toast said "Please refresh." and left three empty selects behind it.
 */
describe("form options that fail to load", { timeout: 30_000 }, () => {
  it("say so on Affiliation, and Try again fills the selects", async () => {
    const user = userEvent.setup();
    vi.spyOn(accountsApi, "colleges")
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValue(page(COLLEGES) as never);
    vi.spyOn(accountsApi, "departments").mockResolvedValue(page(DEPARTMENTS) as never);
    vi.spyOn(accountsApi, "courses").mockResolvedValue(page(COURSES) as never);
    renderScreen(<SignupPage />, { route: "/signup" });
    await fillIdentity(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't load the colleges, programs and departments/i);

    await user.click(within(alert).getByRole("button", { name: "Try again" }));

    await waitFor(() =>
      expect(within(college()).getByRole("option", { name: "College of Computer Studies" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(tab(/^Identity, completed$/));
    expect(firstName()).toHaveValue(" Juan ");
  });
});
