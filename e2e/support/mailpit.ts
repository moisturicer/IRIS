// Mailpit's HTTP API (docker-compose.e2e.yml). Verification and recovery
// mail stays inside the stack; the run reads it here.
import { expect, request as playwrightRequest } from "@playwright/test";

const MAIL = process.env.E2E_MAIL_URL ?? `http://localhost:${process.env.E2E_MAIL_PORT ?? "8026"}`;

type Summary = { ID: string; Subject: string; To: { Address: string }[]; Created: string };

async function mailApi() {
  return playwrightRequest.newContext({ baseURL: MAIL });
}

/** Wait for the newest message to `to` whose subject matches, and return its text body. */
export async function waitForMail(to: string, subject: RegExp, timeoutMs = 60_000): Promise<{ subject: string; text: string; html: string }> {
  const ctx = await mailApi();
  try {
    let found: Summary | undefined;
    await expect
      .poll(async () => {
        const res = await ctx.get("/api/v1/search", { params: { query: `to:"${to}"`, limit: 50 } });
        const body = (await res.json()) as { messages: Summary[] };
        found = body.messages.find((m) => subject.test(m.Subject));
        return Boolean(found);
      }, { timeout: timeoutMs, message: `mail to ${to} matching ${subject}` })
      .toBe(true);
    const res = await ctx.get(`/api/v1/message/${found!.ID}`);
    const msg = (await res.json()) as { Subject: string; Text: string; HTML: string };
    return { subject: msg.Subject, text: msg.Text, html: msg.HTML };
  } finally {
    await ctx.dispose();
  }
}

/**
 * The path of the first link in `body` on the configured FRONTEND_URL origin.
 * FRONTEND_URL must be https in production; nothing here terminates TLS, so
 * the run follows the path on its own base URL (e2e/README.md, Limitations).
 */
export function linkPath(body: string, pathPrefix: string): string {
  const match = body.match(new RegExp(`https://[^\\s"'<>]+(${pathPrefix.replace(/\//g, "\\/")}[^\\s"'<>]*)`));
  expect(match, `a ${pathPrefix} link in the message`).not.toBeNull();
  return match![1];
}
