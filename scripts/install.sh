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
  VERSIONS=(12 11 10)
  MAX_MINOR=12
  BREW_PREFIX=/usr/local
  echo "🖥  Mac Intel rilevato: verrà usata la CPU."
else
  VERSIONS=(12 13 11 10)
  MAX_MINOR=13
  BREW_PREFIX=/opt/homebrew
  if (( APPLE_SILICON )); then echo "🍏 Mac Apple Silicon rilevato: verrà usata la GPU (Metal/MPS)."; fi
fi

# Cerca anche dove installano Homebrew e python.org: da Finder il PATH può non includerli.
candidates() {
  local v
  for v in "${VERSIONS[@]}"; do
    echo "$BREW_PREFIX/opt/python@3.$v/bin/python3.$v"
    echo "$BREW_PREFIX/bin/python3.$v"
    echo "/Library/Frameworks/Python.framework/Versions/3.$v/bin/python3.$v"
    echo "python3.$v"
  done
  echo python3
  # solo per spiegare perché vengono scartate, se sono le uniche installate
  echo python3.13
  echo python3.14
}

PY=""
REJECTED=""
find_python() {
  PY="" REJECTED=""
  local c path minor machine seen=" "
  while read -r c; do
    path="$(command -v "$c" 2>/dev/null)" || continue
    [[ "$seen" == *" $path "* ]] && continue
    seen+="$path "
    # un candidato che non parte (es. /usr/bin/python3 senza Command Line Tools) si salta
    minor="" machine=""
    read -r minor machine < <("$path" -c 'import platform, sys; print(sys.version_info.minor if sys.version_info.major == 3 else 0, platform.machine())' 2>/dev/null) || true
    if ! [[ "$minor" =~ ^[0-9]+$ ]]; then
      REJECTED+="\n     - $path: non si avvia"
      continue
    fi
    if (( minor < 10 )); then
      REJECTED+="\n     - $path: Python 3.$minor, troppo vecchio"
      continue
    fi
    if (( minor > MAX_MINOR )); then
      REJECTED+="\n     - $path: Python 3.$minor, troppo nuovo$( (( ! APPLE_SILICON )) && [[ "$OS" == "Darwin" ]] && echo ' per PyTorch sui Mac Intel')"
      continue
    fi
    # un Python x86_64 (es. vecchio Homebrew in /usr/local) su Apple Silicon girerebbe in Rosetta
    if (( APPLE_SILICON )) && [[ "$machine" != "arm64" ]]; then
      REJECTED+="\n     - $path: versione Intel (x86_64), girerebbe in Rosetta senza GPU"
      continue
    fi
    PY="$path"
    return 0
  done < <(candidates)
  return 1
}

if ! find_python; then
  echo "❌ Serve Python 3.10–3.$MAX_MINOR$( (( APPLE_SILICON )) && echo ' nativo arm64')."
  [[ -n "$REJECTED" ]] && echo -e "   Trovati ma non adatti:$REJECTED"
  if [[ "$OS" == "Darwin" ]] && ! xcrun --version >/dev/null 2>&1 && [[ "$REJECTED" == *"/usr/bin/python3: non si avvia"* ]]; then
    echo "   (il python3 di sistema richiede gli Strumenti da riga di comando: xcode-select --install)"
  fi
  BREW="$(command -v brew || ls "$BREW_PREFIX/bin/brew" 2>/dev/null || true)"
  if [[ -n "$BREW" && -t 0 ]]; then
    read -r -p "   Vuoi che installi Python 3.12 con Homebrew? [s/N] " answer
    if [[ "$answer" =~ ^[sSyY] ]]; then
      "$BREW" install python@3.12
      find_python || { echo "❌ Python 3.12 installato ma non trovato: riapri il Terminale e riprova."; exit 1; }
    fi
  fi
  if [[ -z "$PY" ]]; then
    if [[ -n "$BREW" ]]; then
      echo "   Installa Python con:  brew install python@3.12"
    elif [[ "$OS" == "Darwin" ]]; then
      echo "   Scarica e installa Python 3.12 per macOS (l'ultima 3.12 con installer è la 3.12.10):"
      echo "   https://www.python.org/downloads/release/python-31210/"
      [[ -t 0 ]] && open "https://www.python.org/downloads/release/python-31210/" 2>/dev/null || true
    else
      echo "   Installa Python 3.12 con il gestore di pacchetti della tua distribuzione."
    fi
    echo "   Poi rilancia questo script."
    exit 1
  fi
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
