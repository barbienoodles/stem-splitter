# Tonalità e velocità per stem — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cursori Tonalità (±12 st) e Velocità (50–150%) con preascolto prima di separare; file finali elaborati sorgente per sorgente con Signalsmith Stretch (MIT), qualità ≥ Rubber Band R3 al test cieco.

**Architecture:** Signalsmith Stretch vendorizzato e compilato in una piccola libreria nativa (C API + `ctypes`) usata dal separatore su ogni sorgente del modello prima della somma negli stem, con un profilo per sorgente (voce: formanti; batteria: niente trasposizione; resto: tonale). Il preascolto usa la build WASM ufficiale nel browser; dove manca AudioWorklet, il server rende un tratto con la libreria nativa. Il brano si carica una volta (`/api/uploads`) e "Separa" riusa il caricamento.

**Tech Stack:** C++17 + CMake, Python 3.12 `ctypes`/numpy, FastAPI, JS vanilla + Web Audio, PyInstaller, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-23-pitch-tempo-design.md`

## Global Constraints

- Tonalità: interi da −12 a +12 semitoni. Velocità: da 0.50 a 1.50 (UI in %, passo 1%).
- Tonalità 0 e velocità 1.0 ⇒ motore **mai invocato**, output **bit-identico** a oggi.
- Durata d'uscita di ogni traccia = `round(n_campioni / velocità)` esatti (a 44,1 kHz, prima del ricampionamento).
- Batteria (`drums`): tonalità ignorata, solo velocità.
- Nessun codice o binario GPL nell'app; Rubber Band solo nello strumento di test.
- macOS Intel: deployment target **10.13**; installer al massimo **+2 MB** per piattaforma.
- Signalsmith Stretch al commit `88061fd4eda56a2353c5d65c74aa3f4ccf76f9da`, signalsmith-linear al tag `0.6.6`, in `third_party/` con i LICENSE.
- Nomi file con impostazioni non di default: `vocals (+2 st, 90%).wav`; con default i nomi restano `vocals.wav`.
- Testi dell'interfaccia in italiano; percorso a frecce `① Scegli il brano → ② Ascolta e regola → ③ Separa`.
- Nessun rilascio (tag) finché il test cieco (Task 4) non è superato dall'utente.

## Review Focus

- Brano cortissimo (0,2 s, più corto di un blocco del motore): niente crash, lunghezza esatta.
- Silenzio digitale e valori estremi (+12 st a 50%, −12 st a 150%): uscita finita (niente NaN/Inf), picchi gestiti dal guadagno anti-clip unico.
- Uscita a 96 kHz con tonalità/velocità attive: durata = `round(n/velocità)` ricampionata, nessun campione perso.
- Lavoro annullato mentre il motore elabora: si ferma tra una sorgente e l'altra, cartella ripulita.
- `upload_id` sconosciuto, già usato o scaduto: 404 chiaro, nessun file orfano.

---

### Task 1: Signalsmith vendorizzato + libreria nativa `bs_stretch`

**Files:**
- Create: `third_party/signalsmith-stretch/` (header, `include/`, `LICENSE.txt` al commit fissato), `third_party/signalsmith-linear/` (tag 0.6.6 con LICENSE), `third_party/README.md` (provenienza + commit)
- Create: `native/bs_stretch.cpp`, `native/CMakeLists.txt`, `scripts/build_native.py`
- Create: `stem_splitter/stretch.py`
- Test: `tests/test_stretch.py`
- Modify: `README.md` (crediti: Signalsmith Stretch, MIT), `.gitignore` (cartella `build/native`)

**Interfaces:**
- Produces (C): `int bs_process(const float* in, int channels, int64_t frames, double samplerate, double semitones, double tempo, int profile, float* out, int64_t out_frames)` — campioni interleaved; ritorna 0 se ok. `profile`: 0 = mix, 1 = vocals, 2 = drums, 3 = tonal.
- Produces (Python, `stem_splitter/stretch.py`):
  - `PROFILES = {"mix": 0, "vocals": 1, "drums": 2, "tonal": 3}`
  - `profile_for(source: str) -> str` — `"vocals"`→`"vocals"`, `"drums"`→`"drums"`, altro→`"tonal"`.
  - `is_identity(semitones: int, tempo: float) -> bool`
  - `stretch(audio: np.ndarray, samplerate: int, semitones: int, tempo: float, profile: str = "mix") -> np.ndarray` — `audio` float32 `[canali, n]`; ritorna float32 `[canali, round(n/tempo)]`; con identità ritorna `audio` stesso oggetto; `ValueError` fuori range.
  - `available() -> bool` e `library_path() -> Path` (cerca la libreria accanto al pacchetto: `stem_splitter/_native/` sia in sviluppo che in PyInstaller).
- `scripts/build_native.py`: `cmake -S native -B build/native -DCMAKE_BUILD_TYPE=Release` + build, copia `libbs_stretch.{so,dylib}` / `bs_stretch.dll` in `stem_splitter/_native/`.

- [ ] **Step 1: Vendorizza** le due librerie ai commit fissati (copia dei file, niente submodule), scrivi `third_party/README.md`.
- [ ] **Step 2: Test che falliscono** in `tests/test_stretch.py`:

```python
SR = 44100
def sine(f, sec=3.0, ch=2): t = np.arange(int(SR*sec))/SR; return np.tile(0.3*np.sin(2*np.pi*f*t), (ch,1)).astype(np.float32)
def peak_hz(x): s = np.abs(np.fft.rfft(x[0]*np.hanning(x.shape[1]))); return np.argmax(s)*SR/x.shape[1]

def test_identity_is_untouched(): x = sine(440); assert stretch(x, SR, 0, 1.0) is x
@pytest.mark.parametrize("tempo", [0.5, 0.8, 1.2, 1.5])
def test_length_exact(tempo): assert stretch(sine(440), SR, 0, tempo).shape == (2, round(SR*3/tempo))
@pytest.mark.parametrize("st", [-12, -3, 2, 5, 12])
def test_pitch_shift_tonal(st): assert abs(peak_hz(stretch(sine(440), SR, st, 1.0, "tonal")) / (440*2**(st/12)) - 1) < 0.01
def test_drums_ignore_pitch(): assert abs(peak_hz(stretch(sine(440), SR, 5, 1.0, "drums")) / 440 - 1) < 0.01
def test_vocals_shift_pitch(): assert abs(peak_hz(stretch(sine(220), SR, 3, 1.0, "vocals")) / (220*2**(3/12)) - 1) < 0.01
def test_very_short_input(): assert stretch(sine(440, 0.2), SR, 4, 0.7).shape == (2, round(SR*0.2/0.7))
def test_silence_and_extremes_finite():
    for st, tp in [(12, 0.5), (-12, 1.5)]:
        assert np.isfinite(stretch(np.zeros((2, SR), np.float32), SR, st, tp)).all()
        assert np.isfinite(stretch(sine(80), SR, st, tp)).all()
@pytest.mark.parametrize("st,tp", [(13, 1.0), (0, 0.49), (0, 1.51), (1.5, 1.0)])
def test_out_of_range(st, tp): pytest.raises(ValueError, stretch, sine(440), SR, st, tp)
```

- [ ] **Step 3: Esegui** `.venv/bin/python -m pytest tests/test_stretch.py -q` → FAIL (modulo mancante).
- [ ] **Step 4: Implementa** `bs_stretch.cpp` (un `SignalsmithStretch<float>` per chiamata, `presetDefault`; profilo vocals: `setFormantSemitones(0, true)`; drums: semitoni forzati a 0; tonal/mix: parametri di default, da rifinire nel Task 4; latenza gestita con `seek`/`process`/`flush` così l'uscita è allineata e lunga esattamente `out_frames`), `CMakeLists.txt` (libreria condivisa, C++17, `-O2`, simboli C esportati, include dei due vendor), `build_native.py`, `stretch.py` (ctypes, conversione interleaved).
- [ ] **Step 5: Compila ed esegui** `python scripts/build_native.py && .venv/bin/python -m pytest tests/test_stretch.py -q` → PASS; poi tutta la suite → PASS.
- [ ] **Step 6: Commit** `git add third_party native scripts stem_splitter/stretch.py tests/test_stretch.py README.md .gitignore && git commit -m "Motore tonalità/velocità: Signalsmith Stretch vendorizzato + libreria nativa"`

### Task 2: Separatore — elaborazione per sorgente

**Files:**
- Modify: `stem_splitter/separator.py` (`separate`, costanti), `stem_splitter/outputs.py` (`settings_suffix`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `stretch`, `profile_for`, `is_identity` (Task 1).
- Produces: `Separator.separate(..., pitch: int = 0, tempo: float = 1.0, ...)`; costanti `PITCH_RANGE = (-12, 12)`, `TEMPO_RANGE = (0.5, 1.5)` in `separator.py`; `outputs.settings_suffix(pitch: int, tempo: float) -> str` (`""` se identità, altrimenti `" (+2 st, 90%)"`, `" (−3 st)"`, `" (120%)"`; segno `+` esplicito, meno tipografico `−`).

- [ ] **Step 1: Test che falliscono** (con `FakeSeparator` già presente nei test):

```python
def test_default_never_calls_engine(song, tmp_path, monkeypatch):
    monkeypatch.setattr("stem_splitter.stretch.stretch", lambda *a, **k: pytest.fail("chiamato"))
    out = FakeSeparator("cpu").separate(song, tmp_path, fmt="wav")
    assert {p.name for p in out.values()} == {"vocals.wav", "drums.wav", "instrumental.wav"}

def test_pitch_tempo_lengths_and_names(song, tmp_path):
    out = FakeSeparator("cpu").separate(song, tmp_path, fmt="wav", samplerate=96000, pitch=2, tempo=0.9, midside="mix")
    n = load_audio(song, 44100).shape[1]
    assert out["vocals"].name == "vocals (+2 st, 90%).wav"
    for p in out.values(): assert load_audio(p, 96000).shape[1] == round(round(n/0.9) * 96000/44100)

class SineSeparator(FakeSeparator):  # ogni sorgente = la stessa sinusoide a 440 Hz
    def _run(self, model, mix, shifts, overlap, report):
        return torch.stack([torch.from_numpy(sine(440, mix.shape[1]/SR))] * len(model.sources))

def test_drums_source_not_transposed(song, tmp_path):
    out = SineSeparator("cpu").separate(song, tmp_path, fmt="wav", bit_depth="32f", pitch=5)
    assert abs(peak_hz(load_audio(out["drums"], SR)) / 440 - 1) < 0.01
    assert abs(peak_hz(load_audio(out["vocals"], SR)) / (440*2**(5/12)) - 1) < 0.01

def test_cancel_between_sources(song, tmp_path):
    calls = []
    def progress(p, msg):
        if msg.startswith("Cambio tonalità"):
            calls.append(p)
            if len(calls) == 2: raise JobCancelled()
    with pytest.raises(JobCancelled):
        FakeSeparator("cpu").separate(song, tmp_path, pitch=2, progress=progress)
    assert not list(tmp_path.glob("*.wav"))
