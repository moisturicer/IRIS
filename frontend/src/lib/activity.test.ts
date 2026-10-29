/**
 * The interface's half of the inactivity rule (IR-166, NFR-S2).
 *
 * The server decides when a session is idle; this module tells it how long the
 * user has been, and signs the interface out on the same figure so an
 * unattended screen stops showing what it showed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  HEARTBEAT_MS,
  IDLE_HEADER,
  IDLE_TIMEOUT_MS,
  __resetActivity,
  idleSeconds,
  markReported,
  startHeartbeat,
  startIdleWatch,
  trackActivity,
} from "./activity";

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-29T08:00:00Z"));
  __resetActivity();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("idleSeconds", () => {
  it("is zero right after load", () => {
    expect(idleSeconds()).toBe(0);
  });

  it("counts whole seconds since the last interaction", () => {
    vi.advanceTimersByTime(90_500);
    expect(idleSeconds()).toBe(90);
  });

  it.each(["pointerdown", "keydown", "wheel", "touchstart"])("is reset by %s", (type) => {
    const stop = trackActivity(window);
    vi.advanceTimersByTime(600_000);
    window.dispatchEvent(new Event(type));
    expect(idleSeconds()).toBe(0);
    stop();
  });

  it("is not reset by a request, a timer or a re-render -- only by the user", () => {
    const stop = trackActivity(window);
    vi.advanceTimersByTime(600_000);
    window.dispatchEvent(new Event("scroll")); // a page can scroll itself
    window.dispatchEvent(new Event("focus")); // so can a tab switch with no input
    expect(idleSeconds()).toBe(600);
    stop();
  });

  it("stops counting events once tracking stops", () => {
    const stop = trackActivity(window);
    stop();
    vi.advanceTimersByTime(60_000);
    window.dispatchEvent(new Event("keydown"));
    expect(idleSeconds()).toBe(60);
  });
});

describe("the header", () => {
  it("is the one the server reads", () => {
    // Django exposes it as META["HTTP_X_IRIS_IDLE_SECONDS"].
    expect(IDLE_HEADER).toBe("X-IRIS-Idle-Seconds");
  });

  it("agrees with the server's 30-minute default", () => {
    expect(IDLE_TIMEOUT_MS).toBe(30 * 60 * 1000);
  });
});

describe("startHeartbeat", () => {
  // The server judges idleness from the activity it last heard about, so a
  // user working on a page that sends nothing must still be heard from.
  it("reports input the server has not heard about", () => {
    const ping = vi.fn();
    const stop = trackActivity(window);
    const beat = startHeartbeat(ping);
    vi.advanceTimersByTime(60_000);
    window.dispatchEvent(new Event("wheel"));
    vi.advanceTimersByTime(HEARTBEAT_MS);
    expect(ping).toHaveBeenCalledTimes(1);
    beat();
    stop();
  });

  it("sends nothing when nobody has touched the page", () => {
    const ping = vi.fn();
    const beat = startHeartbeat(ping);
    vi.advanceTimersByTime(HEARTBEAT_MS * 6);
    expect(ping).not.toHaveBeenCalled();
    beat();
  });

  it("sends nothing when a request already carried the input", () => {
    const ping = vi.fn();
    const stop = trackActivity(window);
    const beat = startHeartbeat(ping);
    window.dispatchEvent(new Event("keydown"));
    vi.advanceTimersByTime(1_000);
    markReported(); // the interceptor does this on every request
    vi.advanceTimersByTime(HEARTBEAT_MS);
    expect(ping).not.toHaveBeenCalled();
    beat();
    stop();
  });

  it("beats well inside the timeout", () => {
    expect(HEARTBEAT_MS * 4).toBeLessThan(IDLE_TIMEOUT_MS);
  });
});

describe("startIdleWatch", () => {
  it("signs out once the user has been idle for the timeout", () => {
    const onIdle = vi.fn();
    const stop = startIdleWatch(onIdle);
    vi.advanceTimersByTime(IDLE_TIMEOUT_MS - 60_000);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(90_000);
    expect(onIdle).toHaveBeenCalledTimes(1);
    stop();
  });

  it("does not sign out a user who keeps working", () => {
    const onIdle = vi.fn();
    const stop = trackActivity(window);
    const unwatch = startIdleWatch(onIdle);
    for (let minute = 0; minute < 8 * 60; minute += 20) {
      vi.advanceTimersByTime(20 * 60_000);
      window.dispatchEvent(new Event("keydown"));
    }
    expect(onIdle).not.toHaveBeenCalled();
    unwatch();
    stop();
  });

  it("fires once, not on every tick after", () => {
    const onIdle = vi.fn();
    const stop = startIdleWatch(onIdle);
    vi.advanceTimersByTime(IDLE_TIMEOUT_MS * 3);
    expect(onIdle).toHaveBeenCalledTimes(1);
    stop();
  });
});
