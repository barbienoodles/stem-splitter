"""Avvio come app desktop (installer .dmg, .exe e AppImage).

- avvia il server su una porta libera e apre il browser;
- se l'app è già aperta, riapre solo la pagina invece di avviarne una seconda;
- senza finestra di terminale: i messaggi vanno in ~/.stem-splitter/stem-splitter.log;
- l'app si chiude dal pulsante "Chiudi l'app" nella pagina;
- `--self-test` verifica il pacchetto (PyTorch, Demucs, ffmpeg, server) senza scaricare modelli.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_ID = "stem-splitter"
DEFAULT_PORT = 8765


def app_home() -> Path:
    home = Path(os.environ.get("STEM_SPLITTER_HOME", Path.home() / ".stem-splitter"))
    home.mkdir(parents=True, exist_ok=True)
    return home


def _setup_environment(log_to_file: bool) -> None:
    # Nelle app senza console stdout/stderr non esistono (o non li legge nessuno): su file.
    if log_to_file or sys.stdout is None or sys.stderr is None:
        log = open(app_home() / "stem-splitter.log", "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr = log
    # Il Python incluso nelle app per Mac non trova i certificati di sistema:
    # senza questo il primo download dei modelli fallirebbe con CERTIFICATE_VERIFY_FAILED.
    try:
        import certifi

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    except ImportError:
        pass


def _probe(port: int) -> bool:
    """True se su questa porta risponde già Stem Splitter."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=1) as r:
            return json.load(r).get("app") == APP_ID
    except Exception:
        return False


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
    if _probe(port):  # già aperta: riapri solo la pagina
        print(f"Stem Splitter è già in esecuzione sulla porta {port}")
        if open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return

    from .separator import Separator
    from .server import create_app

    port = _free_port(port)
    sep = Separator()
    print(f"Dispositivo: {sep.info.label}")
    server_box: dict = {}
    app = create_app(sep, on_shutdown=lambda: setattr(server_box["server"], "should_exit", True))
    server = server_box["server"] = _make_server(app, port)
    url = f"http://127.0.0.1:{port}/"

    def open_when_ready() -> None:
        for _ in range(200):
            if server.started:
                print(f"Pronto su {url}")
                if open_browser:
                    webbrowser.open(url)
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
        server = box["s"] = _make_server(
            create_app(sep, tmp / "jobs", on_shutdown=lambda: setattr(box["s"], "should_exit", True)), port)
        th = threading.Thread(target=server.run, daemon=True)
        th.start()
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(base + "/api/info", timeout=5) as r:
            info = json.load(r)
        assert info["app"] == APP_ID and info["can_shutdown"], info
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            assert b"Stem Splitter" in r.read()
        req = urllib.request.Request(base + "/api/shutdown", method="POST",
                                     headers={"X-Stem-Splitter": "1"})
        urllib.request.urlopen(req, timeout=5).read()
        th.join(10)
        assert not th.is_alive(), "il server non si è chiuso"
        print("server: ok")
    print("SELF-TEST OK")
    return 0


def main(argv: list[str] | None = None) -> None:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="stem-splitter-app")
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
