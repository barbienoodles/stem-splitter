"""Avvio come app desktop (installer .dmg, .exe e AppImage).

- avvia il server su una porta libera e apre il browser;
- se l'app è già aperta, riapre solo la pagina invece di avviarne una seconda;
- senza finestra di terminale: i messaggi vanno in ~/.banana-split/banana-split.log;
- l'app si chiude dal pulsante "Chiudi l'app" nella pagina;
- `--self-test` verifica il pacchetto (PyTorch, Demucs, ffmpeg, server) senza scaricare modelli.
"""

from __future__ import annotations

import argparse
import hmac
import json
import multiprocessing
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_ID = "banana-split"
DEFAULT_PORT = 8765


def app_home() -> Path:
    from .outputs import app_home as _home

    return _home()


def _setup_environment(log_to_file: bool) -> None:
    # Nelle app senza console stdout/stderr non esistono (o non li legge nessuno): su file.
    if log_to_file or sys.stdout is None or sys.stderr is None:
        log = open(app_home() / "banana-split.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log
    # Il Python incluso nelle app per Mac non trova i certificati di sistema:
    # senza questo il primo download dei modelli fallirebbe con CERTIFICATE_VERIFY_FAILED.
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass


def _token_file() -> Path:
    return app_home() / "token"


def _probe(port: int) -> str | None:
    """Se su questa porta c'è il VERO Banana Split, ritorna un codice monouso per aprirlo.

    Il server deve dimostrare di conoscere la chiave (HMAC su un numero casuale) senza che la
    chiave gli venga inviata: un altro programma in ascolto su questa porta non può farlo.
    """
    from .auth import proof, read_token_file

    token = read_token_file(_token_file())
    if not token:
        return None
    base = f"http://127.0.0.1:{port}"
    nonce = secrets.token_hex(16)
    try:
        with urllib.request.urlopen(f"{base}/api/hello?nonce={nonce}", timeout=1) as r:
            hello = json.load(r)
        if hello.get("app") != APP_ID or not hmac.compare_digest(str(hello.get("proof")), proof(token, nonce)):
            return None
        req = urllib.request.Request(f"{base}/api/launch-code", method="POST",
                                     headers={"X-Banana-Token": token, "X-Stem-Splitter": "1"})
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.load(r).get("code")
    except Exception:
        return None


def _free_port(preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 50)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_server(app, port: int):
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                            log_config=None, lifespan="off")
    return uvicorn.Server(config)


def run(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    code = _probe(port)
    if code:  # già aperta (e verificata): riapri solo la pagina
        print(f"Banana Split è già in esecuzione sulla porta {port}")
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/?c={code}")
        return

    from .auth import new_token, write_token_file
    from .separator import Separator
    from .server import create_app

    port = _free_port(port)  # se la porta è occupata da altro, se ne usa un'altra
    sep = Separator()
    print(f"Dispositivo: {sep.info.label}")
    token = new_token()
    write_token_file(_token_file(), token)
    server_box: dict = {}
    app = create_app(sep, on_shutdown=lambda: setattr(server_box["server"], "should_exit", True),
                     token=token)
    server = server_box["server"] = _make_server(app, port)
    url = f"http://127.0.0.1:{port}/"

    def open_when_ready() -> None:
        for _ in range(200):
            if server.started:
                print(f"Pronto su {url}")
                if open_browser:
                    webbrowser.open(f"{url}?c={app.state.auth.new_code()}")
                return
            time.sleep(0.05)

    threading.Thread(target=open_when_ready, daemon=True).start()
    server.run()


def self_test() -> int:
    """Separazione con un HTDemucs piccolo a pesi casuali + avvio del server. Exit code 0 = ok."""
    import tempfile

    import numpy as np
    import torch

    from .audio import load_audio, save_audio
    from .separator import Separator
    from .server import create_app

    class _TestSeparator(Separator):
        def load_model(self, name):
            from demucs.apply import BagOfModels
            from demucs.htdemucs import HTDemucs

            if name not in self._models:
                torch.manual_seed(0)
                m = HTDemucs(["drums", "bass", "other", "vocals"], channels=8, t_layers=1, segment=4)
                self._models[name] = BagOfModels([m]).eval()
            return self._models[name]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sr = 44100
        t = np.arange(sr * 3) / sr
        sig = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        song = save_audio(np.stack([sig, sig]), tmp / "song", sr, "mp3")
        sep = _TestSeparator("cpu")
        print(f"torch {torch.__version__} · {sep.info.label}")
        out = sep.separate(song, tmp / "out", fmt="flac", samplerate=96000, midside="mix")
        assert list(out) == ["vocals", "drums", "instrumental", "mix_mid", "mix_side"], list(out)
        assert load_audio(out["vocals"], sr).shape[1] > sr * 2
        print("separazione: ok", ", ".join(out))

        port = _free_port(DEFAULT_PORT + 100)
        box: dict = {}
        from .auth import new_token, proof

        token = new_token()
        app = create_app(sep, tmp / "jobs", on_shutdown=lambda: setattr(box["s"], "should_exit", True),
                         token=token)
        server = box["s"] = _make_server(app, port)
        th = threading.Thread(target=server.run, daemon=True)
        th.start()
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        base = f"http://127.0.0.1:{port}"
        key = {"X-Banana-Token": token}
        # senza chiave: rifiutato
        try:
            urllib.request.urlopen(base + "/api/info", timeout=5)
            raise AssertionError("l'API risponde senza chiave")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401, exc.code
        # prova d'identità senza rivelare la chiave
        with urllib.request.urlopen(base + "/api/hello?nonce=abc", timeout=5) as r:
            assert json.load(r)["proof"] == proof(token, "abc")
        # codice monouso: la prima volta dà il cookie, la seconda no
        code = app.state.auth.new_code()
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
        with opener.open(base + f"/?c={code}", timeout=5) as r:
            assert b"Banana Split" in r.read()
        assert not app.state.auth.consume(code)
        with urllib.request.urlopen(urllib.request.Request(base + "/api/info", headers=key), timeout=5) as r:
            info = json.load(r)
        assert info["app"] == APP_ID and info["can_shutdown"], info
        req = urllib.request.Request(base + "/api/shutdown", method="POST",
                                     headers={"X-Stem-Splitter": "1", **key})
        urllib.request.urlopen(req, timeout=5).read()
        th.join(10)
        assert not th.is_alive(), "il server non si è chiuso"
        print("server e chiave d'accesso: ok")
    print("SELF-TEST OK")
    return 0


def main(argv: list[str] | None = None) -> None:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="banana-split-app")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    # macOS passa argomenti tipo -psn_0_12345 alle app avviate dal Finder
    args, _ = parser.parse_known_args(argv)
    interactive = sys.stdout is not None and sys.stdout.isatty()
    _setup_environment(log_to_file=getattr(sys, "frozen", False) and not args.self_test and not interactive)
    if args.self_test:
        try:
            code = self_test()
        except Exception:
            import traceback

            traceback.print_exc()
            print("SELF-TEST FALLITO")
            code = 1
        sys.stdout.flush()
        sys.exit(code)
    run(args.port, not args.no_browser)


if __name__ == "__main__":
    main()
