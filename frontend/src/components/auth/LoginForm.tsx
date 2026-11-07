import { useState, type Ref } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button, Input } from "@/components/ui";

export interface LoginFormValues {
  identifier: string;
  password: string;
}

const loginSchema = z.object({
  identifier: z
    .string()
    .trim()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

interface LoginFormProps {
  /** Resolves when the sign-in attempt is over; the form stays busy until then. */
  onSubmit: (values: LoginFormValues) => Promise<void>;
  disabled?: boolean;
  submitRef?: Ref<HTMLButtonElement>;
  showCredentialsError?: boolean;
  onIdentifierChange?: (identifier: string) => void;
}

export function LoginForm({
  onSubmit,
  disabled = false,
  showCredentialsError = false,
  onIdentifierChange,
  submitRef,
}: LoginFormProps) {
  const [showPassword, setShowPassword] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { identifier: "", password: "" },
    // An error shows once its field was left, and is re-checked as it is typed;
    // submitting checks both at once. An untouched field shows none.
    mode: "onTouched",
  });

  const identifier = register("identifier");

  return (
    <form className="flex flex-col gap-5" noValidate onSubmit={handleSubmit(onSubmit)}>
      {/* Field names and their order are unchanged: renaming them would
          break autofill and anything downstream keyed to them. */}
      <Input
        {...identifier}
        id="login-identifier"
        label="Email Address"
        size="lg"
        type="email"
        autoComplete="email"
        placeholder="name@university.edu"
        disabled={disabled}
        error={errors.identifier?.message}
        // A rejected sign-in is explained by the alert above the form,
        // so the field is marked invalid without repeating the sentence.
        aria-invalid={showCredentialsError || undefined}
        onChange={(e) => {
          void identifier.onChange(e);
          onIdentifierChange?.(e.target.value);
        }}
      />

      <Input
        {...register("password")}
        id="login-password"
        label="Password"
        size="lg"
        type={showPassword ? "text" : "password"}
        autoComplete="current-password"
        placeholder="••••••••"
        disabled={disabled}
        error={errors.password?.message}
        aria-invalid={showCredentialsError || undefined}
        trailing={
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            // The visible word is the start of the accessible name, so
            // "click Show" still matches what a voice user says (2.5.3).
            aria-label={showPassword ? "Hide password" : "Show password"}
            // px/min-w give the 44px target 2.5.5 asks for; the text
            // alone would be about 34x18.
            className="flex items-center justify-center min-h-11 min-w-11 px-1
              text-[14px] font-semibold text-brand hover:underline"
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        }
      />

      {/* Self-service recovery (IR-642, ADR-045 §7). IR-536's disclosure
          naming RDCO answered a dead end; there is a journey now, and RDCO
          stays as support guidance in its email and confirmation. */}
      <div className="-mt-1 flex justify-end">
        <Link
          to="/password/forgot"
          // The same 44px target as the Show toggle above (2.5.5).
          className="inline-flex items-center min-h-11 px-1 text-sm font-semibold
            text-brand hover:underline"
        >
          Forgot password?
        </Link>
      </div>

      {/* `size="full"` carries the full width and the larger step. Passing
          those as a className instead would collide with the primitive's
          own sizing -- clsx keeps both and stylesheet order decides. */}
      <Button ref={submitRef} type="submit" variant="primary" size="full" loading={isSubmitting} disabled={disabled}>
        {isSubmitting ? "Signing in…" : "Sign In"}
      </Button>
    </form>
  );
}
