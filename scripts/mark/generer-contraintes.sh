#!/usr/bin/env bash
# [.mark] Régénère api/constraints.txt : la version exacte de CHAQUE bibliothèque
# Python de l'image, y compris celles qu'on n'a pas choisies (trou T5, réflexe
# R5, décision E3 du 25/09/2026).
#
# Pourquoi : sans ce fichier, une bibliothèque tirée par une autre change seule
# à la construction suivante. OpenTelemetry 1.45 est arrivé ainsi le 25/09 et a
# cassé la CI.
#
# Usage, depuis la racine du fork, à chaque remise à niveau sur l'amont :
#   bash scripts/mark/generer-contraintes.sh
#   bash scripts/mark/generer-contraintes.sh 2026-09-25T15:30:00Z   # figer à une date passée
#
# ⛔ Seules les dépendances de l'IMAGE entrent ici (api/requirements.txt +
# Pipecat avec les extras du Dockerfile + opencv-python-headless). Les outils de
# développement n'y entrent pas : api/requirements.dev.txt fige watchfiles en
# 1.1.1, l'image installe la 1.3.0 ; les mélanger ferait changer la production.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

# Les extras sont lus dans api/Dockerfile : une seule liste fait foi, jamais une copie.
EXTRAS=$(grep -oE "pipecat-ai\[[a-z0-9,-]+\]" api/Dockerfile | head -1 | sed -E 's/^pipecat-ai//')
if [ -z "$EXTRAS" ]; then
    echo "Extras de Pipecat introuvables dans api/Dockerfile : la forme a changé, relire le fichier." >&2
    exit 1
fi

ENTREES=$(mktemp)
trap 'rm -f "$ENTREES"' EXIT
RACINE=$(pwd -W 2>/dev/null || pwd)
printf -- "-r %s/api/requirements.txt\n%s/pipecat%s\nopencv-python-headless\n" "$RACINE" "$RACINE" "$EXTRAS" > "$ENTREES"

DATE_OPT=()
if [ $# -ge 1 ]; then DATE_OPT=(--exclude-newer "$1"); fi

{
    echo "# [.mark] GÉNÉRÉ par scripts/mark/generer-contraintes.sh, ne pas éditer à la main."
    echo "# Versions exactes de toutes les bibliothèques de l'image (Linux, Python 3.13)."
    echo "# Lu par api/Dockerfile et scripts/setup_requirements.sh (-c). Renouvelé à chaque"
    echo "# remise à niveau sur l'amont. Pipecat n'y figure pas : son commit est tenu par"
    echo "# le sous-module et le Dockerfile (réflexe R2)."
    uv pip compile "$ENTREES" \
        --python-version 3.13 \
        --python-platform x86_64-unknown-linux-gnu \
        --no-emit-package pipecat-ai \
        --no-header --no-annotate -q \
        "${DATE_OPT[@]}"
} > api/constraints.txt

echo "api/constraints.txt : $(grep -cvE '^#' api/constraints.txt) versions figées."
