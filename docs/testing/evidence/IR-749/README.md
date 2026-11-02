# IR-749 — route-level bundle splitting

Baseline and implementation are measured from the same `main` lineage at
`a9d9c7fc3a5071848084f8cd529907ee3d2e319e`.

Production build command:

```text
cd frontend
npm run build
```

## Entry JavaScript

| Build | Raw | Gzip |
|---|---:|---:|
| Before IR-749 | 2,011.53 kB | 595.64 kB |
| After IR-749 | 552.69 kB | 156.18 kB |

The compressed entry JavaScript file is 73.8% smaller. These numbers describe
the entry bundle only; they are not a claim about total application download
size, browser timing, LCP, INP, or production capacity.

IR-749 does not raise Vite's chunk-size warning threshold. Real-device timing
and any CI-enforced bundle budget remain owned by IR-95.
