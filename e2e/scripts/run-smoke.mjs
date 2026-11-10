import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const e2eDir = fileURLToPath(new URL("..", import.meta.url));
const frontendDir = resolve(e2eDir, "../frontend");
const port = Number(process.env.SMOKE_PORT ?? "4173");
const viteCli = resolve(frontendDir, "node_modules/vite/bin/vite.js");
const playwrightCli = resolve(e2eDir, "node_modules/playwright/cli.js");

const preview = spawn(process.execPath, [
  viteCli, "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort",
], { cwd: frontendDir, env: process.env, stdio: "inherit" });

let tests;
const stopped = new WeakSet();

function exited(child) {
  if (child.exitCode !== null) return Promise.resolve(child.exitCode);
  return new Promise((resolveExit) => child.once("exit", (code) => resolveExit(code ?? 1)));
}

async function waitForPreview() {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (preview.exitCode !== null) throw new Error(`Vite preview exited with code ${preview.exitCode}.`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/login`);
      if (response.ok) return;
    } catch {
      // The preview is still starting.
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 100));
  }
  throw new Error("Vite preview did not become ready within 60 seconds.");
}

async function stop(child) {
  if (!child || child.exitCode !== null || stopped.has(child)) return;
  stopped.add(child);
  const closed = exited(child);
  child.kill("SIGTERM");
  let timer;
  const timeout = new Promise((resolveDelay) => { timer = setTimeout(() => resolveDelay(false), 3_000); });
  if (await Promise.race([closed.then(() => true), timeout])) {
    clearTimeout(timer);
    return;
  }
  child.kill("SIGKILL");
  await closed;
}

try {
  await waitForPreview();
  tests = spawn(process.execPath, [
    playwrightCli, "test", "-c", "playwright.smoke.config.ts", ...process.argv.slice(2),
  ], {
    cwd: e2eDir,
    env: { ...process.env, IRIS_SMOKE_MANAGED_SERVER: "1" },
    stdio: "inherit",
  });
  process.exitCode = await exited(tests);
} catch (error) {
  process.exitCode = 1;
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
} finally {
  await stop(tests);
  await stop(preview);
}
