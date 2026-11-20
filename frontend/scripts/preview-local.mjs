// Build the frontend for production and serve it against the local stack (IR-1250).
//
//   cd frontend && npm run preview:local      → http://localhost:4173
//
// Why: the dev server (`npm run dev`, or the Compose `frontend` service) is not
// what users get. Measured 2026-11-20 against the same local backend, a screen
// took 2.5–4.5 s to show its heading on the dev server and ~0.2 s on the
// production build: dev mode loads ~270 separate modules a page, runs every
// request twice (React StrictMode), and in Docker on Windows reads a bind-mounted
// folder. Use this to judge how IRIS looks and how fast it is; use the dev server
// to edit, since this one does not reload on a change (run it again).
//
// It builds into dist-local/, never dist/ (CI's bundle scan reads dist/), skips
// the type check `npm run build` runs, and proxies /api like the dev server.
// Needs the local backend up on port 8000 (`docker compose up -d`).
import { pathToFileURL } from "node:url";

/** Where to build, which port to serve, and the environment Vite's config reads. */
export function localPreviewSettings(env) {
  return {
    outDir: "dist-local",
    port: Number(env.PREVIEW_PORT ?? 4173),
    strictPort: true,
    env: {
      // 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first and
      // added ~190 ms to every API request (IR-1250).
      VITE_PROXY_TARGET: env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
    },
  };
}

async function main() {
  const settings = localPreviewSettings(process.env);
  // vite.config.ts reads these when it loads, for both the build and the preview proxy.
  Object.assign(process.env, settings.env);
  const { build, preview } = await import("vite");

  console.log(`Building the production frontend into ${settings.outDir}/ …`);
  await build({ build: { outDir: settings.outDir, emptyOutDir: true }, logLevel: "warn" });

  const server = await preview({
    build: { outDir: settings.outDir },
    preview: { port: settings.port, strictPort: settings.strictPort },
  });
  console.log(`\nProduction build at http://localhost:${settings.port}/  (API → ${settings.env.VITE_PROXY_TARGET})`);
  console.log("It does not reload on a change: stop it (Ctrl+C) and run it again.\n");
  server.printUrls();
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
