# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: `pyinstaller packaging/stem_splitter.spec` dalla radice del repository.
# Produce dist/Stem Splitter.app (macOS) oppure dist/StemSplitter/ (Windows, Linux).
import sys
from pathlib import Path

import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "packaging"
NAME = "StemSplitter"
VERSION = "0.1.0"

# ffmpeg incluso in imageio-ffmpeg: va tra i "binaries" per mantenere il permesso di esecuzione
ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
binaries = [(str(ffmpeg), "imageio_ffmpeg/binaries")]

datas = (
    collect_data_files("stem_splitter")  # interfaccia web (static/)
    + collect_data_files("demucs")  # elenco e configurazione dei modelli (remote/*.yaml)
    + collect_data_files("certifi")
)

hiddenimports = (
    collect_submodules("demucs")
    + collect_submodules("uvicorn")
    + ["stem_splitter.app", "multipart", "python_multipart"]
)

a = Analysis(
    [str(PKG / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "tensorboard", "pytest", "torchaudio",
              "torchvision", "sphn", "dora", "hydra", "submitit", "musdb", "museval"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,  # niente finestra di terminale: i log vanno in ~/.stem-splitter
    icon=str(PKG / ("icon.icns" if sys.platform == "darwin" else "icon.ico")),
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Stem Splitter.app",
        icon=str(PKG / "icon.icns"),
        bundle_identifier="com.barbienoodles.stemsplitter",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Stem Splitter",
            "CFBundleShortVersionString": VERSION,
            "LSMinimumSystemVersion": "11.0",
            # l'interfaccia è nel browser: niente icona nel Dock né menu "non risponde"
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
        },
    )
