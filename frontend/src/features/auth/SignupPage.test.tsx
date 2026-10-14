/**
 * The register screen, asserted through the accessible tree (IR-539).
 *
 * Before IR-539 no label on this screen was associated with its control, so
 * nine controls had no accessible name, every error was a paragraph tied to no
 * field, and the role choice was two buttons that announced no state. These
 * tests hold the repair: every query goes by role and name, or by label, as in
 * `LoginPage.test.tsx` -- a test that can find a control after its label
 * association breaks cannot catch the bug this file exists for.
 *
 * Validation, its messages and the register request were left alone on
 * purpose, so the last block pins them.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { accountsApi } from "@/api/accounts";
import { authApi } from "@/api/auth";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import SignupPage from "./SignupPage";

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

function renderSignup() {
  vi.spyOn(accountsApi, "colleges").mockResolvedValue(page(COLLEGES) as never);
  vi.spyOn(accountsApi, "departments").mockResolvedValue(page(DEPARTMENTS) as never);
  vi.spyOn(accountsApi, "courses").mockResolvedValue(page(COURSES) as never);
  return renderScreen(<SignupPage />, { route: "/signup" });
}

/** The options are loaded once the college select is enabled. */
async function optionsLoaded() {
  await waitFor(() => expect(screen.getByRole("combobox", { name: "College" })).toBeEnabled());
}

