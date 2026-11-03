"""Separazione degli stem con i modelli Demucs (Meta, licenza MIT) + elaborazione Mid/Side."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import torch

from .audio import load_audio, save_audio, validate_output
from .device import DeviceInfo, configure_threads, pick_device

ProgressFn = Callable[[float, str], None]


@dataclass(frozen=True)
class StemOption:
    key: str
    label: str
    # ogni uscita è la somma di uno o più stem del modello;
    # "*" = tutto ciò che non è già assegnato alle altre uscite
    outputs: tuple[tuple[str, tuple[str, ...]], ...]
    six_stems: bool = False

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.outputs]


REST = ("*",)

STEM_OPTIONS: dict[str, StemOption] = {
    o.key: o
    for o in [
        StemOption("vocals_drums", "Voce, batteria e strumentale",
                   (("vocals", ("vocals",)), ("drums", ("drums",)), ("instrumental", REST))),
        StemOption("vocals", "Voce e strumentale",
                   (("vocals", ("vocals",)), ("instrumental", REST))),
        StemOption("drums", "Batteria", (("drums", ("drums",)), ("no_drums", REST))),
        StemOption("bass", "Basso", (("bass", ("bass",)), ("no_bass", REST))),
        StemOption("guitar", "Chitarra", (("guitar", ("guitar",)), ("no_guitar", REST)), True),
        StemOption("piano", "Piano", (("piano", ("piano",)), ("no_piano", REST)), True),
        StemOption("all4", "4 stem (voce, batteria, basso, altro)",
                   tuple((s, (s,)) for s in ("vocals", "drums", "bass", "other"))),
        StemOption("all6", "6 stem (voce, batteria, basso, chitarra, piano, altro)",
                   tuple((s, (s,)) for s in ("vocals", "drums", "bass", "guitar", "piano", "other")),
                   True),
    ]
}
DEFAULT_STEM = "vocals_drums"


@dataclass(frozen=True)
class Quality:
    key: str
    label: str
    model4: str  # modello per le opzioni a 4 stem
    shifts: int  # passaggi con spostamento temporale casuale, poi mediati
    overlap: float  # sovrapposizione tra i segmenti analizzati


# "Profondità di calcolo": più passaggi e più sovrapposizione = meno artefatti, più tempo.
QUALITIES: dict[str, Quality] = {
    q.key: q
    for q in [
        Quality("standard", "Veloce", "htdemucs", 1, 0.25),
        Quality("high", "Alta (~4x più lenta)", "htdemucs_ft", 1, 0.25),
        Quality("max", "Massima (~12x più lenta)", "htdemucs_ft", 2, 0.5),
    ]
}

MIDSIDE_MODES = {
    "off": "No",
    "mix": "Solo del mix originale",
    "stems": "Del mix e di ogni stem",
}


def model_name_for(stem: str, quality: str) -> str:
    if STEM_OPTIONS[stem].six_stems:
        return "htdemucs_6s"  # unico modello con chitarra e piano
    return QUALITIES[quality].model4


def mid_side(wav: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Codifica M/S (mono): M = (L+R)/2, S = (L-R)/2, quindi L = M+S e R = M-S."""
    left, right = wav[0], wav[1]
    return ((left + right) / 2)[None], ((left - right) / 2)[None]


