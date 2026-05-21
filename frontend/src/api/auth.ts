import { apiClient } from "./client";
import type { LoginPayload, LoginResponse, RegisterPayload, ChangePasswordPayload, User } from "@/types/auth";

export const authApi = {
  login:          (data: LoginPayload)          => apiClient.post<LoginResponse>("/auth/login/", data),
  register:       (data: RegisterPayload)       => apiClient.post("/auth/register/", data),
  activate:       (uidb64: string, token: string) => apiClient.get(`/auth/activate/${uidb64}/${token}/`),
  logout:         (refresh: string)             => apiClient.post("/auth/logout/", { refresh }),
  refreshToken:   (refresh: string)             => apiClient.post("/auth/token/refresh/", { refresh }),
  changePassword: (data: ChangePasswordPayload) => apiClient.post("/auth/password/change/", data),
  me:             ()                            => apiClient.get<User>("/users/me/"),
  updateMe:       (data: Partial<User>)         => apiClient.patch<User>("/users/me/", data),
};
