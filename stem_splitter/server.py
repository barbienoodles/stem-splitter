"""API web + interfaccia grafica (FastAPI)."""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .audio import BIT_DEPTHS, FORMATS, INPUT_EXTENSIONS, MP3_MAX_RATE, SAMPLE_RATES, validate_output
from .jobs import JobManager
from .separator import DEFAULT_STEM, MIDSIDE_MODES, QUALITIES, STEM_OPTIONS, Separator

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_MB = int(os.environ.get("STEM_SPLITTER_MAX_MB", "200"))
MEDIA_TYPES = {"wav": "audio/wav", "flac": "audio/flac", "mp3": "audio/mpeg"}


def default_workdir() -> Path:
    return Path(os.environ.get("STEM_SPLITTER_HOME", Path.home() / ".stem-splitter")) / "jobs"


def create_app(separator: Separator | None = None, workdir: Path | None = None) -> FastAPI:
    separator = separator or Separator()
    manager = JobManager(separator, workdir or default_workdir())
    app = FastAPI(title="Stem Splitter", version=__version__)
    app.state.manager = manager

    @app.get("/api/info")
    def info():
        return {
            "version": __version__,
            "device": separator.info.device,
            "device_label": separator.info.label,
            "platform": f"{separator.info.system} {separator.info.machine}",
            "stems": [{"key": o.key, "label": o.label, "outputs": o.names,
                       "six_stems": o.six_stems} for o in STEM_OPTIONS.values()],
            "default_stem": DEFAULT_STEM,
            "qualities": {k: q.label for k, q in QUALITIES.items()},
            "formats": list(FORMATS),
            "samplerates": list(SAMPLE_RATES),
            "bit_depths": list(BIT_DEPTHS),
            "mp3_max_rate": MP3_MAX_RATE,
            "midside": MIDSIDE_MODES,
            "input_extensions": list(INPUT_EXTENSIONS),
            "max_upload_mb": MAX_UPLOAD_MB,
        }

    @app.post("/api/jobs")
    async def create_job(
        file: UploadFile = File(...),
        stem: str = Form(DEFAULT_STEM),
        quality: str = Form("standard"),
        format: str = Form("wav"),
        samplerate: int = Form(44100),
        bit_depth: str = Form("24"),
        midside: str = Form("off"),
    ):
        if stem not in STEM_OPTIONS:
            raise HTTPException(400, f"Stem non valido: {stem}")
        if quality not in QUALITIES:
            raise HTTPException(400, f"Qualità non valida: {quality}")
        if midside not in MIDSIDE_MODES:
            raise HTTPException(400, f"Modalità Mid/Side non valida: {midside}")
        try:
            validate_output(format, samplerate, bit_depth)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        limit = MAX_UPLOAD_MB * 1024 * 1024
        size = 0
        with tempfile.NamedTemporaryFile(delete=False, dir=manager.workdir) as tmp:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    tmp.close()
                    os.unlink(tmp.name)
                    raise HTTPException(413, f"File troppo grande (max {MAX_UPLOAD_MB} MB)")
                tmp.write(chunk)
        if size == 0:
            os.unlink(tmp.name)
            raise HTTPException(400, "File vuoto")
        job = manager.submit(file.filename or "audio", Path(tmp.name), stem, quality, format,
                             samplerate, bit_depth, midside)
        return job.to_dict()

    def _job(job_id: str):
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(404, "Lavoro non trovato")
        return job

    @app.get("/api/jobs")
    def list_jobs():
        return [j.to_dict() for j in sorted(manager.jobs.values(), key=lambda j: -j.created)]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return _job(job_id).to_dict()

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str):
        if not manager.delete(job_id):
            raise HTTPException(404, "Lavoro non trovato")
        return {"ok": True}

    def _base_name(job) -> str:
        return Path(job.filename).stem or "audio"

    @app.get("/api/jobs/{job_id}/stems/{name}")
    def get_stem(job_id: str, name: str):
        job = _job(job_id)
        path = job.outputs.get(name)
        if path is None or not path.exists():
            raise HTTPException(404, "Stem non trovato")
        return FileResponse(path, media_type=MEDIA_TYPES[job.fmt],
                            filename=f"{_base_name(job)} - {name}.{job.fmt}")

    @app.get("/api/jobs/{job_id}/zip")
    def get_zip(job_id: str):
        job = _job(job_id)
        if job.status != "done":
            raise HTTPException(409, "Il lavoro non è ancora completato")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            for name, path in job.outputs.items():
                zf.write(path, f"{_base_name(job)} - {name}.{job.fmt}")
        buf.seek(0)
        filename = f"{_base_name(job)} - stems.zip"
        return StreamingResponse(buf, media_type="application/zip", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_quote(filename)}"})

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def _quote(s: str) -> str:
    from urllib.parse import quote

    return quote(s)
