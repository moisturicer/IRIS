/**
 * The auth endpoints: method, path, payload and what a refusal looks like
 * (IR-916). `client.test.ts` covers the refresh interceptor; this covers the
 * calls a screen makes.
 */
import { describe, expect, it, vi } from "vitest";

import { authApi } from "./auth";

vi.mock("@/lib/authSession", () => ({ redirectToLoginSessionExpired: vi.fn() }));
import { installApiStub } from "@/test/apiAdapter";

const stub = installApiStub();

describe("authApi", () => {
  it("login posts the credentials to /auth/login/ and returns the response body", async () => {
    stub.reply({ data: { access: "a", refresh: "r", user: { id: 1 } } });

    const res = await authApi.login({ email: "a@cit.edu", password: "pw" });

    expect(stub.only()).toMatchObject({
      method: "post", url: "/auth/login/", body: { email: "a@cit.edu", password: "pw" },
    });
    expect(res.data).toMatchObject({ access: "a", refresh: "r" });
  });

  it("register posts the form to /auth/register/", async () => {
    const payload = {
      email: "a@cit.edu", first_name: "A", last_name: "B", password: "pw", confirm_password: "pw",
      consent_given: true as const,
    };

    await authApi.register(payload);

    expect(stub.only()).toMatchObject({ method: "post", url: "/auth/register/", body: payload });
  });

  it("activate posts the link's two parts in a body, never in the URL (IR-928)", async () => {
    await authApi.activate("Mjc", "abc-123");

    expect(stub.only()).toMatchObject({
      method: "post", url: "/auth/activate/", body: { uid: "Mjc", token: "abc-123" },
    });
  });

  it("logout sends the refresh token to /auth/logout/ so the server can blacklist it", async () => {
    await authApi.logout("refresh-1");

    expect(stub.only()).toMatchObject({
      method: "post", url: "/auth/logout/", body: { refresh: "refresh-1" },
    });
  });

  it("refreshToken sends only the refresh token", async () => {
    await authApi.refreshToken("refresh-1");

    expect(stub.only()).toMatchObject({
      method: "post", url: "/auth/token/refresh/", body: { refresh: "refresh-1" },
    });
  });

  it("changePassword posts to /auth/password/change/", async () => {
    const payload = { old_password: "a", new_password: "b" };

    await authApi.changePassword(payload);

    expect(stub.only()).toMatchObject({
      method: "post", url: "/auth/password/change/", body: payload,
    });
  });

  it("requestPasswordReset wraps the address as { email }", async () => {
    await authApi.requestPasswordReset("a@cit.edu");

    expect(stub.only()).toMatchObject({
      method: "post", url: "/auth/password/reset/request/", body: { email: "a@cit.edu" },
    });
  });

  it("confirmPasswordReset posts the whole payload to /auth/password/reset/confirm/", async () => {
    const payload = { token: "t", new_password: "pw", confirm_password: "pw" };

    await authApi.confirmPasswordReset(payload);

    expect(stub.only()).toMatchObject({
      method: "post", url: "/auth/password/reset/confirm/", body: payload,
    });
  });

  it("me gets /users/me/", async () => {
    stub.reply({ data: { id: 7, email: "a@cit.edu" } });

    const res = await authApi.me();

    expect(stub.only()).toMatchObject({ method: "get", url: "/users/me/" });
    expect(res.data).toEqual({ id: 7, email: "a@cit.edu" });
  });

  it("updateMe patches only what it was given", async () => {
    await authApi.updateMe({ first_name: "Kay" });

    expect(stub.only()).toMatchObject({
      method: "patch", url: "/users/me/", body: { first_name: "Kay" },
    });
  });

  it("sends no Authorization header when nobody is signed in", async () => {
    await authApi.requestPasswordReset("a@cit.edu");

    expect(stub.only().headers).not.toHaveProperty("Authorization");
  });

  describe("a refusal", () => {
    it("rejects a wrong password, a 401 as the server sends it, with its body intact", async () => {
      // The 401 passes through the refresh interceptor, which with no session to
      // refresh ends it and rejects with the original error. The redirect is
      // stubbed: on the real /login page it is a no-op.
      stub.reply({ status: 401, data: { detail: "Invalid credentials." } });

      await expect(authApi.login({ email: "a@cit.edu", password: "bad" }))
        .rejects.toMatchObject({ response: { status: 401, data: { detail: "Invalid credentials." } } });
    });

    it("keeps the lock reason a locked account is refused with", async () => {
      stub.reply({ status: 403, data: { detail: "Account locked.", code: "account_locked" } });

      await expect(authApi.login({ email: "a@cit.edu", password: "pw" }))
        .rejects.toMatchObject({ response: { status: 403, data: { code: "account_locked" } } });
    });

    it("rejects a failed activation link", async () => {
      stub.reply({ status: 400, data: { detail: "Link expired." } });

      await expect(authApi.activate("x", "y")).rejects.toMatchObject({ response: { status: 400 } });
    });

    it("rejects a server error with its status", async () => {
      stub.reply({ status: 500 });

      await expect(authApi.me()).rejects.toMatchObject({ response: { status: 500 } });
    });
  });
});
