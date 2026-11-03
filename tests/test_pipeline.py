"""Test end-to-end con un HTDemucs piccolo a pesi casuali (nessun download richiesto)."""

import time
from pathlib import Path

import numpy as np
import pytest
import torch

import subprocess

from stem_splitter.audio import ffmpeg_exe, load_audio, probe_samplerate, save_audio
from stem_splitter.separator import DEFAULT_STEM, STEM_OPTIONS, Separator, model_name_for

SR = 44100


class FakeSeparator(Separator):
    def load_model(self, name):
        if name not in self._models:
            from demucs.apply import BagOfModels
            from demucs.htdemucs import HTDemucs

            sources = ["drums", "bass", "other", "vocals"]
            if name == "htdemucs_6s":
                sources += ["guitar", "piano"]
            torch.manual_seed(0)
            m = HTDemucs(sources, channels=8, t_layers=1, segment=4)
            self._models[name] = BagOfModels([m]).eval()
        return self._models[name]


@pytest.fixture(scope="module")
def song(tmp_path_factory) -> Path:
    t = np.arange(int(SR * 6)) / SR
    sig = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.random.default_rng(0).standard_normal(t.size)
    wav = np.stack([sig, sig * 0.8]).astype(np.float32)
    return save_audio(wav, tmp_path_factory.mktemp("in") / "song", SR, "mp3")


def test_model_choice():
    assert DEFAULT_STEM == "vocals_drums"
    assert model_name_for("vocals", "standard") == "htdemucs"
    assert model_name_for("vocals", "high") == "htdemucs_ft"
    assert model_name_for("vocals", "max") == "htdemucs_ft"
    assert model_name_for("guitar", "high") == "htdemucs_6s"


def test_quality_levels_differ_for_six_stems():
    from stem_splitter.separator import QUALITIES

    six = [QUALITIES[k].plan(True) for k in ("standard", "high", "max")]
    assert len(set(six)) == 3  # ogni livello cambia davvero qualcosa anche con chitarra/piano
    assert [round(QUALITIES[k].cost(False)) for k in ("standard", "high", "max")] == [1, 4, 12]


@pytest.mark.parametrize("ext,args", [
    (".mp4", ["-f", "lavfi", "-i", "color=c=black:s=64x64:d=3", "-c:v", "libx264", "-c:a", "aac", "-shortest"]),
    (".aac", ["-c:a", "aac"]),
    (".m4a", ["-c:a", "aac"]),
    (".wav", ["-ar", "96000", "-c:a", "pcm_s24le"]),
    (".flac", []),
    (".ogg", ["-c:a", "libvorbis"]),
    (".aiff", []),
])
def test_input_formats(song, tmp_path, ext, args):
    """Accetta qualsiasi file audio/video leggibile da ffmpeg (da un video prende l'audio)."""
    out = tmp_path / f"in{ext}"
    # l'input video (lavfi) va prima delle opzioni di codifica
    video = args[:6] if args[:2] == ["-f", "lavfi"] else []
    rest = args[6:] if video else args
    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-i", str(song), *video,
                    "-map", "0:a", *(["-map", "1:v"] if video else []), *rest, str(out)], check=True)
    wav = load_audio(out, SR)
    assert wav.shape[0] == 2 and wav.shape[1] > SR * 2.5


def test_video_without_audio_is_rejected(tmp_path):
    out = tmp_path / "mute.mp4"
    subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
                    "-c:v", "libx264", str(out)], check=True)
    with pytest.raises(ValueError, match="traccia audio"):
        load_audio(out, SR)


@pytest.mark.parametrize("fmt,rate,bits,codec", [
    ("wav", 44100, "16", "pcm_s16le"),
    ("wav", 48000, "24", "pcm_s24le"),
    ("wav", 96000, "32f", "pcm_f32le"),
    ("flac", 96000, "24", "flac"),
    ("mp3", 48000, "24", "mp3"),
])
def test_output_rate_and_depth(song, tmp_path, fmt, rate, bits, codec):
    wav = load_audio(song, SR)
    path = save_audio(wav, tmp_path / "x", SR, fmt, out_samplerate=rate, bit_depth=bits)
    info = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    assert f"{rate} Hz" in info and codec in info
    back = load_audio(path, SR)
    assert abs(back.shape[1] - wav.shape[1]) < SR * 0.06  # durata invariata dopo il ricampionamento
    assert probe_samplerate(path) == rate


