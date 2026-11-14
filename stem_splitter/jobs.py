"""Coda di lavori: un worker in background elabora un brano alla volta."""

from __future__ import annotations

import os
import queue
import re
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import outputs as out
from .audio import INPUT_EXTENSIONS
from .separator import Separator

DEFAULT_TTL_HOURS = float(os.environ.get("STEM_SPLITTER_TTL_HOURS", "24"))


# solo questi nomi appartengono all'app: la pulizia non tocca nient'altro nella cartella
OWN_ENTRY = re.compile(r"^(?:[0-9a-f]{12}|tmp[^/]*\.upload)$")


class JobCancelled(Exception):
    """Sollevata dal callback di avanzamento quando il lavoro viene eliminato."""


@dataclass
class Job:
    id: str
    filename: str
    input_path: Path
    output_dir: Path
    stem: str
    quality: str
    fmt: str
    samplerate: int = 44100
    bit_depth: str = "24"
    midside: str = "off"
    status: str = "queued"  # queued | running | done | error | cancelled
    progress: float = 0.0
    message: str = "In coda…"
    error: str | None = None
    outputs: dict[str, Path] = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    elapsed: float | None = None
    cancelled: bool = False
    dest_dir: Path | None = None  # dove copiare gli stem a fine lavoro (None = solo download)
    export_dir: Path | None = None
    export_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "stem": self.stem,
            "quality": self.quality,
            "format": self.fmt,
            "samplerate": self.samplerate,
            "bit_depth": self.bit_depth,
            "midside": self.midside,
            "status": self.status,
            "progress": round(self.progress, 4),
            "message": self.message,
            "error": self.error,
            "elapsed": self.elapsed,
            "export_dir": str(self.export_dir) if self.export_dir else None,
            "export_error": self.export_error,
            "stems": [
                {"name": name, "url": f"/api/jobs/{self.id}/stems/{name}"}
                for name in self.outputs
            ],
        }


class JobManager:
    def __init__(self, separator: Separator, workdir: Path, ttl_hours: float = DEFAULT_TTL_HOURS):
        self.separator = separator
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl_hours * 3600
        self.jobs: dict[str, Job] = {}
        self._jobs_lock = threading.Lock()
        self.purge_expired()
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._loop, daemon=True, name="stem-worker")
        self._worker.start()

    def submit(self, filename: str, data_path: Path, stem: str, quality: str, fmt: str,
               samplerate: int = 44100, bit_depth: str = "24", midside: str = "off",
               dest_dir: Path | None = None) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.workdir / job_id
        job_dir.mkdir(parents=True)
        # l'estensione si conserva solo per formati audio/video noti: un file chiamato .m3u8 (playlist)
        # potrebbe far leggere a ffmpeg altri file locali
        suffix = Path(filename).suffix.lower()
        input_path = job_dir / f"input{suffix if suffix in INPUT_EXTENSIONS else '.audio'}"
        shutil.move(str(data_path), input_path)
        job = Job(job_id, filename, input_path, job_dir / "stems", stem, quality, fmt,
                  samplerate, bit_depth, midside, dest_dir=dest_dir)
        with self._jobs_lock:
            self.jobs[job_id] = job
        self._queue.put(job_id)
        self.purge_expired()
        return job

    def purge_expired(self) -> None:
        """Elimina i lavori più vecchi del TTL, comprese le cartelle rimaste da avvii precedenti."""
        if self.ttl <= 0:
            return
        cutoff = time.time() - self.ttl
        with self._jobs_lock:
            for job in [j for j in self.jobs.values()
                        if j.status in ("done", "error") and j.created < cutoff]:
                self.jobs.pop(job.id, None)
                shutil.rmtree(self.workdir / job.id, ignore_errors=True)
            known = set(self.jobs)
        for entry in self.workdir.iterdir():
            if entry.name in known or not OWN_ENTRY.match(entry.name) or entry.is_symlink():
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    if entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
                    else:
                        entry.unlink(missing_ok=True)
            except FileNotFoundError:
                pass

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        with self._jobs_lock:
            job = self.jobs.pop(job_id, None)
            if job is None:
                return False
            job.cancelled = True
            running = job.status == "running"
        # se è in esecuzione, la cartella la rimuove il worker appena il lavoro si ferma
        if not running:
            shutil.rmtree(self.workdir / job_id, ignore_errors=True)
        return True

    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._jobs_lock:
                job = self.jobs.get(job_id)
                if job is None or job.cancelled:  # eliminato mentre era in coda
                    continue
                job.status, job.message = "running", "Avvio…"
            start = time.time()

            def report(p: float, msg: str, job=job) -> None:
                # chiamato per ogni segmento elaborato: è il punto in cui fermarsi
                if job.cancelled:
                    raise JobCancelled()
                job.progress, job.message = p, msg

            try:
                job.outputs = self.separator.separate(
                    job.input_path, job.output_dir, stem=job.stem,
                    quality=job.quality, fmt=job.fmt, samplerate=job.samplerate,
                    bit_depth=job.bit_depth, midside=job.midside, progress=report,
                )
                if job.dest_dir is not None:
                    report(0.995, "Copio gli stem nella cartella scelta…")
                    try:
                        job.export_dir = out.export_stems(job.outputs, job.dest_dir, job.filename)
                    except (OSError, ValueError, RuntimeError) as exc:
                        # gli stem restano scaricabili dalla pagina anche se la copia fallisce
                        job.export_error = str(exc)
                job.status, job.progress, job.message = "done", 1.0, "Completato"
            except JobCancelled:
                job.status, job.message = "cancelled", "Annullato"
            except Exception as exc:
                traceback.print_exc()
                job.status, job.error, job.message = "error", str(exc), "Errore"
            finally:
                job.elapsed = round(time.time() - start, 1)
                if job.cancelled:
                    shutil.rmtree(self.workdir / job.id, ignore_errors=True)
