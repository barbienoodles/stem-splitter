#!/usr/bin/env bash
# Installa Stem Splitter in un ambiente virtuale (.venv) dentro la cartella del progetto.
# Funziona su macOS Intel, macOS Apple Silicon e Linux.
set -euo pipefail
cd "$(dirname "$0")/.."

OS="$(uname -s)"
ARCH="$(uname -m)"

# Un Mac Apple Silicon che esegue il terminale sotto Rosetta si presenta come x86_64:
# in quel caso PyTorch non userebbe la GPU (MPS) e sarebbe limitato alla versione Intel.
if [[ "$OS" == "Darwin" && "$ARCH" == "x86_64" ]] && [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null)" == "1" ]]; then
  echo "⚠️  Il terminale gira sotto Rosetta su un Mac Apple Silicon."
  echo "   Riapri il Terminale senza Rosetta (Info → deseleziona 'Apri con Rosetta') e rilancia lo script."
  exit 1
fi

# PyTorch per Mac Intel esiste solo fino alla 2.2.x, che supporta Python 3.10–3.12.
if [[ "$OS" == "Darwin" && "$ARCH" == "x86_64" ]]; then
  CANDIDATES=(python3.12 python3.11 python3.10 python3)
  MAX_MINOR=12
  echo "🖥  Mac Intel rilevato: verrà usata la CPU."
else
  CANDIDATES=(python3.12 python3.13 python3.11 python3.10 python3)
  MAX_MINOR=13
  if [[ "$OS" == "Darwin" ]]; then echo "🍏 Mac Apple Silicon rilevato: verrà usata la GPU (Metal/MPS)."; fi
fi

PY=""
for c in "${CANDIDATES[@]}"; do
  if command -v "$c" >/dev/null 2>&1; then
    minor="$("$c" -c 'import sys; print(sys.version_info.minor if sys.version_info.major == 3 else 0)')"
    if (( minor >= 10 && minor <= MAX_MINOR )); then PY="$c"; break; fi
  fi
done

if [[ -z "$PY" ]]; then
  echo "❌ Serve Python 3.10–3.$MAX_MINOR."
  echo "   Su Mac: brew install python@3.12   (oppure scaricalo da python.org)"
  exit 1
fi
echo "🐍 Uso $("$PY" --version) ($PY)"

"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel >/dev/null
.venv/bin/python -m pip install -e .
# senza dipendenze: evita `sphn`, che su Mac Intel non ha wheel (vedi pyproject.toml)
.venv/bin/python -m pip install --no-deps "demucs>=4.1.0,<5"

.venv/bin/python - <<'PY'
from stem_splitter.device import pick_device
print("✅ Installazione completata. Dispositivo:", pick_device().label)
PY
echo
echo "Avvia con:  ./scripts/start.sh   (oppure doppio clic su 'Stem Splitter.command' su Mac)"
