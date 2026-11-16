import { describe, expect, it } from "vitest";
import {
  PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordLengthError, passwordStrength,
} from "./passwordPolicy";

describe("the form-side length rule mirrors the server (IR-819)", () => {
  it("is 12 to 128 characters", () => {
    expect([PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH]).toEqual([12, 128]);
    expect(passwordLengthError("a".repeat(11))).toBe("Password must be at least 12 characters.");
    expect(passwordLengthError("a".repeat(12))).toBeUndefined();
    expect(passwordLengthError("a".repeat(128))).toBeUndefined();
    expect(passwordLengthError("a".repeat(129), "New password")).toBe("New password must be at most 128 characters.");
    // Counted as the server counts: eleven letters and one emoji are twelve characters.
    expect(passwordLengthError("abcdefghijk\u{1F512}")).toBeUndefined();
  });
});

describe("password strength is a guide", () => {
  it("calls anything under the minimum too short", () => {
    expect(passwordStrength("Ab1!Ab1!Ab1")).toEqual({ score: 0, label: "Too short" });
  });

  it("rises with length and with a mix of characters", () => {
    expect(passwordStrength("kalamansitid").score).toBe(1);
    expect(passwordStrength("kalamansitidepool").score).toBe(2);
    expect(passwordStrength("Kalamansi-Tide-42").label).toBe("Strong");
    expect(passwordStrength("a long phrase of plain words").score).toBe(3);
  });

  it("calls one repeated character or one run weak, however long", () => {
    expect(passwordStrength("aaaaaaaaaaaaaaaaaaaaaaaa").label).toBe("Weak");
    expect(passwordStrength("abcdefghijklmnopq").label).toBe("Weak");
    expect(passwordStrength("123456789012").label).toBe("Weak");
  });
});
