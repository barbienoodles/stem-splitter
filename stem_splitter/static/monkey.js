"use strict";
// La scimmietta: riceve il file, separa noccioline (le mangia) e sassi (li lancia via),
// e quando ha finito... fa una scorreggia. Tutto in SVG + Web Animations, suoni con Web Audio.

const SVG_NS = "http://www.w3.org/2000/svg";
const IDLE_TEXT = "Trascina qui il brano o clicca su di me! 🍌";
const REDUCED = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

const MONKEY_SVG = `
<svg class="monkey-svg" viewBox="0 50 600 365" role="img" aria-label="Scimmietta con una ciotola">
  <defs>
    <radialGradient id="mk-cloud" cx="50%" cy="50%" r="50%">
      <stop offset="0" stop-color="#d9f0a3"/><stop offset="1" stop-color="#9ccc65" stop-opacity=".85"/>
    </radialGradient>
  </defs>
  <ellipse cx="300" cy="372" rx="230" ry="16" class="mk-shadow"/>
  <g class="mk-body">
    <path class="mk-tail" d="M380 300 C470 310 500 230 455 205 C425 190 410 225 435 235" fill="none" stroke="#7a4a2a" stroke-width="16" stroke-linecap="round"/>
    <ellipse cx="300" cy="262" rx="98" ry="88" fill="#8b5a33"/>
    <ellipse cx="300" cy="275" rx="60" ry="58" fill="#c99467"/>
    <g class="mk-head">
      <circle cx="218" cy="140" r="32" fill="#7a4a2a"/><circle cx="218" cy="140" r="18" fill="#f1c9a0"/>
      <circle cx="382" cy="140" r="32" fill="#7a4a2a"/><circle cx="382" cy="140" r="18" fill="#f1c9a0"/>
      <circle cx="300" cy="140" r="80" fill="#8b5a33"/>
      <path d="M300 92c-24-22-74-17-76 28-2 28 16 44 16 60 0 36 28 64 60 64s60-28 60-64c0-16 18-32 16-60-2-45-52-50-76-28z" fill="#f1c9a0"/>
      <g class="mk-eyes">
        <g class="mk-eye-open">
          <ellipse cx="276" cy="128" rx="13" ry="16" fill="#1b1b24"/><circle cx="280" cy="122" r="4.5" fill="#fff"/>
          <ellipse cx="324" cy="128" rx="13" ry="16" fill="#1b1b24"/><circle cx="328" cy="122" r="4.5" fill="#fff"/>
        </g>
        <g class="mk-eye-happy" opacity="0">
          <path d="M263 132 q13 -16 26 0" stroke="#1b1b24" stroke-width="5" fill="none" stroke-linecap="round"/>
          <path d="M311 132 q13 -16 26 0" stroke="#1b1b24" stroke-width="5" fill="none" stroke-linecap="round"/>
        </g>
        <g class="mk-eye-sad" opacity="0">
          <path d="M263 124 l24 8" stroke="#1b1b24" stroke-width="5" stroke-linecap="round"/>
          <path d="M337 124 l-24 8" stroke="#1b1b24" stroke-width="5" stroke-linecap="round"/>
          <ellipse cx="276" cy="138" rx="9" ry="10" fill="#1b1b24"/><ellipse cx="324" cy="138" rx="9" ry="10" fill="#1b1b24"/>
        </g>
      </g>
      <ellipse cx="292" cy="160" rx="4" ry="3" fill="#5a341c"/><ellipse cx="308" cy="160" rx="4" ry="3" fill="#5a341c"/>
      <g class="mk-mouth">
        <path class="mk-mouth-smile" d="M282 180 q18 16 36 0" stroke="#5a341c" stroke-width="5" fill="none" stroke-linecap="round"/>
        <ellipse class="mk-mouth-open" cx="300" cy="184" rx="13" ry="10" fill="#5a341c" opacity="0"/>
        <path class="mk-mouth-sad" d="M284 190 q16 -12 32 0" stroke="#5a341c" stroke-width="5" fill="none" stroke-linecap="round" opacity="0"/>
      </g>
    </g>
    <g class="mk-arm mk-arm-left">
      <path d="M228 222 L214 300" stroke="#7a4a2a" stroke-width="26" stroke-linecap="round"/>
      <circle class="mk-hand" cx="213" cy="306" r="17" fill="#c99467"/>
    </g>
    <g class="mk-arm mk-arm-right">
      <path d="M372 222 L386 300" stroke="#7a4a2a" stroke-width="26" stroke-linecap="round"/>
      <circle class="mk-hand" cx="387" cy="306" r="17" fill="#c99467"/>
    </g>
  </g>
  <g class="mk-pile">
    <g transform="translate(228 294) rotate(-18)"><use href="#mk-peanut"/></g>
    <g transform="translate(262 286) rotate(-8)"><use href="#mk-banana"/></g>
    <g transform="translate(300 285) rotate(25)"><use href="#mk-peanut"/></g>
    <g transform="translate(340 287) rotate(12) scale(-1 1)"><use href="#mk-banana"/></g>
    <g transform="translate(372 294) rotate(14)"><use href="#mk-peanut"/></g>
  </g>
  <defs>
    <g id="mk-peanut">
      <path d="M-16 0c0-9 7-12 12-9 3 2 5 2 8 0 5-3 12 0 12 9s-7 12-12 9c-3-2-5-2-8 0-5 3-12 0-12-9z" fill="#d9a066" stroke="#a8743f" stroke-width="2"/>
      <path d="M-9 -3v6M-2 -4v8M5 -3v6" stroke="#b9834d" stroke-width="1.6" stroke-linecap="round"/>
    </g>
    <g id="mk-banana">
      <path d="M-22 -6C-16 9 10 12 22 -4L25 -9C20 -7 17 -4 15 -1 6 6-10 5-18 -8Z" fill="#ffd23f" stroke="#b88a00" stroke-width="2" stroke-linejoin="round"/>
      <path d="M-14 -2C-6 5 7 5 14 -2" stroke="#e6b800" stroke-width="2" fill="none" stroke-linecap="round"/>
      <path d="M22 -4L26 -10" stroke="#6b4a1a" stroke-width="4" stroke-linecap="round"/>
      <circle cx="-21" cy="-7" r="2.4" fill="#4a3412"/>
    </g>
  </defs>
  <g class="mk-bowl">
    <path d="M150 312h300c-12 62-78 92-150 92s-138-30-150-92z" fill="#e3b341"/>
    <path d="M190 350c40 22 180 22 220 0" stroke="#c99a2e" stroke-width="6" fill="none" stroke-linecap="round" opacity=".6"/>
    <rect x="140" y="298" width="320" height="26" rx="13" fill="#f5cf6a"/>
  </g>
  <g class="mk-fart"></g>
  <g class="mk-flying"></g>
  <g class="mk-done" opacity="0">
    <g class="mk-done-inner">
      <polygon points="0.0,-62.0 15.6,-42.3 43.4,-55.9 43.6,-33.9 78.2,-38.7 63.1,-18.8 97.5,-13.8 70.0,0.0 97.5,13.8 63.1,18.8 78.2,38.7 43.6,33.9 43.4,55.9 15.6,42.3 0.0,62.0 -15.6,42.3 -43.4,55.9 -43.6,33.9 -78.2,38.7 -63.1,18.8 -97.5,13.8 -70.0,0.0 -97.5,-13.8 -63.1,-18.8 -78.2,-38.7 -43.6,-33.9 -43.4,-55.9 -15.6,-42.3" fill="#ffd23f" stroke="#1b1b24" stroke-width="5" stroke-linejoin="round"/>
      <polygon points="0.0,-62.0 15.6,-42.3 43.4,-55.9 43.6,-33.9 78.2,-38.7 63.1,-18.8 97.5,-13.8 70.0,0.0 97.5,13.8 63.1,18.8 78.2,38.7 43.6,33.9 43.4,55.9 15.6,42.3 0.0,62.0 -15.6,42.3 -43.4,55.9 -43.6,33.9 -78.2,38.7 -63.1,18.8 -97.5,13.8 -70.0,0.0 -97.5,-13.8 -63.1,-18.8 -78.2,-38.7 -43.6,-33.9 -43.4,-55.9 -15.6,-42.3" fill="none" stroke="#ff5c7a" stroke-width="3" stroke-linejoin="round" transform="scale(.82)"/>
      <text x="0" y="11" text-anchor="middle" class="mk-done-text">DONE!</text>
    </g>
  </g>
</svg>`;

