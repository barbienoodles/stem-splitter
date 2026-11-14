"""Test end-to-end con un HTDemucs piccolo a pesi casuali (nessun download richiesto)."""

import os
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

    client = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs"), headers={"X-Stem-Splitter": "1"})
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

    client = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs"), headers={"X-Stem-Splitter": "1"})
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
    old, new = work / "a1b2c3d4e5f6", work / "0f9e8d7c6b5a"
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
    client = _local_client(create_app(SlowSeparator("cpu"), work), headers={"X-Stem-Splitter": "1"})
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
    client = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs", on_shutdown=lambda: closed.append(1)))
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

    client = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs"), headers={"X-Stem-Splitter": "1"})
    assert client.get("/api/info").json()["can_shutdown"] is False
    assert client.post("/api/shutdown").status_code == 404


def test_app_self_test():
    """Lo stesso controllo che la CI esegue sugli installer, qui senza congelamento."""
    from stem_splitter.app import self_test

    assert self_test() == 0


# --- revisione di sicurezza ---------------------------------------------------------------


def _local_client(app, **kw):
    from fastapi.testclient import TestClient

    kw.setdefault("base_url", "http://127.0.0.1:8765")
    return TestClient(app, **kw)


@pytest.mark.parametrize("host", ["evil.example:8765", "evil.example", "192.168.1.20:8765", "127.0.0.1.evil.example"])
def test_dns_rebinding_hosts_are_rejected(tmp_path, host):
    """Un dominio che punta a 127.0.0.1 (DNS rebinding) non deve poter usare l'API."""
    from stem_splitter.server import create_app

    closed = []
    c = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs", on_shutdown=lambda: closed.append(1)),
                      headers={"X-Stem-Splitter": "1", "Host": host})
    assert c.get("/api/jobs").status_code == 400
    assert c.get("/").status_code == 400
    assert c.post("/api/shutdown").status_code == 400
    assert not closed


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "[::1]:8765", "localhost", "LOCALHOST:8765"])
def test_local_hosts_are_accepted(tmp_path, host):
    from stem_splitter.server import create_app

    c = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs"), headers={"Host": host})
    assert c.get("/api/info").status_code == 200


def test_explicit_lan_host_can_be_allowed(tmp_path):
    from stem_splitter.server import create_app

    app = create_app(FakeSeparator("cpu"), tmp_path / "jobs", allowed_hosts=["192.168.1.20"])
    assert _local_client(app, headers={"Host": "192.168.1.20:8765"}).get("/api/info").status_code == 200
    assert _local_client(app, headers={"Host": "evil.example"}).get("/api/info").status_code == 400


def test_purge_only_touches_its_own_files(tmp_path):
    """La pulizia automatica non deve cancellare file dell'utente nella stessa cartella."""
    import os

    from stem_splitter.jobs import JobManager

    work = tmp_path / "jobs"
    work.mkdir()
    past = time.time() - 3 * 24 * 3600
    foreign = [work / "tesi.docx", work / "Foto", work / "abcdef"]
    foreign[0].write_text("importante")
    foreign[1].mkdir()
    foreign[2].mkdir()
    ours = [work / "0123456789ab", work / "tmpk3j2h1.upload"]
    ours[0].mkdir()
    ours[1].write_bytes(b"x")
    for p in foreign + ours:
        os.utime(p, (past, past))
    JobManager(FakeSeparator("cpu"), work, ttl_hours=24)
    assert all(p.exists() for p in foreign)
    assert not any(p.exists() for p in ours)


def test_download_names_are_sanitized(song, tmp_path):
    """Nomi con separatori o caratteri speciali non devono diventare percorsi nello zip."""
    import io
    import zipfile

    from stem_splitter.server import create_app

    c = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs"), headers={"X-Stem-Splitter": "1"})
    with open(song, "rb") as f:
        job_id = c.post("/api/jobs", files={"file": ('..\\..\\Start "x"<>|?*:.mp3', f)},
                        data={"stem": "vocals"}).json()["id"]
    _wait(c, job_id)
    names = zipfile.ZipFile(io.BytesIO(c.get(f"/api/jobs/{job_id}/zip").content)).namelist()
    assert names and all(not set('\\/:*?"<>|') & set(n) for n in names), names
    cd = c.get(f"/api/jobs/{job_id}/stems/vocals").headers["content-disposition"]
    assert "%5C" not in cd and "\\" not in cd, cd


# --- Banana Split: cartella di destinazione ---------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Nessun test deve toccare la vera cartella dell'utente (impostazioni, Musica)."""
    home = tmp_path / "home"
    (home / "Music").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("BANANA_SPLIT_HOME", str(home / ".banana-split"))
    return home


def _app_client(tmp_path, sep=None):
    from stem_splitter.server import create_app

    return _local_client(create_app(sep or FakeSeparator("cpu"), tmp_path / "jobs"),
                         headers={"X-Stem-Splitter": "1"})


def test_settings_default_and_update(tmp_path, _isolated_home):
    c = _app_client(tmp_path)
    s = c.get("/api/settings").json()
    assert s["output_dir"] == str(_isolated_home / "Music" / "Banana Split")
    assert s["output_dir_short"] == "~" + os.sep + os.path.join("Music", "Banana Split")
    assert s["save_to_folder"] is True
    dest = tmp_path / "Stem miei"
    s = c.post("/api/settings", json={"output_dir": str(dest), "save_to_folder": False}).json()
    assert s["output_dir"] == str(dest) and dest.is_dir() and s["save_to_folder"] is False
    assert s["output_dir_short"] == str(dest)  # fuori dalla cartella personale: percorso completo
    # ricordata al riavvio (nuovo server)
    assert _app_client(tmp_path).get("/api/settings").json()["output_dir"] == str(dest)


@pytest.mark.parametrize("bad,msg", [("relativa/cartella", "percorso completo"), ("/non/esiste/proprio", "non esiste"), ("", "Indica")])
def test_settings_reject_bad_paths(tmp_path, bad, msg):
    r = _app_client(tmp_path).post("/api/settings", json={"output_dir": bad})
    assert r.status_code == 400 and msg in r.json()["detail"]


def test_settings_need_app_header(tmp_path):
    from stem_splitter.server import create_app

    c = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs"))
    assert c.post("/api/settings", json={"output_dir": str(tmp_path)}).status_code == 403
    assert c.post("/api/pick-folder").status_code == 403


def test_stems_are_saved_in_chosen_folder(song, tmp_path):
    c = _app_client(tmp_path)
    dest = tmp_path / "uscita"
    c.post("/api/settings", json={"output_dir": str(dest)})
    ids = []
    for _ in range(2):
        with open(song, "rb") as f:
            ids.append(c.post("/api/jobs", files={"file": ("Grazie, Michelina.mp3", f)},
                              data={"save_to_folder": "true", "format": "wav"}).json()["id"])
    jobs = [_wait(c, i).json() for i in ids]
    folders = [Path(j["export_dir"]) for j in jobs]
    assert [f.name for f in folders] == ["Grazie, Michelina - Banana Split", "Grazie, Michelina - Banana Split (2)"]
    assert sorted(p.name for p in folders[0].iterdir()) == [
        "Grazie, Michelina - drums.wav", "Grazie, Michelina - instrumental.wav", "Grazie, Michelina - vocals.wav"]
    assert all(f.parent == dest for f in folders)


def test_no_folder_copy_when_disabled(song, tmp_path):
    c = _app_client(tmp_path)
    c.post("/api/settings", json={"output_dir": str(tmp_path / "uscita")})
    with open(song, "rb") as f:
        job = _wait(c, c.post("/api/jobs", files={"file": ("a.mp3", f)}).json()["id"]).json()
    assert job["status"] == "done" and job["export_dir"] is None
    assert not any((tmp_path / "uscita").iterdir())


def test_export_failure_keeps_job_downloadable(song, tmp_path, monkeypatch):
    from stem_splitter import outputs

    def boom(*a, **k):
        raise OSError("disco pieno")

    monkeypatch.setattr(outputs, "export_stems", boom)
    c = _app_client(tmp_path)
    with open(song, "rb") as f:
        job = _wait(c, c.post("/api/jobs", files={"file": ("a.mp3", f)}, data={"save_to_folder": "true"}).json()["id"]).json()
    assert job["status"] == "done" and "disco pieno" in job["export_error"]
    assert c.get(job["stems"][0]["url"]).status_code == 200


def test_pick_folder_and_reveal(song, tmp_path, monkeypatch):
    from stem_splitter import outputs

    chosen = tmp_path / "scelta"
    chosen.mkdir()
    revealed = []
    c = _app_client(tmp_path)

    monkeypatch.setattr(outputs, "pick_folder", lambda initial=None: chosen)
    assert c.post("/api/pick-folder").json()["output_dir"] == str(chosen)
    monkeypatch.setattr(outputs, "pick_folder", lambda initial=None: None)
    r = c.post("/api/pick-folder").json()
    assert r["cancelled"] is True and r["output_dir"] == str(chosen)

    def unavailable(initial=None):
        raise outputs.PickerUnavailable("niente finestra")

    monkeypatch.setattr(outputs, "pick_folder", unavailable)
    assert c.post("/api/pick-folder").status_code == 501

    monkeypatch.setattr(outputs, "reveal", lambda p: revealed.append(p))
    with open(song, "rb") as f:
        job = _wait(c, c.post("/api/jobs", files={"file": ("b.mp3", f)}, data={"save_to_folder": "true"}).json()["id"]).json()
    assert c.post(f"/api/jobs/{job['id']}/reveal").status_code == 200
    assert revealed == [Path(job["export_dir"])] and revealed[0].parent == chosen


def test_picker_commands_by_platform(monkeypatch, tmp_path):
    """Il comando della finestra di sistema passa il percorso come argomento, mai dentro lo script."""
    from stem_splitter import outputs

    tricky = tmp_path / 'cartella "strana" $(rm -rf)'
    monkeypatch.setattr(outputs.sys, "platform", "darwin")
    monkeypatch.setattr(outputs.shutil, "which", lambda n: "/usr/bin/" + n)
    cmd, _ = outputs._picker_command(tricky)
    assert cmd[0] == "osascript" and cmd[-1] == str(tricky)
    assert all(str(tricky) not in part for part in cmd[:-1])
    monkeypatch.setattr(outputs.sys, "platform", "win32")
    cmd, extra = outputs._picker_command(tricky)
    assert extra["env"]["BANANA_INITIAL"] == str(tricky) and all(str(tricky) not in p for p in cmd)
    monkeypatch.setattr(outputs.sys, "platform", "linux")
    monkeypatch.setattr(outputs.shutil, "which", lambda n: None)
    assert outputs._picker_command(tricky) is None


# --- pulsante "Dove salvo gli stem?": apertura della cartella corrente ------------------


def test_reveal_output_folder_creates_and_opens_it(tmp_path, _isolated_home, monkeypatch):
    from stem_splitter import outputs

    opened = []
    monkeypatch.setattr(outputs, "reveal", lambda p: opened.append(p))
    c = _app_client(tmp_path)
    r = c.post("/api/reveal-output")
    assert r.status_code == 200
    expected = _isolated_home / "Music" / "Banana Split"
    assert opened == [expected] and expected.is_dir()
    # senza l'header dell'app non si può chiedere di aprire cartelle
    from stem_splitter.server import create_app

    bare = _local_client(create_app(FakeSeparator("cpu"), tmp_path / "jobs2"))
    assert bare.post("/api/reveal-output").status_code == 403


def test_reveal_without_file_manager_is_a_clean_error(tmp_path, monkeypatch):
    from stem_splitter import outputs

    def no_opener(*a, **k):
        raise FileNotFoundError("xdg-open")

    monkeypatch.setattr(outputs.subprocess, "Popen", no_opener)
    with pytest.raises(RuntimeError, match="aprire la cartella"):
        outputs.reveal(tmp_path)
    assert _app_client(tmp_path).post("/api/reveal-output").status_code == 501


