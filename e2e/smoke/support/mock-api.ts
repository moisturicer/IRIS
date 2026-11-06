// The smoke tier's network (IR-904). Every request to /api/ is answered here,
// never by a server: there is none behind the built frontend.
//
// Strict on purpose. A request no test claimed is answered 501 and RECORDED,
// and the fixture fails the test afterwards. Without that, a page that quietly
// started calling a new endpoint would get an error it swallows, and the smoke
// set would stay green while exercising something else.
import { test as base, expect, type Route } from "@playwright/test";

export type Handler = (route: Route, request: ReturnType<Route["request"]>) => unknown | Promise<unknown>;

export interface MockApi {
  /** Answer `METHOD /api/v1<path>` with a JSON body (or a function that fulfils the route itself). */
  on(method: string, path: string, reply: unknown | Handler, status?: number): void;
  /** Every request seen, in order, as "METHOD /path". */
  readonly seen: string[];
}

const API_PREFIX = "/api/v1";

export const test = base.extend<{ api: MockApi }>({
  api: async ({ page }, use) => {
    const handlers = new Map<string, { reply: unknown | Handler; status: number }>();
    const seen: string[] = [];
    const unmocked: string[] = [];

    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const key = `${request.method()} ${url.pathname.replace(API_PREFIX, "")}`;
      seen.push(key);
      const entry = handlers.get(key);
      if (!entry) {
        unmocked.push(key);
        await route.fulfill({ status: 501, json: { detail: `smoke: ${key} is not mocked` } });
        return;
      }
      if (typeof entry.reply === "function") {
        await (entry.reply as Handler)(route, request);
        return;
      }
      await route.fulfill({ status: entry.status, json: entry.reply });
    });

    await use({
      on: (method, path, reply, status = 200) => {
        handlers.set(`${method.toUpperCase()} ${path}`, { reply, status });
      },
      seen,
    });

    expect(unmocked, "requests to /api that no smoke test mocked").toEqual([]);
  },
});

export { expect };
