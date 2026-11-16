import { describe, expect, it } from "vitest";
import { excerpt } from "./excerpt";

describe("excerpt", () => {
  it("keeps a short passage whole, with its whitespace collapsed", () => {
    expect(excerpt("  Titration   at\ndawn. ")).toBe("Titration at dawn.");
  });

  it("ends a long passage at the last whole sentence that fits", () => {
    const first = "Gauges upstream fed a recurrent network that forecast river stage six hours ahead.";
    expect(excerpt(`${first} ${"More detail follows here. ".repeat(10)}`))
      .toBe(`${first} More detail follows here. More detail follows here. More detail follows here.`);
  });

  it("otherwise cuts at a word and marks the cut", () => {
    const text = Array.from({ length: 60 }, (_, n) => `word${n}`).join(" ");
    const short = excerpt(text, 60);
    expect(short.endsWith("…")).toBe(true);
    expect(short.length).toBeLessThanOrEqual(61);
    expect(text.startsWith(short.slice(0, -1))).toBe(true);
    expect(short.slice(0, -1).endsWith(" ")).toBe(false);
  });

  it("drops display math, which does not read as a summary", () => {
    expect(excerpt("The rate is $$k = 2$$ per hour.")).toBe("The rate is … per hour.");
  });
});
