"""API web + interfaccia grafica (FastAPI)."""

from __future__ import annotations

import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
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


APP_ID = "stem-splitter"


def require_app_header(x_stem_splitter: str | None = Header(None)) -> None:
    """Le richieste che modificano qualcosa devono avere un header personalizzato.

    Un header non standard costringe il browser a chiedere il permesso CORS, che non diamo:
    così un altro sito aperto nel browser non può caricare file o chiudere l'app su localhost.
    """
    if x_stem_splitter != "1":
        raise HTTPException(403, "Richiesta non consentita")


def create_app(
    separator: Separator | None = None,
    workdir: Path | None = None,
    on_shutdown=None,
) -> FastAPI:
    separator = separator or Separator()
    manager = JobManager(separator, workdir or default_workdir())
    app = FastAPI(title="Stem Splitter", version=__version__)
    app.state.manager = manager

    @app.get("/api/info")
    def info():
        return {
            "app": APP_ID,
            "can_shutdown": on_shutdown is not None,
            "version": __version__,
            "device": separator.info.device,
            "device_label": separator.info.label,
            "platform": f"{separator.info.system} {separator.info.machine}",
            "stems": [{"key": o.key, "label": o.label, "outputs": o.names,
                       "six_stems": o.six_stems} for o in STEM_OPTIONS.values()],
            "default_stem": DEFAULT_STEM,
            "qualities": {k: q.label for k, q in QUALITIES.items()},
            "quality_details": {k: {
                "4": {"model": q.plan(False)[0], "shifts": q.plan(False)[1], "cost": q.cost(False)},
                "6": {"model": q.plan(True)[0], "shifts": q.plan(True)[1], "cost": q.cost(True)},
                "overlap": q.overlap} for k, q in QUALITIES.items()},
            "formats": list(FORMATS),
            "samplerates": list(SAMPLE_RATES),
            "bit_depths": list(BIT_DEPTHS),
            "mp3_max_rate": MP3_MAX_RATE,
            "midside": MIDSIDE_MODES,
            "input_extensions": list(INPUT_EXTENSIONS),
            "max_upload_mb": MAX_UPLOAD_MB,
        }

    @app.post("/api/shutdown", dependencies=[Depends(require_app_header)])
    def shutdown():
        if on_shutdown is None:
            raise HTTPException(404, "Non disponibile")
        on_shutdown()
        return {"ok": True}

    @app.post("/api/jobs", dependencies=[Depends(require_app_header)])
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

        # copia su disco fuori dall'event loop; il file temporaneo non sopravvive a nessun errore
        tmp_path = await run_in_threadpool(_store_upload, file.file, manager.workdir)
        try:
            job = manager.submit(file.filename or "audio", tmp_path, stem, quality, format,
                                 samplerate, bit_depth, midside)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return job.to_dict()

    def _job(job_id: str):
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(404, "Lavoro non trovato")
        return job

    @app.get("/api/jobs")
    def list_jobs():
        return [j.to_dict() for j in sorted(list(manager.jobs.values()), key=lambda j: -j.created)]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return _job(job_id).to_dict()

    @app.delete("/api/jobs/{job_id}", dependencies=[Depends(require_app_header)])
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
        # scritto una volta su disco nella cartella del lavoro e poi servito in streaming
        zip_path = manager.workdir / job.id / "stems.zip"
        if not zip_path.exists():
            part = zip_path.with_suffix(f".{uuid.uuid4().hex}.part")
            try:
                with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
                    for name, path in job.outputs.items():
                        zf.write(path, f"{_base_name(job)} - {name}.{job.fmt}")
                part.replace(zip_path)  # atomico: richieste concorrenti non vedono zip a metà
            finally:
                part.unlink(missing_ok=True)
        return FileResponse(zip_path, media_type="application/zip",
                            filename=f"{_base_name(job)} - stems.zip")

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app



def _store_upload(src, directory: Path) -> Path:
    """Copia l'upload in un file temporaneo con limite di dimensione; lo rimuove in caso di errore."""
    limit = MAX_UPLOAD_MB * 1024 * 1024
    fd, name = tempfile.mkstemp(dir=directory, suffix=".upload")
    path = Path(name)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := src.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File troppo grande (max {MAX_UPLOAD_MB} MB)")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "File vuoto")
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise
