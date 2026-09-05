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
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
