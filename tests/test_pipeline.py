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

    client = TestClient(create_app(FakeSeparator("cpu"), tmp_path / "jobs"))
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
