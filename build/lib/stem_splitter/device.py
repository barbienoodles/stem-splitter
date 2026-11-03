"""Scelta del dispositivo di calcolo: CUDA, Apple Silicon (MPS) o CPU (Intel/AMD)."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass

import torch


@dataclass(frozen=True)
class DeviceInfo:
    device: str  # "cuda", "mps" o "cpu"
    label: str  # descrizione leggibile
    machine: str  # es. "arm64", "x86_64"
    system: str  # es. "Darwin", "Linux"


def _cpu_name() -> str:
    if platform.system() == "Darwin":
        try:
            import subprocess

            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip()
            if out:
                return out
        except Exception:
            pass
    return platform.processor() or platform.machine()


def is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def mps_usable() -> bool:
    backend = getattr(torch.backends, "mps", None)
    return bool(backend and backend.is_available() and backend.is_built())


def pick_device(preferred: str | None = None) -> DeviceInfo:
    """Sceglie il dispositivo migliore.

    Ordine automatico: CUDA > MPS (solo Apple Silicon) > CPU.
    Sui Mac Intel MPS può risultare "disponibile" con GPU AMD ma è instabile con
    Demucs, quindi si usa la CPU a meno che non venga forzato con preferred="mps".
    Si può forzare anche con la variabile d'ambiente STEM_SPLITTER_DEVICE.
    """
    preferred = (preferred or os.environ.get("STEM_SPLITTER_DEVICE") or "auto").lower()
    system, machine = platform.system(), platform.machine()

    if preferred == "auto":
        if torch.cuda.is_available():
            preferred = "cuda"
        elif is_apple_silicon() and mps_usable():
            preferred = "mps"
        else:
            preferred = "cpu"

    if preferred == "cuda" and not torch.cuda.is_available():
        preferred = "cpu"
    if preferred == "mps" and not mps_usable():
        preferred = "cpu"

    if preferred == "cuda":
        label = f"GPU NVIDIA ({torch.cuda.get_device_name(0)})"
    elif preferred == "mps":
        label = "GPU Apple Silicon (Metal/MPS)"
    else:
        label = f"CPU ({_cpu_name()}, {torch.get_num_threads()} thread)"
    return DeviceInfo(device=preferred, label=label, machine=machine, system=system)


def configure_threads() -> None:
    """Usa tutti i core fisici disponibili per l'inferenza su CPU."""
    n = os.cpu_count() or 1
    try:
        torch.set_num_threads(max(1, n))
    except RuntimeError:
        pass