def test_mp3_96k_rejected(song, tmp_path):
    with pytest.raises(ValueError, match="48 kHz"):
        save_audio(load_audio(song, SR), tmp_path / "x", SR, "mp3", out_samplerate=96000)


def test_audio_roundtrip(song, tmp_path):
    wav = load_audio(song, SR)
    assert wav.shape[0] == 2 and abs(wav.shape[1] - 6 * SR) < SR * 0.1
    for fmt in ("wav", "flac", "mp3"):
        assert save_audio(wav, tmp_path / "x", SR, fmt).stat().st_size > 1000


@pytest.mark.parametrize("stem", list(STEM_OPTIONS))
def test_separate(song, tmp_path, stem):
    sep = FakeSeparator("cpu")
    steps = []
    out = sep.separate(song, tmp_path, stem=stem, fmt="wav", progress=lambda p, m: steps.append(p))
    assert list(out) == STEM_OPTIONS[stem].names
    for path in out.values():
        data = load_audio(path, SR)
        assert abs(data.shape[1] - 6 * SR) < SR * 0.1
    assert steps == sorted(steps) and steps[-1] == 1.0 and len(steps) > 4


def test_complement_is_sum_of_other_stems(song, tmp_path, monkeypatch):
    """"strumentale" = somma di tutti gli stem tranne la voce."""
    sep = FakeSeparator("cpu")
    model = sep.load_model("htdemucs")
    levels = {"drums": 0.1, "bass": 0.2, "other": 0.05, "vocals": 0.3}

    def fake_run(model_, mix, shifts, overlap, report):
        return torch.stack([torch.full_like(mix, levels[s]) for s in model.sources])

    monkeypatch.setattr(sep, "_run", fake_run)
    out = sep.separate(song, tmp_path, stem="vocals", fmt="wav", bit_depth="32f")
    mix = load_audio(song, SR)
    std = mix.mean(0).std()
    mean = mix.mean(0).mean()
    inst = load_audio(out["instrumental"], SR)
    expected = (levels["drums"] + levels["bass"] + levels["other"]) * std + mean
    assert np.allclose(inst, expected, atol=1e-3)


def test_default_split_is_vocals_drums_instrumental(song, tmp_path, monkeypatch):
    sep = FakeSeparator("cpu")
    model = sep.load_model("htdemucs")
    levels = {"drums": 0.1, "bass": 0.2, "other": 0.05, "vocals": 0.3}
    monkeypatch.setattr(sep, "_run", lambda m, mix, sh, ov, r: torch.stack(
        [torch.full_like(mix, levels[s]) for s in model.sources]))
    out = sep.separate(song, tmp_path, fmt="wav", bit_depth="32f")
    assert list(out) == ["vocals", "drums", "instrumental"]
    mix = load_audio(song, SR)
    std, mean = mix.mean(0).std(), mix.mean(0).mean()
    inst = load_audio(out["instrumental"], SR)
    assert np.allclose(inst, (0.2 + 0.05) * std + mean, atol=1e-3)  # basso + altro


def test_mid_side(song, tmp_path):
    sep = FakeSeparator("cpu")
    out = sep.separate(song, tmp_path, stem="vocals", fmt="wav", bit_depth="32f", midside="stems")
    assert list(out) == ["vocals", "instrumental", "vocals_mid", "vocals_side",
                         "instrumental_mid", "instrumental_side", "mix_mid", "mix_side"]
    for name in ("vocals", "instrumental"):
        lr = load_audio(out[name], SR)
        mid, side = load_audio(out[f"{name}_mid"], SR, 1)[0], load_audio(out[f"{name}_side"], SR, 1)[0]
        assert np.allclose(mid + side, lr[0], atol=1e-5)  # L = M + S
        assert np.allclose(mid - side, lr[1], atol=1e-5)  # R = M - S
    mix = load_audio(song, SR)
    mix_side = load_audio(out["mix_side"], SR, 1)[0]
    assert np.allclose(mix_side, (mix[0] - mix[1]) / 2, atol=1e-5)

    only_mix = sep.separate(song, tmp_path / "b", stem="vocals", midside="mix")
    assert list(only_mix) == ["vocals", "instrumental", "mix_mid", "mix_side"]


