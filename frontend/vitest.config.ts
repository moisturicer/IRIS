/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

/**
 * The frontend test seam (IR-210).
 *
 * Deliberately a **separate file** from `vite.config.ts` rather than a `test`
 * block added to it. The dev server and the production build are the two things
 * this repo cannot afford to destabilise, and nothing here can reach them.
 *
 * The `@` alias is repeated rather than imported from `vite.config.ts`: sharing
 * it would mean loading that file's `server.proxy` and watcher config into every
 * test run, which is a lot of unrelated behaviour to drag along for one path
 * mapping. If a third consumer appears, extract the alias instead.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // `globals` stays off. Tests import `describe`/`it`/`expect` from vitest
    // explicitly, so nothing depends on an ambient type declaration that
    // `tsc` (which `npm run build` runs over `src`) would also have to agree
    // about.
    globals: false,
    restoreMocks: true,
    // CI needs a run that ends. `vitest run` is non-interactive already; this
    // stops a hung render taking the job's full timeout instead of failing.
    testTimeout: 15000,
    // **Required on Windows, not a preference.** The default `threads` pool
    // talks to workers over a worker_threads RPC, and on this machine every
    // run died with `[vitest-worker]: Timeout calling "fetch" with
    // "["/@vite/env","web"]"` before collecting a single test -- six errors,
    // no tests, 79s. `forks` uses child processes instead and runs clean.
    // IR-210's own notes flagged the Windows/ESM interaction as the thing to
    // watch; this is it. Linux CI is unaffected either way, so the pool is set
    // unconditionally rather than behind a platform check nobody would test.
    pool: "forks",
  },
});
