#!/usr/bin/env bash
# Re-render every Section D diagram (IR-1021, IR-1022). Needs Java, Graphviz,
# plantuml.jar and Pillow. On Windows, set PYTHON=python.
#   PLANTUML_JAR=/path/to/plantuml.jar bash docs/diagrams/section-d/render.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
jar="${PLANTUML_JAR:?set PLANTUML_JAR to plantuml.jar (tested with 1.2024.7)}"
export PYTHONUTF8=1
py="${PYTHON:-python3}"  # PYTHON=python on Windows
"$py" "$here/tools/extract_models.py"
"$py" "$here/tools/extract_iris_ai.py"
"$py" "$here/tools/gen_erd.py"
"$py" "$here/tools/gen_components.py"
rm -f "$here"/png/*.png
java -Djava.awt.headless=true -jar "$jar" -tpng -o ../png "$here"/src/*.puml
"$py" "$here/tools/pad_png.py"
echo "Rendered $(ls "$here"/png/*.png | wc -l) diagrams into $here/png"