const college = () => screen.getByRole("combobox", { name: "College" });
const program = () => screen.getByRole("combobox", { name: "Program" });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the register screen", () => {
  it("names every control", async () => {
    renderSignup();
    await optionsLoaded();

    const roles = screen.getByRole("radiogroup", { name: "I am registering as" });
    expect(within(roles).getByRole("radio", { name: "Student" })).toBeChecked();
    expect(within(roles).getByRole("radio", { name: "Faculty / Adviser" })).not.toBeChecked();

    for (const name of ["First Name", "Last Name", "M.I.", "CIT-U Email"]) {
      expect(screen.getByRole("textbox", { name })).toBeInTheDocument();
    }
    expect(college()).toBeInTheDocument();
    expect(program()).toBeInTheDocument();

    // A password input has no implicit role, so it is reached by its label.
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirm Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show password" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show confirmed password" })).toBeInTheDocument();

    expect(screen.getByRole("checkbox", { name: /I agree to the IRIS/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Register" })).toBeInTheDocument();
  });

  it("marks the required fields, in words and as a state, and leaves M.I. optional", async () => {
    renderSignup();
    await optionsLoaded();

    for (const name of ["First Name", "Last Name", "CIT-U Email"]) {
      expect(screen.getByRole("textbox", { name })).toBeRequired();
    }
    expect(college()).toBeRequired();
    expect(program()).toBeRequired();
    expect(screen.getByLabelText("Password")).toBeRequired();
    expect(screen.getByLabelText("Confirm Password")).toBeRequired();
    expect(screen.getByRole("textbox", { name: "M.I." })).not.toBeRequired();

    // The word is on screen once per required field, not only a colour.
    expect(screen.getAllByText("(required)")).toHaveLength(7);
  });

  it("announces each error as its own field's description, and the field as invalid", async () => {
    const user = userEvent.setup();
    renderSignup();
    await optionsLoaded();

    await user.click(screen.getByRole("checkbox", { name: /I agree to the IRIS/ }));
    await user.click(screen.getByRole("button", { name: "Register" }));

    const expected: Array<[HTMLElement, string]> = [
      [screen.getByRole("textbox", { name: "First Name" }), "First name is required."],
      [screen.getByRole("textbox", { name: "Last Name" }), "Last name is required."],
      [screen.getByRole("textbox", { name: "CIT-U Email" }), "Email is required."],
      [college(), "Please select your college."],
      [program(), "Please select your program."],
      [screen.getByLabelText("Password"), "Password is required."],
      [screen.getByLabelText("Confirm Password"), "Please confirm your password."],
    ];
    for (const [field, message] of expected) {
      expect(field).toHaveAttribute("aria-invalid", "true");
      expect(field).toHaveAccessibleDescription(message);
    }

    // An optional field left blank is not an error.
    expect(screen.getByRole("textbox", { name: "M.I." })).not.toHaveAttribute("aria-invalid");
  });

  it("gives password feedback in words", async () => {
    const user = userEvent.setup();
    renderSignup();
    await optionsLoaded();

    const password = screen.getByLabelText("Password");
    expect(password).toHaveAccessibleDescription("At least 8 characters");

    await user.type(password, "short");
    expect(password).toHaveAccessibleDescription("Password must be at least 8 characters.");

    await user.type(password, "-enough");
    expect(password).toHaveAccessibleDescription("At least 8 characters");
    expect(password).not.toHaveAttribute("aria-invalid");

    const confirm = screen.getByLabelText("Confirm Password");
    await user.type(confirm, "short-enough");
    expect(confirm).toHaveAccessibleDescription("Passwords match");
  });

  it("shows and hides each password from a named toggle", async () => {
    const user = userEvent.setup();
    renderSignup();
    await optionsLoaded();

    const password = screen.getByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show confirmed password" }));
    expect(screen.getByLabelText("Confirm Password")).toHaveAttribute("type", "text");
  });

  it("narrows programs to the chosen college, grouped by department", async () => {
    const user = userEvent.setup();
    renderSignup();
    await optionsLoaded();

    expect(program()).toBeDisabled();

    await user.selectOptions(college(), "College of Computer Studies");

    expect(program()).toBeEnabled();
    const cs = within(program()).getByRole("group", { name: "Computer Science" });
    expect(within(cs).getByRole("option", { name: "BS Computer Science" })).toBeInTheDocument();
    const it_ = within(program()).getByRole("group", { name: "Information Technology" });
    expect(within(it_).getByRole("option", { name: "BS Information Technology" })).toBeInTheDocument();

    expect(within(program()).queryByRole("group", { name: "Civil Engineering" })).not.toBeInTheDocument();
    expect(within(program()).queryByRole("option", { name: "BS Civil Engineering" })).not.toBeInTheDocument();
  });

  it("swaps program for department when the role changes", async () => {
    const user = userEvent.setup();
    renderSignup();
    await optionsLoaded();
    await user.selectOptions(college(), "College of Computer Studies");

    await user.click(screen.getByRole("radio", { name: "Faculty / Adviser" }));

    expect(screen.getByRole("radio", { name: "Faculty / Adviser" })).toBeChecked();
    expect(screen.queryByRole("combobox", { name: "Program" })).not.toBeInTheDocument();
    const department = screen.getByRole("combobox", { name: "Department" });
    expect(department).toBeRequired();
    expect(within(department).getByRole("option", { name: "Computer Science" })).toBeInTheDocument();
    expect(within(department).queryByRole("option", { name: "Civil Engineering" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Student" }));
    expect(screen.queryByRole("combobox", { name: "Department" })).not.toBeInTheDocument();
    expect(program()).toBeInTheDocument();
  });

  it("moves between the roles with the arrow keys, as one group", async () => {
    const user = userEvent.setup();
    renderSignup();
    await optionsLoaded();

    screen.getByRole("radio", { name: "Student" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("radio", { name: "Faculty / Adviser" })).toBeChecked();
    expect(screen.getByRole("combobox", { name: "Department" })).toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations, at rest or with errors", async () => {
    const user = userEvent.setup();
    const { container } = renderSignup();
    await optionsLoaded();
    await expectNoBlockingA11yViolations(container);

    await user.click(screen.getByRole("checkbox", { name: /I agree to the IRIS/ }));
    await user.click(screen.getByRole("button", { name: "Register" }));
    await expectNoBlockingA11yViolations(container);
  });
});

/**
 * What IR-539 did not change. The ticket rebuilt the controls and nothing
 * beneath them, so the request, the field order and the messages are pinned.
 */
// These fill the whole form key by key, which took close to the 15s default in
// the dev container, so they get room rather than a flaky edge.
describe("what the register screen sends", { timeout: 30_000 }, () => {
  function acceptRegistration() {
    return vi.spyOn(authApi, "register").mockResolvedValue({ data: {} } as never);
  }

  async function fillCommonFields(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByRole("textbox", { name: "First Name" }), " Juan ");
    await user.type(screen.getByRole("textbox", { name: "Last Name" }), "Dela Cruz");
    await user.type(screen.getByRole("textbox", { name: "M.I." }), "S.");
    await user.type(screen.getByRole("textbox", { name: "CIT-U Email" }), "juan@cit.edu");
    await user.selectOptions(college(), "College of Computer Studies");
  }

  async function finish(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
    await user.type(screen.getByLabelText("Confirm Password"), "IrisDemo123!");
    await user.click(screen.getByRole("checkbox", { name: /I agree to the IRIS/ }));
    await user.click(screen.getByRole("button", { name: "Register" }));
  }

  it("sends a Student's registration unchanged", async () => {
    const user = userEvent.setup();
    const register = acceptRegistration();
    renderSignup();
    await optionsLoaded();

    await fillCommonFields(user);
    await user.selectOptions(program(), "BS Computer Science");
    await finish(user);

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1));
    const payload = register.mock.calls[0][0];
    expect(payload).toEqual({
      email: "juan@cit.edu",
      first_name: "Juan",
      middle_initial: "S.",
      last_name: "Dela Cruz",
      password: "IrisDemo123!",
      confirm_password: "IrisDemo123!",
      role_name: "Student",
      course_id: 100,
    });
    expect(Object.keys(payload)).toEqual([
      "email", "first_name", "middle_initial", "last_name",
      "password", "confirm_password", "role_name", "course_id",
    ]);
  });

  it("sends an Adviser's registration unchanged", async () => {
    const user = userEvent.setup();
    const register = acceptRegistration();
    renderSignup();
    await optionsLoaded();

    await user.click(screen.getByRole("radio", { name: "Faculty / Adviser" }));
    await fillCommonFields(user);
    await user.selectOptions(screen.getByRole("combobox", { name: "Department" }), "Information Technology");
    await finish(user);

    await waitFor(() => expect(register).toHaveBeenCalledTimes(1));
    expect(register.mock.calls[0][0]).toEqual({
      email: "juan@cit.edu",
      first_name: "Juan",
      middle_initial: "S.",
      last_name: "Dela Cruz",
      password: "IrisDemo123!",
      confirm_password: "IrisDemo123!",
      role_name: "Adviser",
      college_id: 1,
      department_id: 11,
    });
  });

  it("keeps the fields in their order", async () => {
    renderSignup();
    await optionsLoaded();

    const inOrder = [
      screen.getByRole("radio", { name: "Student" }),
      screen.getByRole("textbox", { name: "First Name" }),
      screen.getByRole("textbox", { name: "Last Name" }),
      screen.getByRole("textbox", { name: "M.I." }),
      screen.getByRole("textbox", { name: "CIT-U Email" }),
      college(),
      program(),
      screen.getByLabelText("Password"),
      screen.getByLabelText("Confirm Password"),
      screen.getByRole("checkbox", { name: /I agree to the IRIS/ }),
      screen.getByRole("button", { name: "Register" }),
    ];
    for (let i = 1; i < inOrder.length; i++) {
      expect(inOrder[i - 1].compareDocumentPosition(inOrder[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("keeps the validation messages", async () => {
    const user = userEvent.setup();
    renderSignup();
    await optionsLoaded();

    await user.type(screen.getByRole("textbox", { name: "M.I." }), "S");
    await user.type(screen.getByRole("textbox", { name: "CIT-U Email" }), "not-an-email");
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
    await user.type(screen.getByLabelText("Confirm Password"), "IrisDemo123?");

    expect(screen.getByRole("textbox", { name: "M.I." })).toHaveAccessibleDescription("Missing (.).");
    expect(screen.getByRole("textbox", { name: "CIT-U Email" })).toHaveAccessibleDescription(
      "Enter a valid email address.",
    );
    expect(screen.getByLabelText("Confirm Password")).toHaveAccessibleDescription("Passwords do not match.");

    await user.click(screen.getByRole("radio", { name: "Faculty / Adviser" }));
    await user.click(screen.getByRole("checkbox", { name: /I agree to the IRIS/ }));
    await user.click(screen.getByRole("button", { name: "Register" }));
    expect(screen.getByRole("combobox", { name: "Department" })).toHaveAccessibleDescription(
      "Please select your department.",
    );
  });
});
