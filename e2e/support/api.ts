// The application's own HTTP API, called the way the frontend calls it:
// through nginx, with a JWT from /auth/login/. Journeys use it to reach the
// step under test quickly; the step under test itself is checked in the
// browser where an acceptance criterion names a screen.
import { expect, request as playwrightRequest, type APIRequestContext, type APIResponse, type Page } from "@playwright/test";
import { ACCOUNTS, PASSWORD, type AccountName } from "./accounts";

const BASE = process.env.E2E_BASE_URL ?? `http://localhost:${process.env.E2E_PORT ?? "8090"}`;
const HEADERS = { "X-Forwarded-Proto": "https" };
export const API = "/api/v1";

export type Session = { access: string; refresh: string; user: Record<string, unknown> };

export async function anonymous(): Promise<APIRequestContext> {
  return playwrightRequest.newContext({ baseURL: BASE, extraHTTPHeaders: HEADERS });
}

export async function login(email: string, password = PASSWORD): Promise<Session> {
  const ctx = await anonymous();
  const res = await ctx.post(`${API}/auth/login/`, { data: { email, password } });
  const body = await res.json().catch(() => ({}));
  await ctx.dispose();
  expect(res.status(), `sign in as ${email}: ${JSON.stringify(body)}`).toBe(200);
  return body as Session;
}

/** An API client signed in as one of the seeded accounts, or any email. */
export async function as(who: AccountName | string, password = PASSWORD): Promise<Client> {
  const email = who in ACCOUNTS ? ACCOUNTS[who as AccountName] : who;
  const session = await login(email, password);
  const ctx = await playwrightRequest.newContext({
    baseURL: BASE,
    extraHTTPHeaders: { ...HEADERS, Authorization: `Bearer ${session.access}` },
  });
  return new Client(ctx, session, email);
}

export class Client {
  constructor(readonly ctx: APIRequestContext, readonly session: Session, readonly email: string) {}

  get userId(): number {
    return this.session.user.id as number;
  }

  get(path: string, params?: Record<string, string | number>) {
    return this.ctx.get(`${API}${path}`, { params });
  }
  post(path: string, data?: unknown) {
    return this.ctx.post(`${API}${path}`, { data: data ?? {} });
  }
  patch(path: string, data: unknown) {
    return this.ctx.patch(`${API}${path}`, { data });
  }
  delete(path: string) {
    return this.ctx.delete(`${API}${path}`);
  }
  multipart(method: "post" | "patch", path: string, multipart: Record<string, string | { name: string; mimeType: string; buffer: Buffer }>) {
    return this.ctx[method](`${API}${path}`, { multipart });
  }

  /** GET and assert 200, returning the body. */
  async json<T = any>(path: string, params?: Record<string, string | number>): Promise<T> {
    return ok<T>(await this.get(path, params), `GET ${path} as ${this.email}`);
  }
  /** POST and assert 2xx, returning the body. */
  async act<T = any>(path: string, data?: unknown): Promise<T> {
    return ok<T>(await this.post(path, data), `POST ${path} as ${this.email}`);
  }

  dispose() {
    return this.ctx.dispose();
  }
}

export async function ok<T = any>(res: APIResponse, what: string): Promise<T> {
  const text = await res.text();
  expect(res.ok(), `${what} -> ${res.status()} ${text.slice(0, 500)}`).toBeTruthy();
  return (text ? JSON.parse(text) : null) as T;
}

/**
 * Open the app in the browser already signed in as `who`. The frontend keeps
 * only the refresh token, in sessionStorage, and hydrates from it on load
 * (frontend/src/lib/authStorage.ts), so that is all that is placed. Signing in
 * through the form itself is the account-lifecycle journey's subject.
 */
export async function signInBrowser(page: Page, who: AccountName | string, path = "/", password = PASSWORD): Promise<Session> {
  const email = who in ACCOUNTS ? ACCOUNTS[who as AccountName] : who;
  const session = await login(email, password);
  await page.addInitScript((refresh) => {
    window.sessionStorage.setItem("iris_refresh_token", refresh);
  }, session.refresh);
  await page.goto(path);
  return session;
}