class Monkey {
  constructor(root) {
    this.root = root;
    root.insertAdjacentHTML("afterbegin", MONKEY_SVG);
    this.svg = root.querySelector("svg");
    this.q = (sel) => this.svg.querySelector(sel);
    this.bubble = root.querySelector(".mk-bubble");
    this.active = 0; // lavori in coda o in corso
    this.working = false;
    this.pendingFarts = [];
    this.sound = true;
    try { this.sound = localStorage.getItem("mk-sound") !== "off"; } catch {}
    this.blinkTimer = setInterval(() => this.blink(), 3800);
    this.idle();
  }

  // ---------- stati ----------
  idle() {
    this.hideDone();
    this.face("open", "smile");
    this.say(IDLE_TEXT);
    this.bob(true);
  }

  excited(on) {
    if (this.working) return;
    this.face(on ? "open" : "open", on ? "open" : "smile");
    this.say(on ? "Dai, dammelo! 🍌" : IDLE_TEXT);
    for (const [arm, deg] of [["left", 150], ["right", -150]]) {
      this.q(`.mk-arm-${arm}`).animate([{ transform: `rotate(${on ? deg : 0}deg)` }],
        { duration: 300, fill: "forwards", easing: "ease-out" });
    }
  }

  jobAdded() {
    this.active++;
    this.audio(); // crea l'AudioContext durante il gesto dell'utente (drop/click)
    if (!this.working) this.loop();
  }

