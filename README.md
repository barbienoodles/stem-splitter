# Stem Splitter

Separa qualsiasi brano in stem (voce, batteria, basso, chitarra, piano, altro), in stile LALAL.AI,
ma **in locale sul tuo computer**: nessun upload su server esterni, nessun limite di minuti.

Funziona su:

| Computer | Dispositivo usato | Note |
|---|---|---|
| Mac **Apple Silicon** (M1/M2/M3/M4…) | GPU via Metal (MPS) | le operazioni non supportate da MPS ricadono automaticamente sulla CPU |
| Mac **Intel** | CPU (tutti i core) | richiede Python 3.10–3.12 (ultima PyTorch per Mac Intel: 2.2.x) |
| Linux / Windows | GPU NVIDIA (CUDA) se presente, altrimenti CPU | |

Il motore di separazione è [Demucs](https://github.com/facebookresearch/demucs) (Hybrid Transformer Demucs, licenza MIT).

## Installazione (Mac)

```bash
git clone https://github.com/barbienoodles/stem-splitter.git
cd stem-splitter
./scripts/install.sh
```

Lo script rileva Intel o Apple Silicon e sceglie il Python giusto. Se manca Python:
`brew install python@3.12`. ffmpeg non serve: è incluso tramite `imageio-ffmpeg`.

Al primo utilizzo i pesi del modello (~80 MB per htdemucs, ~320 MB per la qualità alta)
vengono scaricati automaticamente e salvati in cache.

## Uso

### Interfaccia web

```bash
./scripts/start.sh
```

oppure doppio clic su **`Stem Splitter.command`** nel Finder. Si apre il browser su
`http://localhost:8000`:

1. scegli cosa estrarre: di default **voce + batteria + strumentale**, oppure voce, batteria,
   basso, chitarra, piano, 4 stem, 6 stem;
2. scegli profondità di calcolo, formato, frequenza di campionamento, profondità in bit e Mid/Side;
3. trascina uno o più file (qualsiasi audio o video: MP3, MP4, WAV, AAC, M4A, FLAC, AIFF, OGG,
   OPUS, WMA, MOV, MKV…; da un video viene presa la traccia audio). Al termine puoi ascoltare
   gli stem in sincrono con mute/solo/volume, cliccare sulla forma d'onda per spostarti e
   scaricare i singoli file o lo zip.

### Opzioni di uscita

| Opzione | Valori | Note |
|---|---|---|
| Profondità di calcolo | Veloce · Alta · Massima | Alta = modello fine-tuned (`htdemucs_ft`, ~4x); Massima = fine-tuned + 2 passaggi + 50% di sovrapposizione (~12x) |
| Formato | WAV · FLAC · MP3 320 kbps | |
| Frequenza di campionamento | 44,1 · 48 · 96 kHz | MP3 al massimo 48 kHz |
| Profondità in bit | 16 · 24 · 32 bit float | 32 float solo WAV (conserva i picchi oltre 0 dBFS); 16 bit con dither TPDF |
| Mid/Side | No · del mix · del mix e di ogni stem | stile iZotope Ozone: Mid = (L+R)/2, Side = (L−R)/2, file mono; L = M+S, R = M−S |

I modelli Demucs lavorano internamente a 44,1 kHz: a 48/96 kHz l'uscita viene ricampionata
con SoX VHQ (libsoxr), quindi gli stem non contengono frequenze oltre ~22 kHz.

### Riga di comando

```bash
.venv/bin/stem-splitter split canzone.mp3                      # voce, batteria, strumentale
.venv/bin/stem-splitter split video.mp4 --stem vocals --format mp3 -r 48000
.venv/bin/stem-splitter split *.flac --stem all4 -q max -f flac -r 96000 -b 24 --midside stems -o stems/
```

| Opzione `--stem` | File prodotti |
|---|---|
| `vocals_drums` (default) | `vocals`, `drums`, `instrumental` |
| `vocals` | `vocals`, `instrumental` |
| `drums` / `bass` | lo stem + `no_drums` / `no_bass` |
| `guitar` / `piano` | lo stem + `no_guitar` / `no_piano` (modello a 6 stem) |
| `all4` | `vocals`, `drums`, `bass`, `other` |
| `all6` | `vocals`, `drums`, `bass`, `guitar`, `piano`, `other` |

Con `--midside mix` si aggiungono `mix_mid` e `mix_side`; con `--midside stems` anche
`<stem>_mid` e `<stem>_side` per ogni stem.

`-q high|max` usa `htdemucs_ft` (per chitarra/piano si usa sempre `htdemucs_6s`, con più passaggi in `max`).
`--shifts N` forza il numero di passaggi.

### Forzare il dispositivo

```bash
.venv/bin/stem-splitter --device cpu serve
STEM_SPLITTER_DEVICE=mps ./scripts/start.sh
```

Altre variabili: `STEM_SPLITTER_HOME` (cartella dei lavori, default `~/.stem-splitter`),
`STEM_SPLITTER_MAX_MB` (dimensione massima upload, default 200).

## Tempi indicativi (brano di 4 minuti, qualità standard)

Apple Silicon (MPS): circa 20–60 s · Mac Intel recente (CPU): circa 1–3 min.
La qualità alta richiede circa 4 volte tanto.

## Sviluppo

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pip install --no-deps demucs
.venv/bin/pytest
```

Demucs si installa con `--no-deps` perché la 4.1 dipende da `sphn`, che non ha wheel per Mac Intel
e che qui non serve (la lettura dei file la fa ffmpeg). I test sono stati eseguiti sia con lo stack
attuale sia con quello di Mac Intel (Python 3.12, torch 2.2.2, numpy 1.26).

I test usano un piccolo HTDemucs con pesi casuali, quindi non scaricano nulla.

## API

| Metodo | Percorso | Descrizione |
|---|---|---|
| GET | `/api/info` | dispositivo, opzioni disponibili |
| POST | `/api/jobs` | multipart: `file`, `stem`, `quality`, `format`, `samplerate`, `bit_depth`, `midside` |
| GET | `/api/jobs/{id}` | stato, avanzamento, elenco stem |
| GET | `/api/jobs/{id}/stems/{nome}` | scarica uno stem |
| GET | `/api/jobs/{id}/zip` | scarica tutti gli stem |
| DELETE | `/api/jobs/{id}` | elimina il lavoro e i file |
