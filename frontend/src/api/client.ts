import axios, { type InternalAxiosRequestConfig, type AxiosError } from "axios";
import { API_BASE } from "@/lib/constants";
import { redirectToLoginSessionExpired } from "@/lib/authSession";
import { useAuthStore } from "@/store/auth.store";

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = useAuthStore.getState().refreshToken;
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE}/auth/token/refresh/`, { refresh });
          localStorage.setItem("access_token", data.access);
          localStorage.setItem("refresh_token", data.refresh); 
          original.headers!.Authorization = `Bearer ${data.access}`;
          return apiClient(original);
        } catch {
          useAuthStore.getState().logout();
          redirectToLoginSessionExpired();
        }
      } else {
        useAuthStore.getState().logout();
        redirectToLoginSessionExpired();
      }
    }
    return Promise.reject(error);
  }
);
