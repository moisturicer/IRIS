#!/usr/bin/env bash
# Re-render every Section D diagram (IR-1021). Needs Java, Graphviz and plantuml.jar.
#   PLANTUML_JAR=/path/to/plantuml.jar bash docs/diagrams/section-d/render.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
jar="${PLANTUML_JAR:?set PLANTUML_JAR to plantuml.jar (tested with 1.2024.7)}"
python3 "$here/tools/extract_models.py"
python3 "$here/tools/extract_iris_ai.py"
python3 "$here/tools/gen_erd.py"
python3 "$here/tools/gen_components.py"
java -Djava.awt.headless=true -jar "$jar" -tpng -o ../png "$here"/src/*.puml
echo "Rendered $(ls "$here"/png/*.png | wc -l) diagrams into $here/png"
