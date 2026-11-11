"""Dove finiscono gli stem: cartella scelta dall'utente, ricordata tra un avvio e l'altro.

- l'impostazione sta in <app_home>/settings.json;
- la cartella si sceglie con la finestra di sistema (Finder, Esplora file, zenity/kdialog);
- a lavoro finito gli stem vengono copiati in "<cartella>/<brano> - Banana Split/".
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP_NAME = "Banana Split"
PICK_TIMEOUT = 600  # secondi per scegliere la cartella

_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_name(name: str) -> str:
    """Nome di file sicuro su Mac, Windows e Linux (anche dentro uno zip)."""
    name = _UNSAFE_NAME.sub("_", name).strip(" ._")
    return name[:120] or "audio"


def app_home() -> Path:
    """Cartella dei dati dell'app (lavori, impostazioni, log)."""
    home = os.environ.get("BANANA_SPLIT_HOME") or os.environ.get("STEM_SPLITTER_HOME")
    path = Path(home) if home else Path.home() / ".banana-split"
    path.mkdir(parents=True, exist_ok=True)
    return path


def display_path(path: Path) -> str:
    """Percorso breve per l'interfaccia: la cartella personale diventa "~"."""
    try:
        return "~" + os.sep + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def default_output_dir() -> Path:
    music = Path.home() / "Music"
    return (music if music.is_dir() else Path.home()) / APP_NAME


# ---------- impostazioni ----------

def _settings_file() -> Path:
    return app_home() / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(_settings_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**changes) -> dict:
    data = {**load_settings(), **changes}
    tmp = _settings_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_settings_file())
    return data


def output_dir() -> Path:
    saved = load_settings().get("output_dir")
    return Path(saved) if saved else default_output_dir()


def validate_output_dir(value: str) -> Path:
    """Cartella assoluta e scrivibile; viene creata se manca solo l'ultimo livello."""
    if not value or not value.strip():
        raise ValueError("Indica una cartella.")
    path = Path(os.path.expanduser(value.strip()))
    if not path.is_absolute():
        raise ValueError("Serve un percorso completo, ad esempio /Users/nome/Music.")
    if path.exists() and not path.is_dir():
        raise ValueError("Il percorso indicato è un file, non una cartella.")
    if not path.exists():
        if not path.parent.is_dir():
            raise ValueError(f"La cartella {path.parent} non esiste.")
        path.mkdir()
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".banana-", delete=True):
            pass
    except OSError:
        raise ValueError("Non ho il permesso di scrivere in questa cartella.") from None
    return path


# ---------- copia degli stem ----------

def _unique_dir(base: Path) -> Path:
    if not base.exists():
        return base
    for i in range(2, 1000):
        candidate = base.with_name(f"{base.name} ({i})")
        if not candidate.exists():
            return candidate
    raise RuntimeError("Troppe cartelle con lo stesso nome")


def export_stems(outputs: dict[str, Path], dest_root: Path, song: str) -> Path:
    """Copia gli stem in una nuova sottocartella della destinazione (mai sovrascrivendo)."""
    dest_root = validate_output_dir(str(dest_root))
    base = safe_name(Path(song.replace("\\", "/")).stem)
    folder = _unique_dir(dest_root / f"{base} - {APP_NAME}")
    folder.mkdir()
    for name, src in outputs.items():
        shutil.copy2(src, folder / f"{base} - {name}{src.suffix}")
    return folder


# ---------- finestra di sistema per scegliere la cartella ----------

class PickerUnavailable(RuntimeError):
    pass


def _picker_command(initial: Path) -> tuple[list[str], dict] | None:
    if sys.platform == "darwin" and shutil.which("osascript"):
        # "activate" porta in primo piano la finestra di osascript stesso: nessun permesso
        # di automazione su altre app. Il percorso iniziale passa come argomento, non nel codice.
        script = [
            "on run argv",
            "activate",
            'set f to choose folder with prompt "Dove salvo gli stem?" '
            "default location (POSIX file (item 1 of argv))",
            "return POSIX path of f",
            "end run",
        ]
        cmd = ["osascript"]
        for line in script:
            cmd += ["-e", line]
        return cmd + [str(initial)], {}
    if sys.platform == "win32":
        exe = shutil.which("powershell") or shutil.which("pwsh")
        if exe:
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
                "$d.Description='Dove salvo gli stem?';$d.ShowNewFolderButton=$true;"
                "$d.SelectedPath=$env:BANANA_INITIAL;"
                "$o=New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
                "if($d.ShowDialog($o) -eq 'OK'){[Console]::Out.Write($d.SelectedPath)}else{exit 1}"
            )
            env = {**os.environ, "BANANA_INITIAL": str(initial)}
            return [exe, "-NoProfile", "-STA", "-Command", ps], {"env": env, "creationflags": 0x08000000}
        return None
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--directory", "--title=Dove salvo gli stem?",
                f"--filename={initial}/"], {}
    if shutil.which("kdialog"):
        return ["kdialog", "--getexistingdirectory", str(initial), "--title", "Dove salvo gli stem?"], {}
    return None


def can_pick_folder() -> bool:
    return _picker_command(Path.home()) is not None


def pick_folder(initial: Path | None = None) -> Path | None:
    """Apre la finestra di sistema. Ritorna la cartella scelta, None se l'utente annulla."""
    start = initial if initial and initial.is_dir() else Path.home()
    found = _picker_command(start)
    if found is None:
        raise PickerUnavailable("Su questo sistema non c'è una finestra per scegliere le cartelle.")
    cmd, extra = found
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=PICK_TIMEOUT, **extra)
    chosen = proc.stdout.strip()
    if proc.returncode != 0 or not chosen:
        return None  # annullato
    return Path(chosen.rstrip("/\\") or chosen)


def reveal(path: Path) -> None:
    """Apre la cartella nel Finder / Esplora file / file manager."""
    if sys.platform == "darwin":
        cmd = ["open", str(path)]
    elif sys.platform == "win32":
        cmd = ["explorer", str(path)]
    else:
        cmd = ["xdg-open", str(path)]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:  # es. Linux senza xdg-open
        raise RuntimeError(f"Non riesco ad aprire la cartella ({exc.__class__.__name__}): {path}") from exc
