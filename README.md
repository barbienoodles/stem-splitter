# 🍌 Banana Split

Separa qualsiasi brano in stem (voce, batteria, basso, chitarra, piano, altro), in stile LALAL.AI,
ma **in locale sul tuo computer**: nessun upload su server esterni, nessun limite di minuti.

Una scimmietta prende il brano, separa le banane (le mangia) dalle noccioline (le lancia via),
mangia l'ultima banana, fa una scorreggia e… DONE! Gli stem finiscono nella cartella che scegli tu.

*(Fino alla versione 0.1.x si chiamava "Stem Splitter".)*

Funziona su:

| Computer | Dispositivo usato | Note |
|---|---|---|
| Mac **Apple Silicon** (M1/M2/M3/M4…) | GPU via Metal (MPS) | le operazioni non supportate da MPS ricadono automaticamente sulla CPU |
| Mac **Intel** | CPU (tutti i core) | richiede Python 3.10–3.12 (ultima PyTorch per Mac Intel: 2.2.x) |
| Linux / Windows | GPU NVIDIA (CUDA) se presente, altrimenti CPU | |

Il motore di separazione è [Demucs](https://github.com/facebookresearch/demucs) (Hybrid Transformer Demucs, licenza MIT).

## Installazione con l'installer (consigliata)

Scarica il file per il tuo computer dalla pagina **Releases** del repository: non serve installare
Python né altro.

| Sistema | File | Requisiti |
|---|---|---|
| Mac Apple Silicon | `BananaSplit-…-macOS-AppleSilicon.dmg` | macOS 11 o successivo |
| Mac Intel | `BananaSplit-…-macOS-Intel.dmg` | macOS 10.13 High Sierra o successivo |
| Windows 10/11 (64 bit) | `BananaSplit-…-Windows-Setup.exe` | nessun permesso di amministratore |
| Linux (x86_64) | `BananaSplit-…-Linux-x86_64.AppImage` | glibc 2.35+ (Ubuntu 22.04 o più recente) |

- **Mac:** apri il `.dmg` e trascina *Banana Split* in *Applicazioni*. L'app non è firmata con un
  certificato Apple: la prima volta fai **tasto destro → Apri → Apri**. Se macOS dice che è
  «danneggiata» o non offre l'opzione, vai in *Impostazioni di Sistema → Privacy e sicurezza*
  e premi **Apri comunque**.
- **Windows:** avvia il `Setup.exe`. Se compare «Windows ha protetto il PC», clicca
  **Ulteriori informazioni → Esegui comunque**.
- **Linux:** `chmod +x BananaSplit-*.AppImage` e poi avvialo.

L'app apre la pagina nel browser; se è già aperta, la riapre soltanto. Si chiude con il pulsante
**Chiudi l'app** in alto a destra. I lavori temporanei, le impostazioni e il log stanno in `~/.banana-split`.

Gli installer vengono creati da GitHub Actions (`.github/workflows/build.yml`) a ogni push e
pubblicati automaticamente in una Release quando si crea un tag `v*`:

- dal sito: *Releases → Draft a new release → Choose a tag*, scrivi ad esempio `v0.2.0` (*Create new tag*),
  target `main`, poi **Publish release**. Dopo circa 30–40 minuti gli installer compaiono nella Release;
- oppure da terminale: `git tag v0.2.0 && git push origin v0.2.0`.

## Installazione dal codice (Mac e Linux)

```bash
git clone https://github.com/barbienoodles/stem-splitter.git
cd stem-splitter
./scripts/install.sh
```

Lo script rileva Intel o Apple Silicon e sceglie il Python giusto (cercandolo anche nelle cartelle di
Homebrew e di python.org). Se non ne trova uno adatto spiega perché e, se Homebrew funziona,
propone di installarlo. Senza Homebrew: installer *macOS 64-bit universal2* di
[Python 3.12.10](https://www.python.org/downloads/release/python-31210/).
ffmpeg non serve: è incluso tramite `imageio-ffmpeg`.

Se `git` dà l'errore `xcrun: error: invalid active developer path`, mancano gli Strumenti da riga
di comando di Apple: `xcode-select --install` (oppure scarica lo ZIP da GitHub, pulsante *Code*).

Al primo utilizzo i pesi del modello (~80 MB per htdemucs, ~320 MB per la qualità alta)
vengono scaricati automaticamente e salvati in cache.

## Uso

### Interfaccia web

```bash
./scripts/start.sh
```

oppure doppio clic su **`Banana Split.command`** nel Finder. Si apre il browser su
`http://localhost:8000`:

La scimmietta è al centro. **A sinistra** («Cosa separo?») scegli cosa estrarre con un menu a tendina e,
sotto, il Mid/Side; **a destra** («Come separo?») qualità, formato, frequenza e profondità in bit;
**sotto la scimmietta** c'è il pulsante per scegliere la cartella e la **i** con le informazioni.

1. **Cosa separo?** Il menu ha due gruppi, e sotto compare sempre la riga *Ottieni: …* con i file che usciranno:

   | Voce del menu | File ottenuti |
   |---|---|
   | **Più stem insieme** | |
   | Voce + batteria + strumentale (predefinita) | voce, batteria, strumentale (= basso e resto, senza voce né batteria) |
   | 4 stem | voce, batteria, basso, altro |
   | 6 stem (+ chitarra e piano) | voce, batteria, basso, chitarra, piano, altro |
   | **Uno solo, più tutto il resto** | |
   | Voce (karaoke) | voce, strumentale (= tutto tranne la voce) |
   | Batteria · Basso · Chitarra · Piano | lo stem, più «senza …» |

   *Voce (karaoke)* e *Voce + batteria + strumentale* **non** sono la stessa cosa: la prima dà 2 file e lo
   strumentale ha ancora la batteria; la seconda ne dà 3 e lo strumentale non ha né voce né batteria.
2. **Mid/Side** (sotto il menu): nessuno, solo del mix, oppure del mix e di ogni stem;
3. **Come separo?** profondità di calcolo, formato, frequenza di campionamento, profondità in bit;
4. **Dove salvo gli stem?** Il pulsante sotto la scimmietta apre la finestra del sistema (Finder,
   Esplora file, oppure zenity/kdialog su Linux; senza, si scrive il percorso a mano); la freccia ↗
   accanto apre la cartella corrente. La scelta viene ricordata. Di default è `Musica/Banana Split`;
   ogni brano finisce in una sottocartella `<brano> - Banana Split` (mai sovrascritta: se esiste
   diventa `(2)`, `(3)`…). Togliendo la spunta *Copia gli stem nella cartella a fine lavoro* gli stem
   restano solo da scaricare dalla pagina;
5. trascina uno o più file sulla scimmietta, o clicca su di lei (la **i** elenca i formati accettati:
   qualsiasi audio o video; da un video viene presa la traccia audio). Al termine puoi ascoltare
   gli stem in sincrono con mute/solo/volume, cliccare sulla forma d'onda per spostarti,
   aprire la cartella con *Apri cartella* oppure scaricare i singoli file o lo zip.

### Opzioni di uscita

| Opzione | Valori | Note |
|---|---|---|
| Profondità di calcolo | Veloce · Alta · Massima | 4 stem: Alta = `htdemucs_ft` (~4x), Massima = `htdemucs_ft` + 2 passaggi + 50% di sovrapposizione (~12x). Chitarra/piano/6 stem (`htdemucs_6s`): Alta = 2 passaggi (~2x), Massima = 3 passaggi + 50% (~4,5x) |
| Formato | WAV · FLAC · MP3 320 kbps | |
| Frequenza di campionamento | 44,1 · 48 · 96 kHz | MP3 al massimo 48 kHz |
| Profondità in bit | 16 · 24 · 32 bit float | 32 float solo WAV (conserva i picchi oltre 0 dBFS); 16 bit con dither TPDF |

Con uscite intere (16/24 bit, MP3) i picchi vengono misurati **dopo** il ricampionamento e, se
necessario, a tutti i file del lavoro si applica **lo stesso guadagno** (tetto −0,04 dBFS, −1 dBFS
per l'MP3): gli stem continuano a sommarsi al mix e Mid/Side a ricostruire L/R.
| Mid/Side | No · del mix · del mix e di ogni stem | stile iZotope Ozone: Mid = (L+R)/2, Side = (L−R)/2, file mono; L = M+S, R = M−S |

I modelli Demucs lavorano internamente a 44,1 kHz: a 48/96 kHz l'uscita viene ricampionata
con SoX VHQ (libsoxr), quindi gli stem non contengono frequenze oltre ~22 kHz.

### Riga di comando

```bash
.venv/bin/banana-split split canzone.mp3                      # voce, batteria, strumentale
.venv/bin/banana-split split video.mp4 --stem vocals --format mp3 -r 48000
.venv/bin/banana-split split *.flac --stem all4 -q max -f flac -r 96000 -b 24 --midside stems -o stems/
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

`-q high|max` aumenta la profondità di calcolo (vedi tabella sopra).
`--shifts N` forza il numero di passaggi.

### Forzare il dispositivo

```bash
.venv/bin/banana-split --device cpu serve
STEM_SPLITTER_DEVICE=mps ./scripts/start.sh
```

Altre variabili: `BANANA_SPLIT_HOME` (cartella dei dati dell'app, default `~/.banana-split`;
`STEM_SPLITTER_HOME` è ancora accettata),
`STEM_SPLITTER_MAX_MB` (dimensione massima upload, default 200),
`STEM_SPLITTER_TTL_HOURS` (dopo quante ore i lavori e i loro file vengono eliminati, default 24;
`0` per non eliminarli mai).

## Tempi indicativi (brano di 4 minuti, qualità standard)

Apple Silicon (MPS): circa 20–60 s · Mac Intel recente (CPU): circa 1–3 min.
La qualità Alta richiede circa 4 volte tanto, la Massima circa 12.

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
| POST | `/api/jobs` | multipart: `file`, `stem`, `quality`, `format`, `samplerate`, `bit_depth`, `midside`, `save_to_folder` |
| GET / POST | `/api/settings` | cartella di destinazione (`output_dir`) e `save_to_folder` |
| POST | `/api/pick-folder` | apre la finestra di sistema per scegliere la cartella |
| POST | `/api/reveal-output` | apre nel Finder/Esplora file la cartella di destinazione corrente |
| POST | `/api/jobs/{id}/reveal` | apre nel Finder/Esplora file la cartella con gli stem |
| GET | `/api/jobs/{id}` | stato, avanzamento, elenco stem |
| GET | `/api/jobs/{id}/stems/{nome}` | scarica uno stem |
| GET | `/api/jobs/{id}/zip` | scarica tutti gli stem |
| DELETE | `/api/jobs/{id}` | elimina il lavoro e i file (se è in corso lo interrompe) |

Le richieste che modificano qualcosa (POST, DELETE) richiedono l'header `X-Stem-Splitter: 1`.
