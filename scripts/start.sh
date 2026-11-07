#!/usr/bin/env bash
# Avvia l'interfaccia web e apre il browser (installa prima, se serve).
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x .venv/bin/banana-split ]] || ./scripts/install.sh
exec .venv/bin/banana-split serve "$@"
