"use strict";

const LABELS = {
  vocals: "Voce", instrumental: "Strumentale", drums: "Batteria", no_drums: "Senza batteria",
  bass: "Basso", no_bass: "Senza basso", guitar: "Chitarra", no_guitar: "Senza chitarra",
  piano: "Piano", no_piano: "Senza piano", other: "Altro", mix: "Mix originale",
};
const trackLabel = (name) => {
  const m = name.match(/^(.*)_(mid|side)$/);
  return m ? `${LABELS[m[1]] || m[1]} · ${m[2] === "mid" ? "Mid" : "Side"}` : LABELS[name] || name;
};
const CHIP_TEXT = {
  vocals_drums: ["Voce + batteria", "Voce, batteria, strumentale"],
  vocals: ["Voce", "Voce + strumentale (karaoke)"],
  drums: ["Batteria", "Batteria + resto"],
  bass: ["Basso", "Basso + resto"],
  guitar: ["Chitarra", "Chitarra + resto"],
  piano: ["Piano", "Piano + resto"],
  all4: ["4 stem", "Voce, batteria, basso, altro"],
  all6: ["6 stem", "Anche chitarra e piano"],
};
const COLORS = ["#7c5cff", "#19d3c5", "#ff8a3d", "#e3b341", "#ff5c7a", "#4ea8ff"];

const $ = (sel, root = document) => root.querySelector(sel);
const state = { stem: "vocals_drums", info: null };
let monkey = null;
const RATE_LABEL = (r) => `${(r / 1000).toLocaleString("it-IT")} kHz`;
const BITS_LABEL = { "16": "16 bit", "24": "24 bit", "32f": "32 bit float" };
let audioCtx = null;
const mixers = new Set();

