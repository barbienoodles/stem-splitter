# Tonalità e velocità per stem (Banana Split)

## Intento

L'utente vuole cambiare **tonalità** (±12 semitoni) e **velocità** (50–150%) dei brani, con un
**preascolto prima di separare**, e vuole la **qualità più alta possibile**: almeno pari a Rubber
Band, possibilmente migliore. Non vuole i vincoli GPL di Rubber Band. Decisione: partire dal
motore MIT **Signalsmith Stretch** e migliorarlo sfruttando ciò che solo Banana Split ha: gli
stem separati.

## Obiettivi

- Cursori **Tonalità** (−12…+12 semitoni, passo 1; facoltativo il fine tuning in cent: lasciato al
  builder) e **Velocità** (50–150%, passo 1%) nella colonna "Come separo?".
- **Preascolto** del brano caricato, in tempo reale nel browser, con tonalità e velocità applicate,
  *prima* di avviare la separazione.
- File finali (stem, Mid/Side, ZIP) già trasposti/riscalati, in tutti i formati, frequenze e bit
  attuali.
- **Elaborazione per sorgente** (il cuore del miglioramento): il motore lavora su ogni sorgente
  interna del modello (drums, bass, other, vocals, e guitar/piano nel 6 stem) *prima* della somma
  negli stem d'uscita, con impostazioni specifiche:
  - **vocals**: compensazione dei formanti attiva (timbro naturale, niente "voce da paperino");
  - **drums**: la tonalità **non** si applica (strumento senza intonazione); solo la velocità,
    con impostazioni che preservano i transienti;
  - **bass, guitar, piano, other**: impostazioni per materiale tonale (risoluzione in frequenza
    adatta; il builder sceglie i parametri con il test d'ascolto).
- Qualità verificata con un **test d'ascolto alla cieca** contro Rubber Band R3 (Rubber Band usato
  solo nello strumento di test, mai incluso nell'app).

## Non obiettivi

- Motore scritto da zero.
- Cambio di tonalità/velocità variabile nel tempo, loop, editor.
- Rilevamento automatico della tonalità del brano (eventuale fase successiva con gli accordi).

## Anti-obiettivi (fallimento anche se "funziona")

- Qualità udibilmente peggiore di Rubber Band R3 nel test alla cieca.
- Con tonalità 0 e velocità 100% l'audio deve essere **identico bit per bit** a oggi (il motore
  non deve nemmeno essere invocato).
