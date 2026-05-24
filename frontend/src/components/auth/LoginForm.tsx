import { useState } from "react";
import { Formik, Form, Field, ErrorMessage, type FormikHelpers, type FieldProps } from "formik";
import * as Yup from "yup";
import { useUIStore } from "@/store/ui.store";

export interface LoginFormValues {
  identifier: string;
  password: string;
}

const validationSchema = Yup.object({
  identifier: Yup.string()
    .trim()
    .required("Username or email is required.")
    .test(
      "identifier",
      "Enter a valid username or email address.",
      (value) => {
        if (!value) return false;
        if (value.includes("@")) {
          return Yup.string().email().isValidSync(value);
        }
        return value.length >= 2;
      }
    ),
  password: Yup.string().required("Password is required."),
});

const inputBase =
  "w-full rounded-lg px-4 py-3 text-[14px] bg-[#F3F3F3] outline-none transition-colors placeholder:text-gray-400 text-gray-900 border focus:bg-white";
const inputOk = "border-transparent focus:border-brand";
const inputErr = "border-brand bg-red-50/50 focus:border-brand";

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
  const inputState = showCredentialsError ? inputErr : inputOk;

  return (
    <Formik<LoginFormValues>
      initialValues={{ identifier: "", password: "" }}
      validationSchema={validationSchema}
      onSubmit={onSubmit}
    >
      {({ isSubmitting, errors, touched }) => (
        <Form className="flex flex-col gap-5" noValidate>
          <div>
            <label htmlFor="login-identifier" className="block text-[13px] font-semibold text-gray-900 mb-2">
              Username or Email
            </label>
            <Field name="identifier">
              {({ field }: FieldProps<string>) => (
                <input
                  {...field}
                  id="login-identifier"
                  type="text"
                  autoComplete="username"
                  placeholder="student ID or student@cit.edu"
                  disabled={disabled}
                  onChange={(e) => {
                    field.onChange(e);
                    onIdentifierChange?.(e.target.value);
                  }}
                  className={`${inputBase} ${inputState} ${errors.identifier && touched.identifier ? inputErr : ""}`}
                />
              )}
            </Field>
            <ErrorMessage name="identifier" component="p" className="text-[12px] text-red-600 mt-1.5" />
          </div>

          <div>
            <label htmlFor="login-password" className="block text-[13px] font-semibold text-gray-900 mb-2">
              Password
            </label>
            <div className="relative">
              <Field
                id="login-password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="••••••••"
                disabled={disabled}
                className={`${inputBase} pr-16 ${inputState} ${errors.password && touched.password ? inputErr : ""}`}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-[13px] font-semibold text-brand hover:underline"
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <ErrorMessage name="password" component="p" className="text-[12px] text-red-600 mt-1.5" />
          </div>

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

          <button
            type="submit"
            disabled={isSubmitting || disabled}
            className="w-full py-3.5 rounded-lg text-[15px] font-semibold text-white transition-colors bg-gold hover:bg-gold-dark disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            {isSubmitting ? "Signing in…" : "Sign In"}
          </button>
        </Form>
      )}
    </Formik>
  );
}
