#!/usr/bin/env bash
# Installa Stem Splitter in un ambiente virtuale (.venv) dentro la cartella del progetto.
# Funziona su macOS Intel, macOS Apple Silicon e Linux.
set -euo pipefail
cd "$(dirname "$0")/.."

OS="$(uname -s)"
# Si guarda l'hardware, non l'architettura della shell: un Mac Apple Silicon ha hw.optional.arm64=1
# anche quando il Terminale gira sotto Rosetta.
APPLE_SILICON=0
if [[ "$OS" == "Darwin" && "$(sysctl -in hw.optional.arm64 2>/dev/null)" == "1" ]]; then
  APPLE_SILICON=1
fi

# Sotto Rosetta anche un Python universal2 partirebbe come x86_64 e installerebbe la PyTorch Intel.
if (( APPLE_SILICON )) && [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null)" == "1" ]]; then
  echo "⚠️  Il terminale gira sotto Rosetta su un Mac Apple Silicon."
  echo "   Riapri il Terminale senza Rosetta (Info → deseleziona 'Apri con Rosetta') e rilancia lo script."
  exit 1
fi

# PyTorch per Mac Intel esiste solo fino alla 2.2.x, che supporta Python 3.10–3.12.
if [[ "$OS" == "Darwin" ]] && (( ! APPLE_SILICON )); then
  CANDIDATES=(python3.12 python3.11 python3.10 python3)
  MAX_MINOR=12
  echo "🖥  Mac Intel rilevato: verrà usata la CPU."
else
  # su Apple Silicon prima l'Homebrew nativo, poi quello che c'è nel PATH
  CANDIDATES=(/opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.11
              python3.12 python3.13 python3.11 python3.10 python3)
  MAX_MINOR=13
  if (( APPLE_SILICON )); then echo "🍏 Mac Apple Silicon rilevato: verrà usata la GPU (Metal/MPS)."; fi
fi

PY=""
SKIPPED_X86=""
for c in "${CANDIDATES[@]}"; do
  command -v "$c" >/dev/null 2>&1 || continue
  read -r minor machine < <("$c" -c 'import platform, sys; print(sys.version_info.minor if sys.version_info.major == 3 else 0, platform.machine())')
  (( minor >= 10 && minor <= MAX_MINOR )) || continue
  # un Python x86_64 (es. vecchio Homebrew in /usr/local) su Apple Silicon girerebbe in Rosetta
  if (( APPLE_SILICON )) && [[ "$machine" != "arm64" ]]; then
    SKIPPED_X86+=" $(command -v "$c")"
    continue
  fi
  PY="$c"
  break
done

if [[ -z "$PY" ]]; then
  echo "❌ Serve Python 3.10–3.$MAX_MINOR$( (( APPLE_SILICON )) && echo ' nativo arm64')."
  if [[ -n "$SKIPPED_X86" ]]; then
    echo "   Ignorati perché Intel (x86_64), girerebbero in Rosetta senza GPU:$SKIPPED_X86"
  fi
  echo "   Su Mac: brew install python@3.12   (oppure scaricalo da python.org)"
  exit 1
fi
echo "🐍 Uso $("$PY" --version) ($PY)"

# --clear: un .venv creato in precedenza con un Python di altra architettura va rifatto
"$PY" -m venv --clear .venv
.venv/bin/python -m pip install --upgrade pip wheel >/dev/null
.venv/bin/python -m pip install -e .
# senza dipendenze: evita `sphn`, che su Mac Intel non ha wheel (vedi pyproject.toml)
.venv/bin/python -m pip install --no-deps "demucs>=4.1.0,<5"

.venv/bin/python - "$APPLE_SILICON" <<'PY'
import platform, sys
from stem_splitter.device import pick_device
if sys.argv[1] == "1" and platform.machine() != "arm64":
    sys.exit(f"❌ L'ambiente usa un Python {platform.machine()}: su Apple Silicon serve arm64.")
print("✅ Installazione completata. Dispositivo:", pick_device().label)
PY
echo
echo "Avvia con:  ./scripts/start.sh   (oppure doppio clic su 'Stem Splitter.command' su Mac)"
