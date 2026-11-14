"""Integrità dei file dei modelli Demucs.

I file dei modelli (.th) vengono caricati da Demucs con `torch.load(weights_only=False)`, cioè con
pickle: un file manomesso può contenere codice che viene ESEGUITO al caricamento. Demucs/torch.hub
controllano solo i primi 8 caratteri dell'impronta (32 bit) e solo al momento del download; un file
già in cache non viene più verificato.

Qui fissiamo l'impronta SHA-256 COMPLETA di ogni file e la verifichiamo prima di OGNI caricamento:
un file diverso (corrotto o manomesso) viene cancellato e riscaricato; un download che non
corrisponde viene scartato e non tocca mai la cache.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import torch

REMOTE = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/"

# Impronte complete dei file pubblicati da Meta (il prefisso nel nome è quello ufficiale).
SHA256 = {
    "955717e8-8726e21a.th": "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4",
    "f7e0c4bc-ba3fe64a.th": "ba3fe64ae8ef66ac9a4857222ce48efbdc5eb3ad375cb79dd13debee5aaa4066",
    "d12395a8-e57c48e6.th": "e57c48e6b0e38af4f7118d7bd08c49f0a0c0edf7d09143bdd902ea0d237303e6",
    "92cfc3b6-ef3bcb9c.th": "ef3bcb9c8b40d14ae5d51b6db2587339cc12c6b77c0be151ce6d69002e087bf2",
    "04573f0d-f3cf25b2.th": "f3cf25b222c4eed7cd49dd8b2c9597d50c18bd154090f7b919cfa5f93cf22c49",
    "5c90dfd2-34c22ccb.th": "34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd",
}

FILES = {
    "htdemucs": ["955717e8-8726e21a.th"],
    "htdemucs_ft": ["f7e0c4bc-ba3fe64a.th", "d12395a8-e57c48e6.th",
                    "92cfc3b6-ef3bcb9c.th", "04573f0d-f3cf25b2.th"],
    "htdemucs_6s": ["5c90dfd2-34c22ccb.th"],
}


class ModelIntegrityError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_dir() -> Path:
    return Path(torch.hub.get_dir()) / "checkpoints"


def _download(url: str, dest: Path) -> None:
    torch.hub.download_url_to_file(url, str(dest), hash_prefix=None, progress=False)


def ensure_model_files(name: str) -> list[Path]:
    """Garantisce che i file del modello siano in cache e IDENTICI a quelli attesi."""
    if name not in FILES:
        raise ModelIntegrityError(f"Modello sconosciuto: {name}")
    folder = cache_dir()
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for fname in FILES[name]:
        expected = SHA256[fname]
        path = folder / fname
        if path.exists() and _sha256(path) != expected:
            path.unlink()  # corrotto o manomesso: non va mai caricato
        if not path.exists():
            fd, tmp = tempfile.mkstemp(dir=folder, prefix=".download-", suffix=".part")
            os.close(fd)
            try:
                _download(REMOTE + fname, Path(tmp))
                got = _sha256(Path(tmp))
                if got != expected:
                    raise ModelIntegrityError(
                        f"Il file del modello {fname} scaricato non corrisponde all'impronta attesa "
                        f"(atteso {expected[:12]}…, ricevuto {got[:12]}…): scartato.")
                os.replace(tmp, path)
            finally:
                Path(tmp).unlink(missing_ok=True)
        paths.append(path)
    return paths
