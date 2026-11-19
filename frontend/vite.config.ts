import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    // Docker bind mounts on Windows/macOS don't deliver inotify events, so the
    // dev server never sees host edits. Opt into polling there via the env var
    // set in docker-compose.yml; native `npm run dev` keeps native watching.
    watch: process.env.VITE_USE_POLLING
      ? { usePolling: true, interval: 300 }
      : undefined,
    proxy: {
      // Ask IRIS talks to the AI runtime through the nginx edge, which checks
      // the reader's grant with Django and adds the gateway secret (IR-957).
      // Django has no such routes, so Vite hands them to the edge instead of
      // answering 404 (IR-1240). Keys match by prefix in insertion order, so
      // this one stays above "/api". The edge sends everything else under
      // /api to Django, never back here, so there is no proxy loop.
      "/api/v1/ai/runtime": {
        target: process.env.VITE_RUNTIME_PROXY_TARGET ?? "http://localhost:8080",
        // Same reason as "/api" below: the edge builds the grant check's Host
        // from the browser's.
        changeOrigin: false,
      },
      "/api": {
        target: process.env.VITE_PROXY_TARGET ?? "http://localhost:8000",
        // Keep the browser's Host (localhost) so Django's ALLOWED_HOSTS stays
        // unchanged; rewriting it to "backend:8000" is rejected with a 400.
        changeOrigin: false,
      },
    },
  },
});
