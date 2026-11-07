import { apiClient } from "./client";
import type {
  LoginPayload, LoginResponse, RegisterPayload, ChangePasswordPayload, User,
  PasswordResetConfirmPayload, RecoveryAcknowledgement,
} from "@/types/auth";

export const authApi = {
  login:          (data: LoginPayload)          => apiClient.post<LoginResponse>("/auth/login/", data),
  register:       (data: RegisterPayload)       => apiClient.post("/auth/register/", data),
  logout:         (refresh: string)             => apiClient.post("/auth/logout/", { refresh }),
  refreshToken:   (refresh: string)             => apiClient.post("/auth/token/refresh/", { refresh }),
  changePassword: (data: ChangePasswordPayload) => apiClient.post("/auth/password/change/", data),
  // ADR-045 (IR-642). Anonymous: neither sends nor needs a session.
  requestPasswordReset: (email: string) =>
    apiClient.post<RecoveryAcknowledgement>("/auth/password/reset/request/", { email }),
  confirmPasswordReset: (data: PasswordResetConfirmPayload) =>
    apiClient.post<RecoveryAcknowledgement>("/auth/password/reset/confirm/", data),
  // ADR-045 (IR-643). The same contract for verifying an email address.
  resendVerification: (email: string) =>
    apiClient.post<RecoveryAcknowledgement>("/auth/verification/resend/", { email }),
  confirmVerification: (token: string) =>
    apiClient.post<RecoveryAcknowledgement>("/auth/verification/confirm/", { token }),
  me:             ()                            => apiClient.get<User>("/users/me/"),
  updateMe:       (data: Partial<User>)         => apiClient.patch<User>("/users/me/", data),
};
