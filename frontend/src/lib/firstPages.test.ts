import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/store/auth.store";
import {
  firstPageSession,
  forgetFirstPages,
  knownFirstPage,
  rememberFirstPage,
  rememberNoFirstPage,
} from "./firstPages";

const createObjectURL = vi.fn((_: Blob) => "blob:page");
const revokeObjectURL = vi.fn();
const page = new Blob(["webp"], { type: "image/webp" });
const nextSession = () => useAuthStore.setState((s) => ({ sessionEpoch: s.sessionEpoch + 1 }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  forgetFirstPages();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("first-page images for the session (IR-1241)", () => {
  it("keeps one object URL per record", () => {
    const session = firstPageSession();

    expect(rememberFirstPage(5, page, session)).toBe("blob:page");
    expect(rememberFirstPage(5, page, session)).toBe("blob:page");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(knownFirstPage(5)).toBe("blob:page");
  });

  it("knows the difference between none and never asked", () => {
    rememberNoFirstPage(7, firstPageSession());

    expect(knownFirstPage(7)).toBeNull();
    expect(knownFirstPage(8)).toBeUndefined();
  });

  it("drops an answer to a read started in the previous session", () => {
    const session = firstPageSession();
    nextSession();

    expect(rememberFirstPage(5, page, session)).toBeUndefined();
    rememberNoFirstPage(6, session);
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(knownFirstPage(5)).toBeUndefined();
    expect(knownFirstPage(6)).toBeUndefined();
  });

  it("empties itself and revokes every URL on sign-out", () => {
    rememberFirstPage(5, page, firstPageSession());
    rememberNoFirstPage(6, firstPageSession());

    useAuthStore.getState().logout();

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:page");
    expect(knownFirstPage(5)).toBeUndefined();
    expect(knownFirstPage(6)).toBeUndefined();
  });
});
