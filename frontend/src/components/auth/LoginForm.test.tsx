/**
 * The sign-in form on its own (IR-916): validation, what it hands to its
 * caller, and the states the page puts it in. `LoginPage` owns the lock and the
 * server call; this owns the fields. Queries go through role and accessible
 * name.
 */
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "./LoginForm";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";

function setup(props: Partial<React.ComponentProps<typeof LoginForm>> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  const view = renderScreen(<LoginForm onSubmit={onSubmit} {...props} />);
  const email = () => screen.getByRole("textbox", { name: /email address/i });
  // A password field has no role, so it is found by its label.
  const password = () => screen.getByLabelText(/^password/i);
  const signIn = () => screen.getByRole("button", { name: /sign in|signing in/i });
  return { onSubmit, user, view, email, password, signIn };
}

describe("LoginForm", () => {
  it("offers an email field, a password field, Sign In and a way to recover a password", () => {
    const { email, password, signIn } = setup();

    expect(email()).toHaveValue("");
    expect(password()).toHaveValue("");
    expect(signIn()).toBeEnabled();
    expect(screen.getByRole("link", { name: "Forgot password?" })).toHaveAttribute("href", "/password/forgot");
  });

  it("hands the typed values to onSubmit", async () => {
    const { onSubmit, user, email, password, signIn } = setup();

    await user.type(email(), "kay@cit.edu");
    await user.type(password(), "hunter2");
    await user.click(signIn());

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toEqual({ identifier: "kay@cit.edu", password: "hunter2" });
  });

  it("submits from the keyboard", async () => {
    const { onSubmit, user, email, password } = setup();

    await user.type(email(), "kay@cit.edu");
    await user.type(password(), "hunter2{Enter}");

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  describe("validation", () => {
    it("says both fields are required and does not submit an empty form", async () => {
      const { onSubmit, user, signIn } = setup();

      await user.click(signIn());

      expect(await screen.findByText("Email is required.")).toBeInTheDocument();
      expect(screen.getByText("Password is required.")).toBeInTheDocument();
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("rejects something that is not an email address", async () => {
      const { onSubmit, user, email, password, signIn } = setup();

      await user.type(email(), "not-an-email");
      await user.type(password(), "pw");
      await user.click(signIn());

      expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("joins the message to its field, so a screen reader reads it with the field", async () => {
      const { user, email, signIn } = setup();

      await user.click(signIn());

      await waitFor(() => expect(email()).toBeInvalid());
      expect(email()).toHaveAccessibleDescription("Email is required.");
    });

    it("shows an error only after the field was touched, not on first render", () => {
      setup();

      expect(screen.queryByText("Email is required.")).not.toBeInTheDocument();
      expect(screen.queryByText("Password is required.")).not.toBeInTheDocument();
    });

    it("does not block an address with surrounding spaces, which the schema trims when validating", async () => {
      const { onSubmit, user, email, password, signIn } = setup();

      await user.type(email(), "  kay@cit.edu  ");
      await user.type(password(), "pw");
      await user.click(signIn());

      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    });
  });

  describe("the password toggle", () => {
    it("starts hidden and flips to text and back", async () => {
      const { user, password } = setup();
      expect(password()).toHaveAttribute("type", "password");

      await user.click(screen.getByRole("button", { name: "Show password" }));
      expect(password()).toHaveAttribute("type", "text");

      await user.click(screen.getByRole("button", { name: "Hide password" }));
      expect(password()).toHaveAttribute("type", "password");
    });

    it("does not submit the form", async () => {
      const { onSubmit, user } = setup();

      await user.click(screen.getByRole("button", { name: "Show password" }));

      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe("the page's states", () => {
    it("disables both fields and Sign In when the page says the account is locked", () => {
      const { email, password, signIn } = setup({ disabled: true });

      expect(email()).toBeDisabled();
      expect(password()).toBeDisabled();
      expect(signIn()).toBeDisabled();
    });

    it("marks both fields invalid, without repeating the sentence, after a rejected sign-in", () => {
      const { email, password } = setup({ showCredentialsError: true });

      expect(email()).toBeInvalid();
      expect(password()).toBeInvalid();
      expect(screen.queryByText(/required|valid email/i)).not.toBeInTheDocument();
    });

    it("tells the page what is being typed in the email field, for its lock check", async () => {
      const onIdentifierChange = vi.fn();
      const { user, email } = setup({ onIdentifierChange });

      await user.type(email(), "ab");

      expect(onIdentifierChange).toHaveBeenLastCalledWith("ab");
    });

    it("shows Signing in… and refuses a second submit while the call is out", async () => {
      let finish: () => void = () => {};
      const onSubmit = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
      const { user, email, password } = setup({ onSubmit });

      await user.type(email(), "kay@cit.edu");
      await user.type(password(), "pw");
      await user.click(screen.getByRole("button", { name: "Sign In" }));

      const busy = await screen.findByRole("button", { name: /signing in/i });
      await user.click(busy);
      expect(onSubmit).toHaveBeenCalledTimes(1);

      finish();
      expect(await screen.findByRole("button", { name: "Sign In" })).toBeEnabled();
    });

    it("hands its submit button to the page, which focuses it after an unlock", () => {
      const ref = { current: null as HTMLButtonElement | null };
      const { signIn } = setup({ submitRef: ref });

      expect(ref.current).toBe(signIn());
    });
  });

  it("has no blocking accessibility violation", async () => {
    const { view } = setup();

    await expectNoBlockingA11yViolations(view.container);
  });
});
