"""Riga di comando: `banana-split serve` (interfaccia web) e `banana-split split` (batch)."""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

from .audio import BIT_DEPTHS, FORMATS, SAMPLE_RATES
from .separator import DEFAULT_STEM, MIDSIDE_MODES, QUALITIES, STEM_OPTIONS


def _serve(args) -> None:
    import uvicorn

    from .separator import Separator
    from .server import create_app

    from .server import LOCAL_HOSTS

    sep = Separator(args.device)
    print(f"Dispositivo: {sep.info.label}")
    hosts = list(LOCAL_HOSTS)
    if args.host in ("0.0.0.0", "::"):
        print("⚠️  In ascolto su tutte le interfacce: chiunque sulla tua rete può usare Banana Split "
              "(non c'è autenticazione).")
        hosts = ["*"]
    elif args.host not in LOCAL_HOSTS:
        hosts.append(args.host)
    app = create_app(sep, allowed_hosts=hosts)
    url = f"http://{'localhost' if args.host in ('0.0.0.0', '127.0.0.1') else args.host}:{args.port}"
    print(f"Apri {url} nel browser")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def _split(args) -> None:
    from .separator import Separator

    sep = Separator(args.device)
    print(f"Dispositivo: {sep.info.label}")
    for f in args.files:
        path = Path(f)
        if not path.exists():
            print(f"✗ {path}: file non trovato", file=sys.stderr)
            continue
        out = Path(args.output) / path.stem
        start = time.time()

        def progress(p: float, msg: str) -> None:
            bar = "█" * int(p * 30)
            print(f"\r  {path.name}: [{bar:<30}] {p * 100:5.1f}% {msg:<40}", end="", flush=True)

        try:
            outputs = sep.separate(path, out, stem=args.stem, quality=args.quality,
                                   fmt=args.format, samplerate=args.rate, bit_depth=args.bits,
                                   midside=args.midside, shifts=args.shifts, progress=progress)
        except Exception as exc:
            print(f"\n✗ {path.name}: {exc}", file=sys.stderr)
            continue
        print(f"\n✓ {path.name} in {time.time() - start:.1f}s →")
        for name, p in outputs.items():
            print(f"    {name:<13} {p}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="banana-split", description="Banana Split: separa i brani in stem.")
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default=None,
                        help="dispositivo di calcolo (default: automatico)")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="avvia l'interfaccia web (default)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--no-browser", action="store_true", help="non aprire il browser")

    p_split = sub.add_parser("split", help="separa uno o più file da riga di comando")
    p_split.add_argument("files", nargs="+")
    p_split.add_argument("-s", "--stem", choices=list(STEM_OPTIONS), default=DEFAULT_STEM)
    p_split.add_argument("-q", "--quality", choices=list(QUALITIES), default="standard",
                         help="profondità di calcolo: standard, high, max")
    p_split.add_argument("-f", "--format", choices=list(FORMATS), default="wav")
    p_split.add_argument("-r", "--rate", type=int, choices=list(SAMPLE_RATES), default=44100,
                         help="frequenza di campionamento in uscita (Hz)")
    p_split.add_argument("-b", "--bits", choices=list(BIT_DEPTHS), default="24",
                         help="profondità in bit (WAV/FLAC); 32f = 32 bit float")
    p_split.add_argument("--midside", choices=list(MIDSIDE_MODES), default="off",
                         help="esporta anche i canali Mid/Side: del mix o anche di ogni stem")
    p_split.add_argument("-o", "--output", default="separated")
    p_split.add_argument("--shifts", type=int, default=None,
                         help="forza il numero di passaggi (sovrascrive la qualità)")

    args = parser.parse_args(argv)
    if args.command == "split":
        _split(args)
    else:
        if args.command is None:
            args = parser.parse_args([*(argv or sys.argv[1:]), "serve"])
        _serve(args)


if __name__ == "__main__":
    main()
