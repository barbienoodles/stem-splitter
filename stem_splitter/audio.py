"""Decodifica/codifica audio tramite ffmpeg.

Usa l'ffmpeg incluso in imageio-ffmpeg (binari per macOS Intel, macOS Apple Silicon,
Linux e Windows, tutti con libmp3lame; libsoxr c'è solo nelle build Linux e macOS Intel: altrove
si usa il ricampionatore standard di ffmpeg, vedi has_soxr), così non serve installare nulla
a parte; se manca, ripiega sull'ffmpeg di sistema.

In ingresso accetta qualsiasi file che ffmpeg sappia leggere: MP3, WAV, AAC, M4A/ALAC,
MP4, MOV, MKV, WEBM, FLAC, OGG, OPUS, AIFF, WMA, CAF… (da un video prende la traccia audio).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

FORMATS = ("wav", "flac", "mp3")
SAMPLE_RATES = (44100, 48000, 96000)
BIT_DEPTHS = ("16", "24", "32f")  # 32f = 32 bit in virgola mobile (solo WAV)
MP3_MAX_RATE = 48000  # lo standard MP3 non va oltre i 48 kHz

INPUT_EXTENSIONS = (
    ".mp3", ".wav", ".wave", ".aac", ".m4a", ".mp4", ".m4v", ".mov", ".mkv", ".webm",
    ".flac", ".ogg", ".oga", ".opus", ".aif", ".aiff", ".aifc", ".wma", ".wmv", ".alac",
    ".caf", ".ac3", ".eac3", ".dts", ".amr", ".3gp", ".mka", ".avi", ".mpg", ".mpeg",
    ".ts", ".mp2", ".au", ".snd", ".w64", ".rf64", ".wv", ".ape", ".dsf", ".dff",
)


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        raise RuntimeError(
            "ffmpeg non trovato. Installa il pacchetto 'imageio-ffmpeg' oppure ffmpeg "
            "(su Mac: brew install ffmpeg)."
        )


@lru_cache(maxsize=1)
def has_soxr() -> bool:
    try:
        out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-buildconf"],
                             capture_output=True, text=True, timeout=10).stdout
        return "libsoxr" in out
    except Exception:
        return False


def _resample_filter(rate: int) -> list[str]:
    if has_soxr():  # resampler di qualità mastering
        return ["-af", f"aresample={rate}:resampler=soxr:precision=28:cheby=1"]
    return ["-af", f"aresample={rate}:filter_size=64:cutoff=0.97"]


# Solo file locali e pipe: un file "audio" costruito apposta (es. una playlist HLS) non può far
# aprire connessioni di rete a ffmpeg, qualunque sia la versione di ffmpeg in uso.
SAFE_INPUT = ["-protocol_whitelist", "file,pipe"]


def probe_samplerate(path: str | Path) -> int | None:
    """Frequenza di campionamento originale del file (None se non determinabile)."""
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", *SAFE_INPUT, "-i", str(path)],
                          capture_output=True, text=True)
    m = re.search(r"Audio:.*?(\d{4,6}) Hz", proc.stderr)
    return int(m.group(1)) if m else None


def load_audio(path: str | Path, samplerate: int, channels: int = 2) -> np.ndarray:
    """Legge un file audio/video e ritorna float32 [channels, samples] alla frequenza richiesta."""
    cmd = [
        ffmpeg_exe(), "-nostdin", "-v", "error", *SAFE_INPUT, "-i", str(path),
        "-map", "0:a:0", "-vn", *_resample_filter(samplerate),
        "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(channels), "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode(errors="replace").strip().splitlines()
        if any("matches no streams" in m for m in msg):
            raise ValueError("Il file non contiene una traccia audio.")
        raise ValueError(f"Impossibile leggere il file audio: {msg[-1] if msg else 'errore ffmpeg'}")
    data = np.frombuffer(proc.stdout, dtype=np.float32)
    if data.size == 0:
        raise ValueError("Il file non contiene audio.")
    return data.reshape(-1, channels).T.copy()


# Tetto per le uscite intere: misurato dopo il ricampionamento, quindi basta un margine minimo.
# L'MP3 ha bisogno di più spazio perché la codifica stessa crea over (−1 dBTP).
PEAK_CEILING = {"wav": 0.995, "flac": 0.995, "mp3": 0.891}


def measure_peak(wav: np.ndarray, samplerate: int, out_samplerate: int | None = None) -> float:
    """Picco assoluto del segnale come sarà dopo il ricampionamento (over inter-campione inclusi).

    Il ricampionamento avviene in streaming: non serve tenere in memoria la versione a 96 kHz.
    """
    wav = np.asarray(wav, dtype=np.float32)
    if wav.size == 0:
        return 0.0
    peak = float(np.max(np.abs(wav)))
    if not out_samplerate or out_samplerate == samplerate:
        return peak
    cmd = [
        ffmpeg_exe(), "-nostdin", "-v", "error",
        "-f", "f32le", "-ar", str(samplerate), "-ac", str(wav.shape[0]), "-i", "-",
        *_resample_filter(out_samplerate), "-f", "f32le", "-",
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data = np.ascontiguousarray(wav.T).tobytes()

    def feed() -> None:
        try:
            proc.stdin.write(data)
        finally:
            proc.stdin.close()

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    while chunk := proc.stdout.read(1 << 20):
        chunk = chunk[: len(chunk) - len(chunk) % 4]
        if chunk:
            peak = max(peak, float(np.max(np.abs(np.frombuffer(chunk, np.float32)))))
    writer.join()
    proc.wait()
    return peak


def _codec_args(fmt: str, bit_depth: str) -> list[str]:
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", "320k"]
    if fmt == "flac":
        if bit_depth == "16":
            return ["-c:a", "flac", "-sample_fmt", "s16", "-compression_level", "8"]
        # FLAC non supporta il float: 32f diventa 24 bit
        return ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24",
                "-compression_level", "8"]
    codec = {"16": "pcm_s16le", "24": "pcm_s24le", "32f": "pcm_f32le"}[bit_depth]
    return ["-c:a", codec, "-rf64", "auto"]  # RF64 oltre i 4 GB


def validate_output(fmt: str, samplerate: int, bit_depth: str) -> None:
    if fmt not in FORMATS:
        raise ValueError(f"Formato non supportato: {fmt}")
    if samplerate not in SAMPLE_RATES:
        raise ValueError(f"Frequenza non supportata: {samplerate}")
    if bit_depth not in BIT_DEPTHS:
        raise ValueError(f"Profondità in bit non supportata: {bit_depth}")
    if fmt == "mp3" and samplerate > MP3_MAX_RATE:
        raise ValueError("L'MP3 supporta al massimo 48 kHz: scegli WAV o FLAC per 96 kHz.")


def save_audio(
    wav: np.ndarray,
    path: str | Path,
    samplerate: int,
    fmt: str = "wav",
    out_samplerate: int | None = None,
    bit_depth: str = "24",
    gain: float = 1.0,
) -> Path:
    """Salva float32 [channels, samples] (a `samplerate`) ricampionando a `out_samplerate`.

    Non normalizza: il guadagno `gain` va deciso dal chiamante, uguale per tutti i file di un
    lavoro, così gli stem continuano a sommarsi al mix e Mid/Side a ricostruire L/R.
    """
    out_samplerate = out_samplerate or samplerate
    if fmt not in FORMATS or bit_depth not in BIT_DEPTHS:
        raise ValueError(f"Formato non supportato: {fmt} / {bit_depth}")
    if fmt == "mp3" and out_samplerate > MP3_MAX_RATE:
        raise ValueError("L'MP3 supporta al massimo 48 kHz: scegli WAV o FLAC per 96 kHz.")
    path = Path(path).with_suffix(f".{fmt}")
    wav = np.asarray(wav, dtype=np.float32)
    if gain != 1.0:
        wav = wav * np.float32(gain)
    channels = wav.shape[0]
    resample = _resample_filter(out_samplerate) if out_samplerate != samplerate else []
    dither = ["-af", "aresample=dither_method=triangular_hp"] if bit_depth == "16" and not resample else []
    if bit_depth == "16" and resample:
        resample[-1] += ":dither_method=triangular_hp"
    cmd = [
        ffmpeg_exe(), "-nostdin", "-v", "error", "-y",
        "-f", "f32le", "-ar", str(samplerate), "-ac", str(channels), "-i", "-",
        *resample, *dither, *_codec_args(fmt, bit_depth), str(path),
    ]
    proc = subprocess.run(cmd, input=np.ascontiguousarray(wav.T).tobytes(), capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Errore nel salvataggio: {proc.stderr.decode(errors='replace')}")
    return path
