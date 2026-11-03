"""Coda di lavori: un worker in background elabora un brano alla volta."""

from __future__ import annotations

import queue
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .separator import Separator


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
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    message: str = "In coda…"
    error: str | None = None
    outputs: dict[str, Path] = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    elapsed: float | None = None

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
            "stems": [
                {"name": name, "url": f"/api/jobs/{self.id}/stems/{name}"}
                for name in self.outputs
            ],
        }


class JobManager:
    def __init__(self, separator: Separator, workdir: Path):
        self.separator = separator
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._loop, daemon=True, name="stem-worker")
        self._worker.start()

    def submit(self, filename: str, data_path: Path, stem: str, quality: str, fmt: str,
               samplerate: int = 44100, bit_depth: str = "24", midside: str = "off") -> Job:
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.workdir / job_id
        job_dir.mkdir(parents=True)
        input_path = job_dir / f"input{Path(filename).suffix.lower() or '.audio'}"
        shutil.move(str(data_path), input_path)
        job = Job(job_id, filename, input_path, job_dir / "stems", stem, quality, fmt,
                  samplerate, bit_depth, midside)
        self.jobs[job_id] = job
        self._queue.put(job_id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        job = self.jobs.pop(job_id, None)
        if job is None:
            return False
        shutil.rmtree(self.workdir / job_id, ignore_errors=True)
        return True

    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.jobs.get(job_id)
            if job is None:  # cancellato mentre era in coda
                continue
            job.status, job.message = "running", "Avvio…"
            start = time.time()

            def report(p: float, msg: str, job=job) -> None:
                job.progress, job.message = p, msg

            try:
                job.outputs = self.separator.separate(
                    job.input_path, job.output_dir, stem=job.stem,
                    quality=job.quality, fmt=job.fmt, samplerate=job.samplerate,
                    bit_depth=job.bit_depth, midside=job.midside, progress=report,
                )
                job.status, job.progress, job.message = "done", 1.0, "Completato"
            except Exception as exc:
                traceback.print_exc()
                job.status, job.error, job.message = "error", str(exc), "Errore"
            finally:
                job.elapsed = round(time.time() - start, 1)