def test_api(song, tmp_path):
    from fastapi.testclient import TestClient

    from stem_splitter.server import create_app

    client = TestClient(headers={"X-Stem-Splitter": "1"}, app=create_app(FakeSeparator("cpu"), tmp_path / "jobs"))
    info = client.get("/api/info").json()
    assert info["device"] == "cpu" and "vocals" in [s["key"] for s in info["stems"]]
    assert client.get("/").status_code == 200

    with open(song, "rb") as f:
        r = client.post("/api/jobs", files={"file": ("My Song.mp3", f, "audio/mpeg")},
                        data={"stem": "drums", "format": "flac", "samplerate": "96000",
                              "bit_depth": "24", "midside": "mix"})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    for _ in range(300):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    assert [s["name"] for s in job["stems"]] == ["drums", "no_drums", "mix_mid", "mix_side"]
    assert job["samplerate"] == 96000
    r = client.get(job["stems"][0]["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "audio/flac"
    assert 'My%20Song%20-%20drums.flac' in r.headers["content-disposition"]
    r = client.get(f"/api/jobs/{job_id}/zip")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/jobs/{job_id}").status_code == 404

    r = client.post("/api/jobs", files={"file": ("a.mp3", b"x", "audio/mpeg")},
                    data={"format": "mp3", "samplerate": "96000"})
    assert r.status_code == 400 and "48 kHz" in r.json()["detail"]
    assert client.post("/api/jobs", files={"file": ("a.mp3", b"x")}, data={"samplerate": "22050"}).status_code == 400
    assert client.post("/api/jobs", files={"file": ("a.mp3", b"x")}, data={"quality": "ultra"}).status_code == 400

    bad = client.post("/api/jobs", files={"file": ("x.mp3", b"not audio", "audio/mpeg")})
    assert bad.status_code == 200
    for _ in range(100):
        job = client.get(f"/api/jobs/{bad.json()['id']}").json()
        if job["status"] in ("done", "error"):
            break
        time.sleep(0.1)
    assert job["status"] == "error"


# --- regressioni dalla code review -------------------------------------------------------


def _const_run(model, levels):
    return lambda m, mix, sh, ov, r: torch.stack([mix * levels[s] for s in model.sources])


def test_common_gain_keeps_stems_and_mid_side_consistent(song, tmp_path, monkeypatch):
    """Con uscita intera, un solo guadagno per tutti i file: le somme e M/S restano valide."""
    sep = FakeSeparator("cpu")
    model = sep.load_model("htdemucs")
    # stem molto forti: senza guadagno comune il clipping/normalizzazione per file è certo
    levels = {"drums": 3.0, "bass": 2.0, "other": 1.0, "vocals": 0.5}
    monkeypatch.setattr(sep, "_run", _const_run(model, levels))
    out = sep.separate(song, tmp_path, stem="vocals", fmt="wav", bit_depth="24", midside="stems")
    v, i = load_audio(out["vocals"], SR), load_audio(out["instrumental"], SR)
    assert np.abs(i).max() < 1.0 and np.abs(v).max() < 1.0
    # rapporto tra stem invariato (3+2+1 = 6 volte la voce)
    ratio = np.abs(i).max() / np.abs(v).max()
    assert abs(ratio - 12.0) < 0.05, ratio
    mid = load_audio(out["instrumental_mid"], SR, 1)[0]
    side = load_audio(out["instrumental_side"], SR, 1)[0]
    assert np.allclose(mid + side, i[0], atol=1e-4) and np.allclose(mid - side, i[1], atol=1e-4)


def test_float_output_keeps_original_level(song, tmp_path, monkeypatch):
    sep = FakeSeparator("cpu")
    model = sep.load_model("htdemucs")
    monkeypatch.setattr(sep, "_run", _const_run(model, {"drums": 3.0, "bass": 0, "other": 0, "vocals": 0}))
    out = sep.separate(song, tmp_path, stem="drums", fmt="wav", bit_depth="32f")
    assert np.abs(load_audio(out["drums"], SR)).max() > 1.0  # il float conserva gli over


@pytest.mark.parametrize("rate", [48000, 96000])
def test_no_clipping_after_resampling(tmp_path, monkeypatch, rate):
    """Un'onda quadra quasi a fondo scala genera over inter-campione nel ricampionamento."""
    t = np.arange(SR * 3) / SR
    sq = (0.999 * np.sign(np.sin(2 * np.pi * 997 * t))).astype(np.float32)
    src = save_audio(np.stack([sq, sq]), tmp_path / "sq", SR, "wav", bit_depth="32f")
    sep = FakeSeparator("cpu")
    model = sep.load_model("htdemucs")
    levels = {"drums": 0, "bass": 0, "other": 0, "vocals": 1.0}
    monkeypatch.setattr(sep, "_run", _const_run(model, levels))
    out = sep.separate(src, tmp_path / "o", stem="vocals", fmt="wav", samplerate=rate, bit_depth="24")
    raw = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(out["vocals"]), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    peak = np.abs(np.frombuffer(raw, np.float32)).max()
    assert peak < 0.9999, peak  # nessun campione bloccato a fondo scala


def _wait(client, job_id, statuses=("done", "error"), timeout=30):
    for _ in range(int(timeout * 10)):
        r = client.get(f"/api/jobs/{job_id}")
        if r.status_code == 404 or r.json()["status"] in statuses:
            return r
        time.sleep(0.1)
    raise AssertionError("timeout")


def test_zip_is_written_to_disk_not_memory(song, tmp_path):
    from fastapi.testclient import TestClient

    from stem_splitter.server import create_app

    client = TestClient(headers={"X-Stem-Splitter": "1"}, app=create_app(FakeSeparator("cpu"), tmp_path / "jobs"))
    with open(song, "rb") as f:
        job_id = client.post("/api/jobs", files={"file": ("s.mp3", f)}).json()["id"]
    _wait(client, job_id)
    r = client.get(f"/api/jobs/{job_id}/zip")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert list((tmp_path / "jobs" / job_id).glob("*.zip"))  # file su disco, riusato


def test_old_job_dirs_are_purged(tmp_path):
    import os

    from stem_splitter.jobs import JobManager

    work = tmp_path / "jobs"
    old, new = work / "oldjob", work / "newjob"
    old.mkdir(parents=True)
    new.mkdir()
    (old / "input.mp3").write_bytes(b"x")
    past = time.time() - 3 * 24 * 3600
    os.utime(old, (past, past))
    JobManager(FakeSeparator("cpu"), work, ttl_hours=24)
    assert not old.exists() and new.exists()


class SlowSeparator(FakeSeparator):
    def _run(self, model, mix, shifts, overlap, report):
        for i in range(200):
            time.sleep(0.05)
            report(0.08 + 0.004 * i, "lento")
        return torch.stack([mix] * len(model.sources))


def test_delete_cancels_running_job(song, tmp_path):
    from fastapi.testclient import TestClient

    from stem_splitter.server import create_app

    work = tmp_path / "jobs"
    client = TestClient(headers={"X-Stem-Splitter": "1"}, app=create_app(SlowSeparator("cpu"), work))
    with open(song, "rb") as f:
        slow = client.post("/api/jobs", files={"file": ("a.mp3", f)}).json()["id"]
    with open(song, "rb") as f:
        nxt = client.post("/api/jobs", files={"file": ("b.mp3", f)}).json()["id"]
    _wait(client, slow, statuses=("running",))
    time.sleep(0.3)
    start = time.time()
    assert client.delete(f"/api/jobs/{slow}").status_code == 200
    # il lavoro successivo parte subito invece di aspettare i ~10 s del primo
    _wait(client, nxt, statuses=("running", "done"), timeout=5)
    assert time.time() - start < 3
    for _ in range(30):
        if not (work / slow).exists():
            break
        time.sleep(0.1)
    assert not (work / slow).exists()


def test_mutating_requests_need_app_header(song, tmp_path):
    """Un altro sito non può caricare file o chiudere l'app (serve un header non semplice)."""
    from fastapi.testclient import TestClient

    from stem_splitter.server import create_app

    closed = []
    client = TestClient(create_app(FakeSeparator("cpu"), tmp_path / "jobs", on_shutdown=lambda: closed.append(1)))
    with open(song, "rb") as f:
        assert client.post("/api/jobs", files={"file": ("a.mp3", f)}).status_code == 403
    assert client.post("/api/shutdown").status_code == 403
    assert client.delete("/api/jobs/x").status_code == 403
    assert not closed and client.get("/api/info").json()["can_shutdown"] is True
    assert client.post("/api/shutdown", headers={"X-Stem-Splitter": "1"}).status_code == 200
    assert closed == [1]


def test_shutdown_unavailable_without_launcher(tmp_path):
    from fastapi.testclient import TestClient

    from stem_splitter.server import create_app

    client = TestClient(create_app(FakeSeparator("cpu"), tmp_path / "jobs"), headers={"X-Stem-Splitter": "1"})
    assert client.get("/api/info").json()["can_shutdown"] is False
    assert client.post("/api/shutdown").status_code == 404


def test_app_self_test():
    """Lo stesso controllo che la CI esegue sugli installer, qui senza congelamento."""
    from stem_splitter.app import self_test

    assert self_test() == 0
