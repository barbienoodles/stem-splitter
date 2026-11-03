#!/usr/bin/env bash
# Avvia l'interfaccia web e apre il browser (installa prima, se serve).
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x .venv/bin/stem-splitter ]] || ./scripts/install.sh
exec .venv/bin/stem-splitter serve "$@"