const fmtTime = (s) => {
  s = Math.max(0, Math.floor(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

// header richiesto dal server per le richieste che modificano qualcosa (protezione CSRF)
const APP_HEADERS = { "X-Stem-Splitter": "1" };

async function api(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: { ...APP_HEADERS, ...(opts.headers || {}) } });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

async function init() {
  const info = await api("/api/info");
  state.info = info;
  $("#device").textContent = `⚡ ${info.device_label}`;
  $("#device").title = info.platform;

  const chips = $("#stems");
  for (const s of info.stems) {
    const [name, desc] = CHIP_TEXT[s.key] || [s.label, ""];
    const b = document.createElement("button");
    b.className = "chip";
    b.type = "button";
    b.setAttribute("role", "radio");
    b.dataset.key = s.key;
    b.innerHTML = `<span class="name"></span><span class="desc"></span>`;
    b.querySelector(".name").textContent = name;
    b.querySelector(".desc").textContent = desc;
    b.addEventListener("click", () => selectStem(s.key));
    chips.appendChild(b);
  }
  state.stem = info.default_stem;
  selectStem(state.stem);

  for (const [k, v] of Object.entries(info.qualities)) $("#quality").add(new Option(v, k));
  for (const f of info.formats) $("#format").add(new Option(f.toUpperCase(), f));
  for (const r of info.samplerates) $("#samplerate").add(new Option(RATE_LABEL(r), r));
  for (const b of info.bit_depths) $("#bitdepth").add(new Option(BITS_LABEL[b] || b, b));
  for (const [k, v] of Object.entries(info.midside)) $("#midside").add(new Option(v, k));
  $("#bitdepth").value = "24";
  ["#format", "#samplerate", "#bitdepth", "#quality", "#midside"].forEach((id) =>
    $(id).addEventListener("change", updateOptions));
  updateOptions();
  $("#file").accept = ["audio/*", "video/*", ...info.input_extensions].join(",");

  monkey = new Monkey($("#monkey"));
  const soundBtn = $("#sound");
  const showSound = () => { soundBtn.textContent = monkey.sound ? "🔊" : "🔇"; soundBtn.setAttribute("aria-pressed", monkey.sound); };
  soundBtn.onclick = () => { monkey.setSound(!monkey.sound); showSound(); };
  showSound();
  if (info.can_shutdown) {
    $("#quit").hidden = false;
    $("#quit").onclick = async () => {
      try { await api("/api/shutdown", { method: "POST" }); } catch {}
      document.body.innerHTML = '<main class="closed"><h1>Stem Splitter è chiuso 👋</h1><p class="muted">Puoi chiudere questa scheda. Per riaprirlo, avvia di nuovo l\'app.</p></main>';
    };
  }

  // il file si può lasciare cadere ovunque nella pagina: la scimmietta si emoziona
  const drop = $("#drop"), input = $("#file");
  input.addEventListener("change", () => { [...input.files].forEach(upload); input.value = ""; });
  let depth = 0;
  const hasFiles = (ev) => [...(ev.dataTransfer?.types || [])].includes("Files");
  document.addEventListener("dragenter", (ev) => {
    if (!hasFiles(ev)) return;
    ev.preventDefault();
    if (depth++ === 0) { drop.classList.add("over"); monkey.excited(true); }
  });
  document.addEventListener("dragover", (ev) => { if (hasFiles(ev)) ev.preventDefault(); });
  document.addEventListener("dragleave", (ev) => {
    if (!hasFiles(ev)) return;
    if (--depth <= 0) { depth = 0; drop.classList.remove("over"); monkey.excited(false); }
  });
  document.addEventListener("drop", (ev) => {
    if (!hasFiles(ev)) return;
    ev.preventDefault();
    depth = 0;
    drop.classList.remove("over");
    monkey.excited(false);
    [...ev.dataTransfer.files].forEach(upload);
  });
}

function selectStem(key) {
  state.stem = key;
  document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-checked", c.dataset.key === key));
  updateOptions();
}

// Mantiene coerenti le combinazioni (es. l'MP3 arriva al massimo a 48 kHz e non ha bit depth).
function updateOptions() {
  const info = state.info;
  if (!info || !$("#format").options.length) return;
  const fmt = $("#format").value, rate = $("#samplerate"), bits = $("#bitdepth");
  for (const o of rate.options) o.disabled = fmt === "mp3" && +o.value > info.mp3_max_rate;
  if (rate.selectedOptions[0]?.disabled) rate.value = String(info.mp3_max_rate);
  bits.disabled = fmt === "mp3";
  for (const o of bits.options) o.disabled = fmt === "flac" && o.value === "32f";
  if (bits.selectedOptions[0]?.disabled) bits.value = "24";

  const hints = [];
  const q = $("#quality").value, d = info.quality_details[q];
  const six = info.stems.find((s) => s.key === state.stem)?.six_stems;
  const plan = d[six ? "6" : "4"];
  if (q !== "standard") {
    const parts = [`modello ${plan.model}`, `${plan.shifts} ${plan.shifts > 1 ? "passaggi" : "passaggio"}`,
      `${Math.round(d.overlap * 100)}% di sovrapposizione`];
    hints.push(`${info.qualities[q]}: ${parts.join(", ")}, circa ${+plan.cost.toFixed(1)} volte il tempo di "Veloce".`);
  }
  if (+rate.value > 44100) hints.push("La separazione avviene a 44,1 kHz; l'uscita viene ricampionata con SoX VHQ.");
  if (fmt === "mp3") hints.push("MP3 a 320 kbps.");
  if ($("#midside").value !== "off") hints.push("Mid = (L+R)/2, Side = (L−R)/2, file mono. Nel mixer partono in muto.");
  $("#hint").textContent = hints.join(" ");
}

async function upload(file) {
  const el = $("#job-tpl").content.firstElementChild.cloneNode(true);
  $("#jobs").prepend(el);
  $(".job-title", el).textContent = file.name;
  $(".status", el).textContent = "Caricamento…";
  el._monkey = "active"; // ogni lavoro chiude il suo conto con la scimmietta una volta sola
  monkey.jobAdded();
  const maxMb = state.info.max_upload_mb;
  if (file.size > maxMb * 1024 * 1024) return fail(el, `File troppo grande (max ${maxMb} MB)`);

  const fd = new FormData();
  fd.append("file", file);
  fd.append("stem", state.stem);
  fd.append("quality", $("#quality").value);
  fd.append("format", $("#format").value);
  fd.append("samplerate", $("#samplerate").value);
  fd.append("bit_depth", $("#bitdepth").value);
  fd.append("midside", $("#midside").value);
  try {
    const job = await api("/api/jobs", { method: "POST", body: fd });
    const qLabel = state.info.qualities[job.quality] || job.quality;
    const bitsLabel = job.format === "mp3" ? "320 kbps" : BITS_LABEL[job.format === "flac" && job.bit_depth === "32f" ? "24" : job.bit_depth];
    $(".job-sub", el).textContent = [CHIP_TEXT[job.stem]?.[0] || job.stem, qLabel.split(" (")[0],
      `${job.format.toUpperCase()} ${RATE_LABEL(job.samplerate)} ${bitsLabel}`,
      job.midside !== "off" ? "Mid/Side" : null].filter(Boolean).join(" · ");
    $(".remove", el).onclick = async () => {
      if (el._monkey === "active") { el._monkey = "closed"; monkey.cancel(); }
      el._mixer?.destroy();
      el.remove();
      try { await fetch(`/api/jobs/${job.id}`, { method: "DELETE", headers: APP_HEADERS }); } catch {}
    };
    poll(job.id, el);
  } catch (e) {
    fail(el, e.message);
  }
}

function fail(el, msg) {
  if (el._monkey === "active") { el._monkey = "closed"; monkey.fail(msg); }
  el.classList.add("error");
  $(".status", el).textContent = `Errore: ${msg}`;
  $(".remove", el).onclick = () => el.remove();
}

async function poll(id, el) {
  let job;
  try { job = await api(`/api/jobs/${id}`); } catch (e) { return fail(el, e.message); }
  if (!el.isConnected) return;
  $(".bar", el).style.width = `${(job.progress * 100).toFixed(1)}%`;
  $(".status", el).textContent = job.status === "queued" ? "In coda…" :
    `${job.message} ${job.status === "running" ? Math.round(job.progress * 100) + "%" : ""}`;
  if (job.status === "error") return fail(el, job.error);
  if (job.status === "running") monkey.progress(job.progress, job.message);
  if (job.status !== "done") return setTimeout(() => poll(id, el), 800);
  // i file compaiono solo dopo la... scorreggia della scimmietta
  $(".status", el).textContent = "La scimmietta sta finendo…";
  if (el._monkey === "active") { el._monkey = "closed"; await monkey.finish(); }
  if (!el.isConnected) return;
  el.classList.add("done", "reveal");
  $(".status", el).textContent = `Completato in ${job.elapsed}s`;
  $(".zip", el).href = `/api/jobs/${id}/zip`;
  $(".player", el).hidden = false;
  el._mixer = new Mixer(el, job);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

class Mixer {
  constructor(el, job) {
    this.el = el;
    this.tracks = [];
    this.playing = false;
    this.offset = 0;
    this.duration = 0;
    this.playBtn = $(".play", el);
    this.timeEl = $(".time", el);
    this.playBtn.disabled = true;
    this.playBtn.onclick = () => (this.playing ? this.pause() : this.play());
    mixers.add(this);
    this.build(job.stems);
    this.load().catch((e) => { this.timeEl.textContent = `Anteprima non disponibile: ${e.message}`; });
  }

  build(stems) {
    const box = $(".tracks", this.el);
    stems.forEach((s, i) => {
      const row = document.createElement("div");
      row.className = "track";
      row.innerHTML = `
        <div>
          <div class="track-name"></div>
          <div class="track-ctrl">
            <button class="toggle m" title="Muto">M</button>
            <button class="toggle s" title="Solo">S</button>
            <input class="vol" type="range" min="0" max="1.5" step="0.01" value="1" title="Volume">
          </div>
        </div>
        <canvas class="wave"></canvas>
        <a class="dl" title="Scarica" download>⤓</a>`;
      $(".track-name", row).textContent = trackLabel(s.name);
      $(".dl", row).href = s.url;
      // le tracce Mid/Side duplicano il contenuto degli stem: partono in muto e vengono
      // scaricate/decodificate solo quando servono, per non occupare memoria inutilmente
      const isMS = /_(mid|side)$/.test(s.name);
      if (isMS) { row.classList.add("ms"); $(".m", row).classList.add("on"); }
      const t = { ...s, row, color: COLORS[i % COLORS.length], muted: isMS, solo: false, vol: 1,
        lazy: isMS, loading: null, canvas: $("canvas", row), buffer: null, gain: null, src: null, peaks: null };
      $(".m", row).onclick = (e) => { t.muted = !t.muted; e.target.classList.toggle("on", t.muted); this.changed(t); };
      $(".s", row).onclick = (e) => { t.solo = !t.solo; e.target.classList.toggle("on", t.solo); this.changed(t); };
      $(".vol", row).oninput = (e) => { t.vol = +e.target.value; this.updateGains(); };
      t.canvas.onclick = (e) => {
        const r = t.canvas.getBoundingClientRect();
        this.seek(((e.clientX - r.left) / r.width) * this.duration);
      };
      box.appendChild(row);
      this.tracks.push(t);
    });
    this.resizeObs = new ResizeObserver(() => this.draw());
    this.tracks.forEach((t) => this.resizeObs.observe(t.canvas));
  }

  async load() {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    this.timeEl.textContent = "Carico l'anteprima…";
    await Promise.all(this.tracks.filter((t) => !t.lazy).map((t) => this.loadTrack(t)));
    this.duration = Math.max(...this.tracks.filter((t) => t.buffer).map((t) => t.buffer.duration));
    this.playBtn.disabled = false;
    this.updateGains();
    this.draw();
    this.updateTime();
  }

  loadTrack(t) {
    t.loading = t.loading || (async () => {
      const res = await fetch(t.url);
      if (!res.ok) throw new Error(res.statusText);
      t.buffer = await audioCtx.decodeAudioData(await res.arrayBuffer());
      t.gain = audioCtx.createGain();
      t.gain.gain.value = 0;
      t.gain.connect(audioCtx.destination);
      t.peaks = computePeaks(t.buffer, 800);
    })();
    return t.loading;
  }

  audible(t) {
    const anySolo = this.tracks.some((x) => x.solo);
    return !t.muted && (!anySolo || t.solo);
  }

  // Mute/solo cambiati: carica al volo le tracce M/S appena diventano udibili.
  async changed(t) {
    this.updateGains();
    const pending = this.tracks.filter((x) => x.lazy && !x.buffer && this.audible(x));
    if (!pending.length) return;
    pending.forEach((x) => (x.row.querySelector(".track-name").dataset.loading = "1"));
    this.draw();
    try {
      await Promise.all(pending.map((x) => this.loadTrack(x)));
    } catch (e) {
      this.timeEl.textContent = `Traccia non disponibile: ${e.message}`;
      return;
    } finally {
      pending.forEach((x) => delete x.row.querySelector(".track-name").dataset.loading);
    }
    if (this.playing) {
      const when = audioCtx.currentTime + 0.05;
      for (const x of pending) if (!x.src) this.startTrack(x, when, when - this.startedAt);
    }
    this.updateGains();
    this.draw();
  }

  startTrack(t, when, offset) {
    t.src = audioCtx.createBufferSource();
    t.src.buffer = t.buffer;
    t.src.connect(t.gain);
    t.src.start(when, Math.max(0, offset));
  }

  updateGains() {
    const anySolo = this.tracks.some((t) => t.solo);
    for (const t of this.tracks) {
      const on = !t.muted && (!anySolo || t.solo);
      t.row.style.opacity = on ? 1 : 0.45;
      if (!t.gain) continue;
      t.gain.gain.setTargetAtTime(on ? t.vol : 0, audioCtx.currentTime, 0.015);
    }
  }

  position() {
    return this.playing ? Math.min(this.duration, audioCtx.currentTime - this.startedAt) : this.offset;
  }

  play() {
    mixers.forEach((m) => m !== this && m.playing && m.pause());
    if (audioCtx.state === "suspended") audioCtx.resume();
    if (this.offset >= this.duration) this.offset = 0;
    const when = audioCtx.currentTime + 0.05;
    for (const t of this.tracks) if (t.buffer) this.startTrack(t, when, this.offset);
    this.startedAt = when - this.offset;
    this.playing = true;
    this.playBtn.textContent = "❚❚";
    requestAnimationFrame(() => this.tick());
  }

  pause() {
    this.offset = this.position();
    this.stopSources();
    this.playing = false;
    this.playBtn.textContent = "▶";
    this.updateTime();
    this.draw();
  }

  stopSources() {
    for (const t of this.tracks) {
      try { t.src?.stop(); } catch {}
      t.src?.disconnect();
      t.src = null;
    }
  }

  seek(time) {
    const was = this.playing;
    if (was) this.pause();
    this.offset = Math.max(0, Math.min(time, this.duration));
    if (was) this.play();
    this.draw();
    this.updateTime();
  }

  updateTime() {
    this.timeEl.textContent = `${fmtTime(this.position())} / ${fmtTime(this.duration)}`;
  }

  // Animazione solo durante la riproduzione: si ferma da sola in pausa.
  tick() {
    if (this.destroyed || !this.playing) return;
    if (this.position() >= this.duration) {
      this.pause();
      this.offset = 0;
      this.updateTime();
      this.draw();
      return;
    }
    this.updateTime();
    this.draw();
    requestAnimationFrame(() => this.tick());
  }

  draw() {
    const frac = this.duration ? this.position() / this.duration : 0;
    const dpr = window.devicePixelRatio || 1;
    for (const t of this.tracks) {
      const c = t.canvas, w = c.clientWidth, h = c.clientHeight;
      if (!w) continue;
      if (c.width !== Math.round(w * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
      const g = c.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      if (!t.peaks) {
        g.fillStyle = "#59607a";
        g.font = "12px -apple-system, sans-serif";
        g.textBaseline = "middle";
        const loading = t.row.querySelector(".track-name").dataset.loading;
        g.fillText(loading ? "Caricamento…" : t.lazy ? "Togli il muto (M) o premi S per caricarla" : "", 8, h / 2);
        continue;
      }
      const n = t.peaks.length, bw = w / n, mid = h / 2, cut = frac * w;
      for (let i = 0; i < n; i++) {
        const x = i * bw, a = Math.max(1, t.peaks[i] * mid);
        g.fillStyle = x < cut ? t.color : "#3a4252";
        g.fillRect(x, mid - a, Math.max(1, bw - 0.5), a * 2);
      }
      g.fillStyle = "#fff";
      g.fillRect(cut, 0, 1.5, h);
    }
  }

  destroy() {
    this.destroyed = true;
    this.stopSources();
    this.resizeObs?.disconnect();
    this.tracks.forEach((t) => t.gain?.disconnect());
    mixers.delete(this);
  }
}

function computePeaks(buffer, n) {
  const chans = [...Array(buffer.numberOfChannels)].map((_, i) => buffer.getChannelData(i));
  const len = buffer.length, step = Math.max(1, Math.floor(len / n)), peaks = new Float32Array(n);
  let max = 0;
  for (let i = 0; i < n; i++) {
    let p = 0;
    const start = i * step, end = Math.min(len, start + step);
    for (const d of chans) for (let j = start; j < end; j += 16) p = Math.max(p, Math.abs(d[j]));
    peaks[i] = p;
    max = Math.max(max, p);
  }
  if (max > 0) for (let i = 0; i < n; i++) peaks[i] /= max;
  return peaks;
}

document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || /INPUT|SELECT|BUTTON/.test(e.target.tagName)) return;
  const m = [...mixers].find((x) => x.playing) || [...mixers][0];
  if (m && !m.playBtn.disabled) { e.preventDefault(); m.playing ? m.pause() : m.play(); }
});

init().catch((e) => { $("#device").textContent = `Errore: ${e.message}`; });