# --- sicurezza: niente codice eseguito da file manomessi -------------------------------


def _fake_model_setup(monkeypatch, tmp_path):
    from stem_splitter import weights

    good = b"modello buono"
    import hashlib
    monkeypatch.setattr(weights, "FILES", {"m": ["aaaa-bbbb.th"]})
    monkeypatch.setattr(weights, "SHA256", {"aaaa-bbbb.th": hashlib.sha256(good).hexdigest()})
    monkeypatch.setattr(weights, "cache_dir", lambda: tmp_path / "hub")
    return weights, good


def test_tampered_model_in_cache_is_replaced(monkeypatch, tmp_path):
    weights, good = _fake_model_setup(monkeypatch, tmp_path)
    (tmp_path / "hub").mkdir()
    (tmp_path / "hub" / "aaaa-bbbb.th").write_bytes(b"pickle con un trojan")
    downloads = []
    monkeypatch.setattr(weights, "_download", lambda url, dest: (downloads.append(url), dest.write_bytes(good)))
    [path] = weights.ensure_model_files("m")
    assert path.read_bytes() == good and len(downloads) == 1


def test_bad_download_is_rejected_and_never_cached(monkeypatch, tmp_path):
    weights, _ = _fake_model_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(weights, "_download", lambda url, dest: dest.write_bytes(b"file diverso"))
    with pytest.raises(weights.ModelIntegrityError, match="non corrisponde"):
        weights.ensure_model_files("m")
    assert not any((tmp_path / "hub").iterdir())  # né il file né il temporaneo


def test_good_cached_model_is_not_downloaded_again(monkeypatch, tmp_path):
    weights, good = _fake_model_setup(monkeypatch, tmp_path)
    (tmp_path / "hub").mkdir()
    (tmp_path / "hub" / "aaaa-bbbb.th").write_bytes(good)
    monkeypatch.setattr(weights, "_download", lambda *a: (_ for _ in ()).throw(AssertionError("download inutile")))
    assert weights.ensure_model_files("m")[0].read_bytes() == good


def test_pinned_hashes_cover_every_model_and_match_names():
    from stem_splitter import weights
    from stem_splitter.separator import QUALITIES, STEM_OPTIONS

    used = {q.plan(six)[0] for q in QUALITIES.values() for six in (False, True)}
    assert used <= set(weights.FILES)
    for files in weights.FILES.values():
        for f in files:
            assert weights.SHA256[f].startswith(f.split("-")[1].split(".")[0])  # prefisso ufficiale
            assert len(weights.SHA256[f]) == 64


def test_media_file_cannot_make_ffmpeg_use_the_network(tmp_path, monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    hits = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    port = srv.server_address[1]
    evil = tmp_path / "canzone.mp3"
    evil.write_text(f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttp://127.0.0.1:{port}/spia.ts\n#EXT-X-ENDLIST\n")
    with pytest.raises(ValueError):
        load_audio(evil, SR)
    srv.shutdown()
    assert hits == []


@pytest.mark.parametrize("name", ["Evil.app", "Strumento.command", "Plugin.bundle"])
def test_app_bundles_are_never_output_folders_or_opened(tmp_path, monkeypatch, name):
    from stem_splitter import outputs

    pkg = tmp_path / name
    pkg.mkdir()
    r = _app_client(tmp_path).post("/api/settings", json={"output_dir": str(pkg)})
    assert r.status_code == 400 and "applicazione" in r.json()["detail"]
    launched = []
    monkeypatch.setattr(outputs.subprocess, "Popen", lambda *a, **k: launched.append(a))
    with pytest.raises(RuntimeError, match="non è una cartella normale"):
        outputs.reveal(pkg)
    # anche se qualcuno scrivesse a mano il percorso nelle impostazioni
    outputs.save_settings(output_dir=str(pkg))
    assert _app_client(tmp_path).post("/api/reveal-output").status_code in (400, 501)
    assert launched == []
