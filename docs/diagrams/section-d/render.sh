#!/usr/bin/env bash
# Re-render every Section D diagram (IR-1021). Needs Python 3 and Node 18 or later.
#   bash docs/diagrams/section-d/render.sh
# 1. reads the models, migrations and imports and rewrites the generated sources (src/*.json)
# 2. lays out and draws all 21 sources (src/*.json and src/*.mjs) into png/
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
py=python3; "$py" -c "" 2>/dev/null || py=python  # on Windows python3 can be a Store shim
"$py" "$here/tools/extract_models.py"
"$py" "$here/tools/extract_iris_ai.py"
"$py" "$here/tools/gen_erd.py"
"$py" "$here/tools/gen_components.py"
(cd "$here/tools" && npm ci --no-audit --no-fund --silent && node render.mjs "$@")
echo "Rendered $(ls "$here"/png/*.png | wc -l) diagrams into $here/png"
