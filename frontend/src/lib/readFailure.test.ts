import fs from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";

import {
  failureCause,
  failureMessage,
  OFFLINE_MESSAGE,
  readFailureKind,
  REFUSED_MESSAGE,
  SLOW_MESSAGE,
  UNREACHED_MESSAGE,
} from "./readFailure";

describe("readFailureKind", () => {
  it("calls a timeout interrupted", () => {
    expect(readFailureKind(new RequestTimeoutError(30_000))).toBe("interrupted");
  });

  it("answers 403 and 404 alike, so a hidden Record cannot be told from a missing id", () => {
    expect(readFailureKind({ response: { status: 404 } })).toBe("unavailable");
    expect(readFailureKind({ response: { status: 403 } })).toBe("unavailable");
  });

  it("calls everything else failed", () => {
    expect(readFailureKind({ response: { status: 500 } })).toBe("failed");
    expect(readFailureKind(new Error("Network Error"))).toBe("failed");
    expect(readFailureKind(null)).toBe("failed");
  });
});

describe("failureMessage (IR-1078)", () => {
  afterEach(() => vi.restoreAllMocks());

  const offline = () => vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

  it("tells an offline reader to check their connection", () => {
    offline();
    expect(failureMessage(new Error("Network Error"))).toBe(OFFLINE_MESSAGE);
    expect(failureMessage(new RequestTimeoutError(30_000))).toBe(OFFLINE_MESSAGE);
  });

  it("blames IRIS, not the reader's connection, for a timeout", () => {
    expect(failureMessage(new RequestTimeoutError(30_000))).toBe(SLOW_MESSAGE);
    expect(SLOW_MESSAGE).toBe("IRIS took too long to answer. Try again.");
  });

  it("blames IRIS for a 5xx, whatever text it carries", () => {
    expect(failureMessage({ response: { status: 500 } })).toBe(SLOW_MESSAGE);
    expect(failureMessage({ response: { status: 503, data: { detail: "internal text" } } })).toBe(SLOW_MESSAGE);
  });

  it("says IRIS could not be reached, not that it was slow, when nothing answered and the browser is online", () => {
    expect(failureMessage(new Error("Network Error"))).toBe(UNREACHED_MESSAGE);
    expect(failureMessage(null)).toBe(UNREACHED_MESSAGE);
    expect(failureMessage(null, { unreached: "Your request may not have arrived. Try again." }))
      .toBe("Your request may not have arrived. Try again.");
  });

  it("does not call a 5xx an offline reader's problem: an answer arrived", () => {
    offline();
    expect(failureMessage({ response: { status: 502 } })).toBe(SLOW_MESSAGE);
  });

  it("gives a 4xx the server's own reason, else the caller's words, else a neutral line", () => {
    expect(failureMessage({ response: { status: 400, data: { detail: "That title is taken." } } }))
      .toBe("That title is taken.");
    expect(failureMessage({ response: { status: 422 } }, { rejected: "Check the form." })).toBe("Check the form.");
    expect(failureMessage({ response: { status: 400 } })).toBe(REFUSED_MESSAGE);
  });

  it("keeps the wait a 429 names", () => {
    expect(failureMessage({ response: { status: 429, data: { retry_after: 30 } } }))
      .toBe("Too many requests — try again in about 30 seconds.");
  });

  it("puts the caller's lead in front of the cause", () => {
    expect(failureMessage(new RequestTimeoutError(30_000), { lead: "The notice didn't load." }))
      .toBe("The notice didn't load. IRIS took too long to answer. Try again.");
  });

  it("names the cause for callers that branch on it", () => {
    expect(failureCause({ response: { status: 404 } })).toBe("rejected");
    expect(failureCause({ response: { status: 500 } })).toBe("slow");
    expect(failureCause(new Error("Network Error"))).toBe("unreached");
    offline();
    expect(failureCause(undefined)).toBe("offline");
  });
});

describe("one place for the connection advice (IR-1078)", () => {
  it("leaves no screen with a hard-coded 'Check your connection'", () => {
    const root = path.resolve(__dirname, "..");
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)
          && path.relative(root, full).split(path.sep).join("/") !== "lib/readFailure.ts"
          && /check your connection/i.test(fs.readFileSync(full, "utf8"))) {
          offenders.push(path.relative(root, full));
        }
      }
    };
    walk(root);
    expect(offenders).toEqual([]);
  });
});