- Installer più pesanti di oltre ~2 MB per piattaforma.
- Codice o binari GPL nell'app distribuita.
- Rompere il Mac Intel con macOS 10.13 (requisito dell'utente).

## Vincoli

- Python 3.12, PyInstaller, quattro piattaforme (macOS arm64, macOS x86_64 con deployment target
  10.13, Windows x64, Linux x64). Le wheel pubbliche esistenti (`python-stretch`) partono da
  macOS 10.14: quindi **compiliamo noi** il modulo nativo in CI.
- Signalsmith Stretch: libreria C++ header-only, MIT (Geraint Luff / Signalsmith Audio, attiva,
  ultimo commit ottobre 2026). Ha già: `presetDefault/presetCheaper`, `setTransposeSemitones`,
  `setFormantSemitones(…, compensatePitch)`, `setFormantBase`, `process/flush/seek`, e una build
  WebAssembly ufficiale (`web/emscripten`). Va vendorizzata in `third_party/signalsmith-stretch`
  con il file LICENSE e la menzione nel README.
- Interfaccia attuale: `stem_splitter/separator.py` ottiene `by_name` (sorgenti interne
  `[canali, campioni]`, dominio normalizzato) e le somma negli stem d'uscita; Mid/Side del mix
  usa il `wav` originale. Il guadagno anti-clip è unico per tutti i file del lavoro.
- Il server gira solo su 127.0.0.1 con chiave d'avvio; il preascolto deve usare le API esistenti
  autenticate (o file locale lato browser), niente nuovi canali di rete.
- Modelli/binari scaricati devono restare verificati (oggi SHA-256): il WASM è incluso nel
  pacchetto statico, non scaricato.

## Approcci considerati

1. **Copia nostra di Signalsmith + elaborazione per sorgente** — *scelto dall'utente.* Qualità
   superiore grazie agli stem; MIT; stesso algoritmo per preascolto (WASM) e file finali (nativo).
   Costo: compilazione nativa e WASM in CI.
2. Signalsmith così com'è (wheel `python-stretch`) — scartato: nessun miglioramento di qualità e
   niente Mac 10.13.
3. Motore da zero — scartato: mesi di lavoro, rischio concreto di qualità inferiore.

Rubber Band rimane solo come **riferimento** nel test d'ascolto.

## Decisioni prese (dall'utente)

- Approccio 1.
- Obiettivo: qualità più alta, non la licenza in sé.
- Tonalità e velocità "assolutamente sì", con preascolto prima di separare.
- **Flusso**: il brano scelto **aspetta sempre "Separa"**: prima si ascolta e si regola, poi si
  separa. Più brani trascinati insieme: stesse impostazioni, in coda.
- **Percorso a frecce** visibile nella pagina, come un diagramma di flusso:

  ```
  ① Scegli il brano  →  ② Ascolta e regola tonalità/velocità  →  ③ Separa
  ```

  Il passo attivo è evidenziato; quelli fatti hanno la spunta. Il pulsante "Separa" è il punto
  d'arrivo delle frecce.
- **Test alla cieca**: ascolta l'utente (coppie A/B anonime). Se il nostro perde contro Rubber Band
  R3, si migliora e si ripete: **niente rilascio** finché non vince o pareggia. Il test è una tappa
  di controllo prima dell'interfaccia e degli installer.

## Proposte mie (correggibili)

- **Preascolto = mix intero** (gli stem ancora non esistono): usa Signalsmith WASM sul mix, con
  le impostazioni "default". È un'approssimazione: il file finale per sorgente sarà migliore.
  L'interfaccia lo dice in una riga ("l'anteprima è indicativa: il risultato finale è elaborato
  stem per stem").
- **Mix Mid/Side con tonalità/velocità attive**: si calcola dalla somma delle sorgenti elaborate
  (così Mid/Side resta coerente con gli stem e la somma degli stem ricostruisce il mix).
- **Ordine nel separatore**: separazione → elaborazione per sorgente (prima della somma) → somma
  negli stem → Mid/Side → guadagno anti-clip unico → salvataggio. Il guadagno anti-clip va
  misurato dopo l'elaborazione.
- **Batteria e tonalità**: per default la batteria non viene trasposta. Le parti intonate che il
  modello mette nella batteria (timpani, toms molto accordati) restano non trasposte: accettato.
- **Nomi dei file**: suffisso con le impostazioni quando diverse dal default, es.
  `vocals (+2 st, 90%).wav`; lo ZIP e la cartella seguono lo stesso nome.
- **CLI**: opzioni `--pitch` e `--tempo` in `banana-split split`.
- **Interfaccia**: due cursori con valore numerico e pulsante "0 / 100%" per azzerare; un
  mini-player (▶/❚❚, barra di avanzamento) compare quando il brano è stato scelto, dentro il
  passo ②. Schizzo:

  ```
  ① Scegli il brano ✓  ──→  ② Ascolta e regola  ──→  ③ [ Separa 🍌 ]
                            ▶ ━━━━━●━━━━ 1:12 / 3:40
                            Tonalità  ◀─────●───▶  +2 st
                            Velocità  ◀───●─────▶   90 %   [↺ 0 / 100%]
                            (anteprima indicativa: il risultato è elaborato stem per stem)
  ```
- **Audio del preascolto** (mia scelta): nuova API sullo stesso server locale autenticato. Il brano
  si carica **una sola volta**: il server lo decodifica con ffmpeg (tutti i formati accettati) e
  fornisce al browser una versione per l'ascolto; "Separa" riusa lo stesso caricamento.
- **Browser vecchi** (mia scelta): dove manca AudioWorklet (Safari 13 su macOS 10.13) il preascolto
  usa un ripiego (ScriptProcessorNode) con lo stesso WASM; deve funzionare anche lì.

## Lasciato al builder

- Modulo nativo: C++ con API C minimale + `ctypes`, oppure nanobind/pybind11. Requisito: un solo
  binario per piattaforma, deployment target macOS 10.13 su Intel, nessuna dipendenza da
  runtime extra.
- Parametri esatti per sorgente (block/interval, tonalityLimit, formantBase) scelti con il test
  d'ascolto.
- Gestione di inizio/fine (latenza del motore, `flush`) per non perdere né aggiungere campioni:
  la durata d'uscita deve essere esattamente `round(durata / velocità)`.
- Elaborazione a 44,1 kHz (frequenza del modello) prima del ricampionamento d'uscita.
- Prestazioni: obiettivo indicativo ≤ 1× tempo reale per sorgente su CPU; mostrare l'avanzamento.
- Strumento di test d'ascolto (fuori dall'app): genera coppie A/B anonime (nostro vs Rubber Band
  R3) su *Grazie Michelina* a +2, −3, +5 semitoni e 80%/120%, per voce e mix, con chiave delle
  risposte in un file separato.
- Test automatici: identità bit per bit a 0/100%; lunghezza corretta; batteria non trasposta
  (es. sinusoide nella sorgente drums resta alla stessa frequenza); voce trasposta della quantità
  giusta (stima di frequenza); self-test degli installer che carica il modulo nativo.
