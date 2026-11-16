import { describe, expect, it } from "vitest";

import type { Notification } from "@/types/notifications";

import { notificationHref } from "./notificationHref";

const n = (o: Partial<Notification>) => ({ record: null, target: null, ...o }) as Notification;

describe("notificationHref (IR-765)", () => {
  it("opens the page the server names, for a notice with no Record", () => {
    expect(notificationHref(n({ target: "/rdco/call-requests" }))).toBe("/rdco/call-requests");
  });

  it("opens the Record otherwise", () => {
    expect(notificationHref(n({ record: 12 }))).toBe("/records/12");
  });

  it("has nowhere to go when the server names neither", () => {
    expect(notificationHref(n({}))).toBeNull();
  });
});