class Separator:
    """Carica i modelli una sola volta e li riusa; thread-safe (un brano alla volta)."""

    def __init__(self, device: str | None = None):
        configure_threads()
        self.info: DeviceInfo = pick_device(device)
        self._models: dict[str, torch.nn.Module] = {}
        self._lock = threading.Lock()

    # Separato per poter iniettare un modello finto nei test.
    def load_model(self, name: str) -> torch.nn.Module:
        if name not in self._models:
            try:
                from demucs.pretrained import get_model
            except ImportError as exc:
                raise RuntimeError(
                    "Demucs non è installato. Esegui ./scripts/install.sh oppure "
                    "`pip install --no-deps demucs`."
                ) from exc
            model = get_model(name)
            model.eval()
            self._models[name] = model
        return self._models[name]

    def separate(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        stem: str = DEFAULT_STEM,
        quality: str = "standard",
        fmt: str = "wav",
        samplerate: int = 44100,
        bit_depth: str = "24",
        midside: str = "off",
        shifts: int | None = None,
        progress: ProgressFn | None = None,
    ) -> dict[str, Path]:
        if stem not in STEM_OPTIONS:
            raise ValueError(f"Stem sconosciuto: {stem}. Opzioni: {', '.join(STEM_OPTIONS)}")
        if quality not in QUALITIES:
            raise ValueError(f"Qualità sconosciuta: {quality}")
        if midside not in MIDSIDE_MODES:
            raise ValueError(f"Modalità Mid/Side sconosciuta: {midside}")
        validate_output(fmt, samplerate, bit_depth)
        option, q = STEM_OPTIONS[stem], QUALITIES[quality]
        report = progress or (lambda p, m: None)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            name = model_name_for(stem, quality)
            report(0.02, f"Carico il modello {name}…")
            model = self.load_model(name)
            sr = model.samplerate  # i modelli lavorano a 44.1 kHz

            report(0.05, "Decodifico l'audio…")
            wav = torch.from_numpy(load_audio(input_path, sr, model.audio_channels))

            # stessa normalizzazione usata da demucs.separate
            ref = wav.mean(0)
            mean, std = ref.mean(), ref.std()
            std = std if std > 1e-8 else torch.tensor(1.0)
            mix = (wav - mean) / std

            sources = self._run(model, mix, shifts or q.shifts, q.overlap, report)
            by_name = dict(zip(model.sources, sources))  # [channels, samples] ciascuno

            tracks: dict[str, torch.Tensor] = {}
            used = {s for _, parts in option.outputs if parts != REST for s in parts}
            for out_name, parts in option.outputs:
                selected = [s for s in model.sources if s not in used] if parts == REST else parts
                # somma nel dominio normalizzato: la componente DC si aggiunge una sola volta
                tracks[out_name] = sum(by_name[s] for s in selected) * std + mean

            if midside == "stems":
                for out_name in list(tracks):
                    tracks[f"{out_name}_mid"], tracks[f"{out_name}_side"] = mid_side(tracks[out_name])
            if midside in ("mix", "stems"):
                tracks["mix_mid"], tracks["mix_side"] = mid_side(wav)

            outputs: dict[str, Path] = {}
            for i, (out_name, track) in enumerate(tracks.items()):
                report(0.93 + 0.07 * i / len(tracks), "Salvo i file…")
                outputs[out_name] = save_audio(track.numpy(), output_dir / out_name, sr, fmt,
                                               out_samplerate=samplerate, bit_depth=bit_depth)
            report(1.0, "Fatto")
            return outputs

    def _run(self, model, mix: torch.Tensor, shifts: int, overlap: float,
             report: ProgressFn) -> torch.Tensor:
        from demucs.apply import apply_model

        sub_models = getattr(model, "models", [model])
        segment = float(getattr(sub_models[0], "segment", 7.8))
        stride = max(1, int((1 - overlap) * segment * model.samplerate))
        total = len(sub_models) * max(1, shifts) * max(1, math.ceil(mix.shape[-1] / stride))
        done = 0
        device_label = {"mps": "GPU Apple", "cuda": "GPU", "cpu": "CPU"}[self.info.device]

        def on_chunk(state: dict) -> None:
            nonlocal done
            if state.get("state") == "end":
                done += 1
                report(0.08 + 0.85 * min(done / total, 1.0), f"Separazione in corso ({device_label})…")

        def apply(device: str) -> torch.Tensor:
            out = apply_model(
                model, mix[None], device=device, shifts=shifts, split=True,
                overlap=overlap, progress=False, callback=on_chunk,
            )[0]
            return out.to("cpu", dtype=torch.float32)

        report(0.08, f"Separazione in corso ({device_label})…")
        try:
            return apply(self.info.device)
        except RuntimeError as exc:
            if self.info.device == "cpu":
                raise
            # es. operazione non supportata o memoria insufficiente su MPS/CUDA
            report(0.08, f"Errore su {self.info.device} ({exc.__class__.__name__}), riprovo su CPU…")
            done = 0
            model.to("cpu")
            return apply("cpu")