def test_pitch_out_of_range(song, tmp_path): pytest.raises(ValueError, FakeSeparator("cpu").separate, song, tmp_path, pitch=13)
```

- [ ] **Step 2: Esegui** → FAIL.
- [ ] **Step 3: Implementa** in `separate`: validazione; se non identità, dopo `_run` sostituisci ogni `by_name[s]` con `stretch(..., profile_for(s))` (nel dominio normalizzato, avanzamento 0.85→0.92 con messaggio "Cambio tonalità e velocità…", `report` chiamato tra le sorgenti così l'annullamento interviene); con tonalità/velocità attive `mix_mid/mix_side` vengono dalla somma delle sorgenti elaborate (`sum(by_name.values()) * std + mean`); il guadagno anti-clip si misura dopo; i file si chiamano `out_name + settings_suffix(...)`.
- [ ] **Step 4: Esegui** la suite → PASS.
- [ ] **Step 5: Commit** `"Separatore: tonalità e velocità per sorgente"`

### Task 3: Lavori, API di caricamento/preascolto, CLI

**Files:**
- Modify: `stem_splitter/jobs.py` (`Job.pitch`, `Job.tempo`, `JobManager.submit`, `JobManager.store_upload/take_upload/purge_expired`), `stem_splitter/server.py`, `stem_splitter/cli.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `separate(pitch, tempo)` (Task 2), `stretch` (Task 1), `load_audio`/`save_audio`.
- Produces (HTTP, tutte con chiave d'avvio; quelle che modificano con `X-Stem-Splitter`):
  - `POST /api/uploads` (multipart `file`) → `{"id", "filename", "duration"}`; file in `workdir/up-<12 hex>/`, scade col TTL esistente.
  - `GET /api/uploads/{id}/preview` → WAV 16 bit 44,1 kHz stereo del brano (decodificato con ffmpeg, cache su disco).
  - `GET /api/uploads/{id}/render?pitch=&tempo=&start=&seconds=` → WAV del tratto elaborato con profilo `mix` (`seconds` ≤ 30); ripiego per browser senza AudioWorklet.
  - `DELETE /api/uploads/{id}`.
  - `POST /api/jobs` accetta **o** `file` **o** `upload_id` (form), più `pitch: int = 0`, `tempo: float = 1.0`; un `upload_id` usato viene consumato (secondo uso → 404). `Job.to_dict()` include `pitch`, `tempo`.
  - CLI `banana-split split --pitch N --tempo F`.

- [ ] **Step 1: Test che falliscono:** upload → preview (WAV valido, durata ≈ `duration`) → job con `upload_id` e `pitch=2,tempo=0.9` → `done` con nomi suffissati; `upload_id` riusato → 404; sconosciuto → 404; `render` con `seconds=31` → 400, con valori validi → WAV di `round(seconds*44100/tempo)` campioni; `pitch=13` o `tempo=2` → 400; upload scaduto (TTL nel passato) rimosso da `purge_expired`; CLI `--pitch 2 --tempo 0.9` passa i valori a `separate`.
- [ ] **Step 2: Esegui** → FAIL.
- [ ] **Step 3: Implementa** (riusa `_store_upload`, `validate_output`, la regex `OWN_ENTRY` estesa al prefisso `up-`).
- [ ] **Step 4: Esegui** la suite → PASS.
- [ ] **Step 5: Commit** `"API: caricamento unico, preascolto e lavori con tonalità/velocità"`

### Task 4: Test cieco contro Rubber Band (tappa di controllo)

**Files:**
- Create: `tools/ab_test.py`, `tools/README.md`

**Interfaces:**
- Consumes: `Separator`, `stretch` (Task 1–2).
- Produces: `python tools/ab_test.py <brano> <cartella_uscita>` → `ab/coppia-01-A.wav`, `…-B.wav`, …, `ab/CHIAVE.txt` (A/B mescolati con seme casuale, chiave separata). Casi: voce e mix × {+2, −3, +5 st a 100%} ∪ {0 st a 80%, 120%}. Rubber Band: `rubberband -3 --formant` (R3, formanti per la voce) sullo **stesso** materiale (stem voce separato / mix ricomposto dalle sorgenti non elaborate) così confrontiamo solo il motore.

- [ ] **Step 1: Scrivi** lo strumento (Rubber Band chiamato come programma esterno; se manca, messaggio con il comando d'installazione; nessuna dipendenza aggiunta all'app).
- [ ] **Step 2: Genera** le coppie su *Grazie Michelina* (prerequisito: permesso dell'utente a installare `rubberband-cli` e le librerie di build in questa sessione) e consegnale all'utente con SendUserFile.
- [ ] **Step 3: Tappa:** l'utente ascolta e risponde con le preferenze. Se il nostro perde in qualche caso: rifinisci i parametri del profilo in `native/bs_stretch.cpp` (blocco/intervallo, `tonalityLimit`, `setFormantBase`), rigenera, ripeti. **Non proseguire ai Task 5–6 finché l'utente non dichiara pari o vittoria.**
- [ ] **Step 4: Commit** `"Strumento di test cieco A/B contro Rubber Band"` (+ eventuali parametri rifiniti, con i test del Task 1 ancora verdi).

### Task 5: Interfaccia — percorso a frecce e preascolto

**Files:**
- Create: `stem_splitter/static/vendor/SignalsmithStretch.js` (copia di `web/release/SignalsmithStretch.js` al commit fissato) + `stem_splitter/static/vendor/LICENSE-signalsmith.txt`
- Create: `stem_splitter/static/preview.js` (classe `Preview`)
- Modify: `stem_splitter/static/index.html`, `app.js`, `style.css`

**Interfaces:**
- Consumes: API del Task 3.
- Produces: `class Preview { constructor(root); async load(uploadId, duration); play(); pause(); seek(sec); setPitch(st); setTempo(t); destroy() }` — AudioWorklet + Signalsmith se `window.AudioWorkletNode` esiste, altrimenti ripiego che chiede a `/render` tratti da 20 s e li accoda.

- [ ] **Step 1:** Markup del percorso `① Scegli il brano → ② Ascolta e regola → ③ Separa` (passo attivo evidenziato, passi fatti con ✓), cursori Tonalità/Velocità con valore e ↺, mini-player, riga "anteprima indicativa: il risultato è elaborato stem per stem", pulsante **Separa 🍌** in fondo alle frecce. Il caricamento ora chiama `/api/uploads` e **non** avvia la separazione; più brani = coda, stesse impostazioni; "Separa" invia `POST /api/jobs` con `upload_id`, `pitch`, `tempo` per ognuno e da lì il flusso (scimmietta, card del lavoro) resta quello di oggi.
- [ ] **Step 2: Verifica nel browser** (Playwright, come negli screenshot precedenti): carica un brano, cambia tonalità, ▶ suona (nessun errore in console), "Separa" produce card con sottotitolo che include `+2 st · 90%`; ripeti con `AudioWorkletNode` disattivato (`delete window.AudioWorkletNode` prima del caricamento) → il ripiego suona. Screenshot del percorso a frecce all'utente.
- [ ] **Step 3: Commit** `"Interfaccia: percorso a frecce, preascolto con tonalità e velocità"`

### Task 6: Pacchetti e CI

**Files:**
- Modify: `.github/workflows/build.yml` (build della libreria nativa con `scripts/build_native.py` nei job test e build; su macOS Intel `MACOSX_DEPLOYMENT_TARGET=10.13` già presente), `packaging/stem_splitter.spec` (`binaries += [(lib, "stem_splitter/_native")]`), `stem_splitter/app.py` (`self_test`)

- [ ] **Step 1: Self-test:** aggiungi in `self_test()` una chiamata `stretch(sinusoide, 44100, 3, 0.9, "vocals")` con verifica di lunghezza e picco, e una separazione di prova con `pitch=2, tempo=0.9`; stampa `"tonalità e velocità: ok"`.
- [ ] **Step 2:** Il passo "Compatibilità con macOS 10.13" esistente deve coprire anche la libreria nativa (minos ≤ 10.13).
- [ ] **Step 3: Push e CI:** tutti e 4 gli installer verdi con `tonalità e velocità: ok` nel log; dimensioni ≤ +2 MB rispetto a v0.2.6 (Linux 193.5, Win 112.6, Mac AS 114.8, Mac Intel 204.0 MB).
- [ ] **Step 4: Commit** `"Pacchetti: libreria nativa tonalità/velocità in tutti gli installer"`, poi PR verso `main` (merge solo su richiesta dell'utente).
