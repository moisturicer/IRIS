// Opening a catalogued screen the way every smoke spec that scans one needs it
// (IR-908): sign in as its role, mock its API, draw it, and wait until it is
// still enough to read. Shared by axe-routes.spec.ts and axe-states.spec.ts so
// the two cannot drift on what "drawn and settled" means.
import { expect, type Page } from "@playwright/test";
import type { MockApi } from "./mock-api";
import { signedIn } from "./fixtures";
import type { Screen } from "./screens";

/** A request that is never answered: the screen stays in its loading state, or, with `timeOut`, its interrupted one. */
export const hang = () => new Promise<void>(() => undefined);

/**
 * The client gives a read 30 s before it shows "This took too long" (ADR-061),
 * and the browser enforces that on the XMLHttpRequest itself, so a fake clock
 * cannot move it. This caps the `timeout` any request asks for at 300 ms, so a
 * request the test never answers times out the way a real one would, with the
 * same error the client sorts as "interrupted".
 */
export async function makeReadsTimeOut(page: Page, only?: string) {
  await page.addInitScript(capReadTimeouts, only);
}

/**
 * The same cap for a page that is already open: only reads that start AFTER
 * this call time out early. For a screen whose later read (Load more) is the
 * one under test, so its opening reads are not cut short on a slow machine.
 */
export async function makeLaterReadsTimeOut(page: Page, only?: string) {
  await page.evaluate(capReadTimeouts, only);
}

/**
 * Runs in the page, so it must stand alone. With `only`, a path such as
 * "/records/101/", just the requests whose address ENDS with it are capped: on
 * a slow machine an unrelated read on the same screen must not time out too,
 * or the screen shows two failures and the test is measuring the wrong one.
 */
function capReadTimeouts(only?: string) {
  const own = Object.getOwnPropertyDescriptor(XMLHttpRequest.prototype, "timeout");
  if (!own?.set || !own.get) return;
  const set = own.set;
  const open = XMLHttpRequest.prototype.open as (...args: unknown[]) => void;
  const targets = new WeakMap<XMLHttpRequest, boolean>();
  XMLHttpRequest.prototype.open = function (this: XMLHttpRequest, ...args: unknown[]) {
    if (only) {
      let path = "";
      try { path = new URL(String(args[1]), location.href).pathname; } catch { /* not a URL: not capped */ }
      targets.set(this, path.endsWith(only));
    }
    return open.apply(this, args);
  } as typeof XMLHttpRequest.prototype.open;
  Object.defineProperty(XMLHttpRequest.prototype, "timeout", {
    configurable: true,
    get: own.get,
    set(this: XMLHttpRequest, value: number) {
      const capped = !only || targets.get(this) === true;
      set.call(this, value && capped ? Math.min(value, 300) : value);
    },
  });
}

/**
 * Colour contrast is read from the colours on screen at that instant, so a fade
 * or slide still running reads as the wrong colour (IR-934 met the same with the
 * shell's margin transition). Finite animations are awaited, for 3 s at most; an
 * endless one (a spinner, a skeleton pulse) must not hang the scan.
 */
export async function settle(page: Page) {
  await page.evaluate(async () => {
    const ended = Promise.all(
      document.getAnimations()
        .filter((a) => a.effect?.getTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    );
    await Promise.race([ended, new Promise((resolve) => setTimeout(resolve, 3000))]);
  });
}

export interface OpenOptions {
  /** Replaces or adds mocks after the screen's own, to put it in a state. */
  override?: (api: MockApi) => void;
  /**
   * Reads the test never answers time out (see `makeReadsTimeOut`). `{ only }` limits
   * that to the read whose path ends with it, so no other read on the screen can time out.
   */
  timeOut?: boolean | { only: string };
}

/** Signs in, mocks and opens the screen. Does not wait for the network to go quiet: a state may be waiting on a request on purpose. */
export async function openScreen(page: Page, api: MockApi, screen: Screen, options: OpenOptions = {}) {
  if (options.timeOut) await makeReadsTimeOut(page, options.timeOut === true ? undefined : options.timeOut.only);
  if (screen.role) await signedIn(page, api, screen.role);
  screen.mocks?.(api);
  options.override?.(api);
  await page.goto(screen.path);
}

/** A screen that crashed into the error boundary can be accessible; it is not the screen under test. */
export async function expectNotCrashed(page: Page) {
  await expect(page.getByRole("heading", { name: "Something went wrong" })).toHaveCount(0);
}
