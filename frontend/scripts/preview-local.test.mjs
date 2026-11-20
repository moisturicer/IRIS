// The local production preview's settings (IR-1250). Run with `npm run test:security`,
// which runs every scripts/*.test.mjs.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { localPreviewSettings } from "./preview-local.mjs";

describe("localPreviewSettings (IR-1250)", () => {
  it("builds into its own folder, so CI's dist/ bundle scan never sees it", () => {
    assert.equal(localPreviewSettings({}).outDir, "dist-local");
  });

  it("serves on 4173 and refuses another port rather than moving silently", () => {
    const { port, strictPort } = localPreviewSettings({});
    assert.equal(port, 4173);
    assert.equal(strictPort, true);
  });

  it("proxies the API to 127.0.0.1, not localhost, which costs ~190 ms a request on Windows", () => {
    assert.equal(localPreviewSettings({}).env.VITE_PROXY_TARGET, "http://127.0.0.1:8000");
  });

  it("keeps a proxy target the caller already set", () => {
    const { env } = localPreviewSettings({ VITE_PROXY_TARGET: "http://127.0.0.1:9000" });
    assert.equal(env.VITE_PROXY_TARGET, "http://127.0.0.1:9000");
  });

  it("takes another port from PREVIEW_PORT", () => {
    assert.equal(localPreviewSettings({ PREVIEW_PORT: "4300" }).port, 4300);
  });
});
