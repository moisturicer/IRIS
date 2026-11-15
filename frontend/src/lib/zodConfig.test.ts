import { describe, expect, it } from "vitest";
import { config, z } from "zod";
import "./zodConfig";

describe("zod runs without new Function (IR-823)", () => {
  it("is jitless, so building a schema never probes eval under the enforced CSP", () => {
    expect(config().jitless).toBe(true);
    const evalSpy = globalThis.Function;
    let probed = false;
    globalThis.Function = new Proxy(evalSpy, { construct(target, args) { probed = true; return Reflect.construct(target, args); },
      apply(target, self, args) { probed = true; return Reflect.apply(target, self, args); } });
    try {
      z.object({ email: z.string() }).parse({ email: "a@b.c" });
    } finally {
      globalThis.Function = evalSpy;
    }
    expect(probed).toBe(false);
  });
});