  // lavoro eliminato prima della fine
  cancel() {
    this.active = Math.max(0, this.active - 1);
  }

  progress(p, msg) {
    if (this.working && !this.finishing) this.say(`${Math.round(p * 100)}% · ${msg || "Separo…"}`);
  }

  // Lavoro finito: scorreggia (in coda se sta ancora pescando). Si risolve a fine animazione.
  finish() {
    this.active = Math.max(0, this.active - 1);
    return new Promise((resolve) => {
      this.pendingFarts.push(resolve);
      if (!this.working) this.loop();
    });
  }

  fail(msg) {
    this.active = Math.max(0, this.active - 1);
    this.face("sad", "sad");
    this.say(`Ops… ${msg}`);
    clearTimeout(this.sadTimer);
    this.sadTimer = setTimeout(() => { if (!this.working) this.idle(); }, 6000);
  }

  // ---------- ciclo di lavoro ----------
  async loop() {
    if (this.working) return;
    this.working = true;
    if (!this.pendingFarts.length) this.hideDone();
    this.bob(false);
    this.excited(false);
    try {
      while (this.active > 0 || this.pendingFarts.length) {
        if (this.pendingFarts.length) {
          // a lavoro finito: l'ultima banana, poi... la scorreggia
          this.say("L'ultima banana… 🍌");
          this.finishing = true;
          await this.eatBanana();
          this.finishing = false;
          await this.fart();
          this.pendingFarts.shift()();
          continue;
        }
        // Banana Split: le banane le mangia, le noccioline le lancia via
        if (Math.random() < 0.55) await this.eatBanana();
        else await this.throwPeanut();
      }
    } finally {
      this.working = false;
    }
    this.face("happy", "smile");
    this.say("DONE! Ecco i tuoi file 👇");
    this.bob(true);
    clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => { if (!this.working) this.idle(); }, 8000);
  }

  item(kind, arm) {
    const hand = this.q(`.mk-arm-${arm} .mk-hand`);
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", `mk-item mk-${kind}`);
    g.setAttribute("transform", `translate(${hand.getAttribute("cx")} ${+hand.getAttribute("cy") + 6})`);
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", `#mk-${kind}`);
    // trasformazioni CSS attorno al centro dell'oggetto (serve per i morsi alla banana)
    use.style.transformBox = "fill-box";
    use.style.transformOrigin = "center";
    if (kind === "banana") use.setAttribute("transform", "scale(1.5)");
    g.appendChild(use);
    hand.parentNode.insertBefore(g, hand); // la mano lo "tiene" davanti
    return g;
  }

  rotate(arm, deg, duration, easing = "ease-in-out") {
    return this.q(`.mk-arm-${arm}`).animate([{ transform: `rotate(${deg}deg)` }],
      { duration: REDUCED ? 1 : duration, fill: "forwards", easing }).finished;
  }

  async eatBanana() {
    await this.rotate("left", -14, 260); // pesca nella ciotola
    const banana = this.item("banana", "left");
    this.face("open", "open");
    await this.rotate("left", -128, 420, "cubic-bezier(.3,.7,.4,1)"); // alla bocca
    // tre morsi: la banana si accorcia mentre mastica
    const bites = banana.firstChild.animate(
      [{ transform: "scale(1.5)" }, { transform: "scale(1.1, 1.3)" }, { transform: "scale(.7, 1.1)" }, { transform: "scale(.25, .8)" }],
      { duration: REDUCED ? 1 : 3 * 170, easing: "steps(3, end)", fill: "forwards" });
    await Promise.all([this.chew(), bites.finished]);
    banana.remove();
    await this.rotate("left", 0, 260);
  }

  async throwPeanut() {
    await this.rotate("right", 14, 260);
    const peanut = this.item("peanut", "right");
    this.face("open", "sad"); // bleah, una nocciolina
    await this.rotate("right", 40, 160);
    const swing = this.rotate("right", -135, 260, "cubic-bezier(.5,0,.9,.5)");
    await this.wait(REDUCED ? 0 : 190);
    this.fling(peanut);
    await swing;
    this.face("open", "smile");
    await this.rotate("right", 0, 300);
  }

  // stacca la nocciolina dalla mano e la fa volare via con un arco
  fling(el) {
    // posizione della mano nelle coordinate del livello dei voli (unità del viewBox)
    const layer = this.q(".mk-flying");
    const m = layer.getCTM().inverse().multiply(el.getCTM());
    const x = m.e, y = m.f;
    el.remove();
    const fly = document.createElementNS(SVG_NS, "g");
    fly.appendChild(el);
    el.setAttribute("transform", "");
    layer.appendChild(fly);
    const dx = 380 + Math.random() * 120, up = 120 + Math.random() * 80, spin = 540 + Math.random() * 360;
    fly.animate([
      { transform: `translate(${x}px, ${y}px) rotate(0deg)` },
      { transform: `translate(${x + dx * 0.5}px, ${y - up}px) rotate(${spin / 2}deg)`, offset: 0.45 },
      { transform: `translate(${x + dx}px, ${y + 140}px) rotate(${spin}deg)`, opacity: 0.2 },
    ], { duration: REDUCED ? 1 : 900, easing: "linear", fill: "forwards" }).finished.then(() => fly.remove());
  }

  async chew() {
    const mouth = this.q(".mk-mouth-open");
    this.face("happy", "open");
    for (let i = 0; i < 3; i++) {
      await mouth.animate([{ transform: "scaleY(1)" }, { transform: "scaleY(.3)" }, { transform: "scaleY(1)" }],
        { duration: REDUCED ? 1 : 170 }).finished;
    }
    this.face("open", "smile");
  }

  async fart() {
    this.say("Uff… 😳");
    this.face("happy", "smile");
    await this.wait(250);
    const body = this.q(".mk-body");
    const jump = body.animate([
      { transform: "translateY(0)" }, { transform: "translateY(-16px)" }, { transform: "translateY(0)" },
    ], { duration: REDUCED ? 1 : 420, easing: "ease-out" });
    this.puff();
    this.playFart();
    await jump.finished;
    this.say("DONE! 💨 Ecco i tuoi file 👇");
    this.showDone();
    await this.wait(REDUCED ? 0 : 900);
  }

  // esplosione da fumetto "DONE!" accanto alla testa
  showDone() {
    const done = this.q(".mk-done");
    done.setAttribute("opacity", 1);
    this.q(".mk-done-inner").animate([
      { transform: "scale(0) rotate(-25deg)" },
      { transform: "scale(1.2) rotate(6deg)", offset: 0.6 },
      { transform: "scale(1) rotate(-4deg)" },
    ], { duration: REDUCED ? 1 : 450, easing: "cubic-bezier(.2,.9,.3,1.4)", fill: "forwards" });
    clearTimeout(this.doneTimer);
    this.doneTimer = setTimeout(() => this.hideDone(), 7000);
  }

  hideDone() {
    clearTimeout(this.doneTimer);
    const done = this.q(".mk-done");
    if (done.getAttribute("opacity") === "0") return;
    this.q(".mk-done-inner").animate([{ transform: "scale(1) rotate(-4deg)" }, { transform: "scale(0) rotate(20deg)" }],
      { duration: REDUCED ? 1 : 250, fill: "forwards" }).finished.then(() => done.setAttribute("opacity", 0));
  }

  puff() {
    const layer = this.q(".mk-fart");
    for (let i = 0; i < 9; i++) {
      const c = document.createElementNS(SVG_NS, "circle");
      const r = 22 + Math.random() * 26;
      c.setAttribute("r", r);
      c.setAttribute("fill", "url(#mk-cloud)");
      layer.appendChild(c);
      // escono da dietro, sul fianco sinistro sopra il bordo della ciotola
      const x0 = 170 + Math.random() * 30, y0 = 280 + Math.random() * 15;
      const x1 = x0 - 60 - Math.random() * 110, y1 = y0 - 30 - Math.random() * 110;
      c.animate([
        { transform: `translate(${x0}px, ${y0}px) scale(.2)`, opacity: 0.95 },
        { transform: `translate(${(x0 + x1) / 2}px, ${(y0 + y1) / 2}px) scale(1.1)`, opacity: 0.85, offset: 0.4 },
        { transform: `translate(${x1}px, ${y1}px) scale(${1.4 + Math.random()})`, opacity: 0 },
      ], { duration: REDUCED ? 1 : 1400 + Math.random() * 500, delay: i * 50, easing: "ease-out", fill: "forwards" })
        .finished.then(() => c.remove());
    }
  }

  // ---------- suoni (sintetizzati, nessun file) ----------
  audio() {
    if (!this.sound) return null;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (this.ctx.state === "suspended") this.ctx.resume();
      return this.ctx;
    } catch { return null; }
  }

  playFart() {
    const ctx = this.audio();
    if (!ctx) return;
    const t = ctx.currentTime, dur = 0.75;
    const out = ctx.createGain();
    out.gain.setValueAtTime(0.0001, t);
    out.gain.exponentialRampToValueAtTime(0.55, t + 0.04);
    out.gain.setValueAtTime(0.55, t + dur * 0.6);
    out.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    const lp = ctx.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 600;
    lp.Q.value = 6;
    lp.connect(out).connect(ctx.destination);

    // tono "pernacchia": dente di sega che scende, con un tremolio veloce
    const osc = ctx.createOscillator();
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(115, t);
    osc.frequency.exponentialRampToValueAtTime(55, t + dur);
    const wob = ctx.createOscillator(), wobGain = ctx.createGain();
    wob.frequency.value = 23;
    wobGain.gain.value = 28;
    wob.connect(wobGain).connect(osc.frequency);
    osc.connect(lp);

    // un po' di rumore per la "aria"
    const noise = ctx.createBufferSource();
    const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * 0.35;
    noise.buffer = buf;
    noise.connect(lp);

    for (const n of [osc, wob, noise]) { n.start(t); n.stop(t + dur + 0.05); }
  }

  setSound(on) {
    this.sound = on;
    try { localStorage.setItem("mk-sound", on ? "on" : "off"); } catch {}
  }

  // ---------- dettagli ----------
  face(eyes, mouth) {
    for (const k of ["open", "happy", "sad"]) this.q(`.mk-eye-${k}`).setAttribute("opacity", k === eyes ? 1 : 0);
    for (const k of ["smile", "open", "sad"]) this.q(`.mk-mouth-${k}`).setAttribute("opacity", k === mouth ? 1 : 0);
  }

  blink() {
    if (REDUCED || this.q(".mk-eye-open").getAttribute("opacity") !== "1") return;
    this.q(".mk-eye-open").animate([{ transform: "scaleY(1)" }, { transform: "scaleY(.1)" }, { transform: "scaleY(1)" }],
      { duration: 180 });
  }

  bob(on) {
    this.bobAnim?.cancel();
    if (!on || REDUCED) return;
    this.bobAnim = this.q(".mk-head").animate(
      [{ transform: "rotate(-3deg)" }, { transform: "rotate(3deg)" }, { transform: "rotate(-3deg)" }],
      { duration: 3200, iterations: Infinity, easing: "ease-in-out" });
  }

  say(text) {
    if (!this.bubble) return;
    this.bubble.textContent = text;
    // l'insegna al neon lampeggia solo quando la scimmietta chiama il brano
    this.bubble.classList.toggle("flicker", text === IDLE_TEXT);
  }

  wait(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }
}

window.Monkey = Monkey;
