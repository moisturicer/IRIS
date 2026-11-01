// Commands run inside the IR-631 stack's backend container, the way an
// operator would run them. Used only for what the application has no screen
// or endpoint for: seeding accounts and moving a due date into the past.
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const e2eDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(e2eDir, "..");

const COMPOSE = [
  "compose", "-p", process.env.E2E_COMPOSE_PROJECT ?? "iris-e2e",
  "--env-file", path.join(e2eDir, ".env.e2e"),
  "--project-directory", repoRoot,
  "-f", path.join(repoRoot, "docker-compose.prod.yml"),
  "-f", path.join(repoRoot, "docker-compose.e2e.yml"),
];

/** `python manage.py <args>` in the backend container; returns stdout. */
export function manage(...args: string[]): string {
  return execFileSync(
    "docker", [...COMPOSE, "exec", "-T", "backend", "python", "manage.py", ...args],
    { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );
}

/** The build under test, for the run record. */
export function buildIdentity(): { sha: string | null; settings: string } {
  let sha: string | null = process.env.E2E_BUILD_SHA ?? null;
  if (!sha) {
    try {
      sha = execFileSync("git", ["-C", repoRoot, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
    } catch {
      sha = null;
    }
  }
  return { sha, settings: "config.settings.production" };
}
