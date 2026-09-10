import { useState } from "react";
import { Formik, Form, Field, type FormikHelpers, type FieldProps } from "formik";
import * as Yup from "yup";
import { useUIStore } from "@/store/ui.store";
import { Button, Input } from "@/components/ui";

export interface LoginFormValues {
  identifier: string;
  password: string;
}

const validationSchema = Yup.object({
  identifier: Yup.string()
    .trim()
    .required("Email is required.")
    .email("Enter a valid email address."),
  password: Yup.string().required("Password is required."),
});

interface LoginFormProps {
  onSubmit: (
    values: LoginFormValues,
    helpers: FormikHelpers<LoginFormValues>
  ) => Promise<void>;
  disabled?: boolean;
  showCredentialsError?: boolean;
  onIdentifierChange?: (identifier: string) => void;
}

export function LoginForm({
  onSubmit,
  disabled = false,
  showCredentialsError = false,
  onIdentifierChange,
}: LoginFormProps) {
  const { addToast } = useUIStore();
  const [showPassword, setShowPassword] = useState(false);

  return (
    <Formik<LoginFormValues>
      initialValues={{ identifier: "", password: "" }}
      validationSchema={validationSchema}
      onSubmit={onSubmit}
    >
      {({ isSubmitting, errors, touched }) => {
        // Formik reports an error for an untouched field too; only a touched
        // one should show it, and both fields want the same rule.
        const shownError = (name: keyof LoginFormValues) =>
          touched[name] && errors[name] ? errors[name] : undefined;

        return (
        <Form className="flex flex-col gap-5" noValidate>
          {/* Field names and their order are unchanged: renaming them would
              break autofill and anything downstream keyed to them. */}
          <Field name="identifier">
            {({ field }: FieldProps<string>) => (
              <Input
                {...field}
                id="login-identifier"
                label="Email Address"
                size="lg"
                type="email"
                autoComplete="email"
                placeholder="iris-student@cit.edu"
                disabled={disabled}
                error={shownError("identifier")}
                // A rejected sign-in is explained by the alert above the form,
                // so the field is marked invalid without repeating the sentence.
                aria-invalid={showCredentialsError || undefined}
                onChange={(e) => {
                  field.onChange(e);
                  onIdentifierChange?.(e.target.value);
                }}
              />
            )}
          </Field>

          <Field name="password">
            {({ field }: FieldProps<string>) => (
              <Input
                {...field}
                id="login-password"
                label="Password"
                size="lg"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                disabled={disabled}
                error={shownError("password")}
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
                      text-[13px] font-semibold text-brand hover:underline"
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                }
              />
            )}
          </Field>

          <div className="flex justify-end -mt-1">
            <button
              type="button"
              className="text-[13px] font-semibold text-brand hover:underline"
              onClick={() =>
                addToast({
                  type: "info",
                  message: "Password reset is not available yet. Contact your administrator.",
                })
              }
            >
              Forgot password?
            </button>
          </div>

          {/* `size="full"` carries the full width and the larger step. Passing
              those as a className instead would collide with the primitive's
              own sizing -- clsx keeps both and stylesheet order decides. */}
          <Button type="submit" variant="primary" size="full" loading={isSubmitting} disabled={disabled}>
            {isSubmitting ? "Signing in…" : "Sign In"}
          </Button>
        </Form>
        );
      }}
    </Formik>
  );
}
