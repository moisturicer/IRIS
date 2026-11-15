import { config } from "zod";

// zod 4 probes whether it may compile validators with `new Function` the first
// time it validates, and falls back when it may not. Under the enforced
// Content-Security-Policy (`script-src 'self'`, no 'unsafe-eval'; IR-823) that
// probe is a violation on every page, reported and logged though nothing
// breaks. `jitless` skips the probe and always uses the interpreter, which is
// what the policy would force anyway. Imported first in main.tsx, before any
// schema is used.
config({ jitless: true });
