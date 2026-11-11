# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: `pyinstaller packaging/stem_splitter.spec` dalla radice del repository.
# Produce dist/Banana Split.app (macOS) oppure dist/BananaSplit/ (Windows, Linux).
import platform
import sys
from pathlib import Path

import imageio_ffmpeg
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "packaging"
NAME = "BananaSplit"
VERSION = "0.2.1"

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
    console=False,  # niente finestra di terminale: i log vanno in ~/.banana-split
    icon=str(PKG / ("icon.icns" if sys.platform == "darwin" else "icon.ico")),
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Banana Split.app",
        icon=str(PKG / "icon.icns"),
        bundle_identifier="com.barbienoodles.bananasplit",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Banana Split",
            "CFBundleShortVersionString": VERSION,
            # Intel: Python 3.12 di python.org e PyTorch 2.2 funzionano da macOS 10.13 High Sierra
            # (la CI lo verifica con packaging/check_macos_min.py); Apple Silicon parte da macOS 11
            "LSMinimumSystemVersion": "11.0" if platform.machine() == "arm64" else "10.13",
            # l'interfaccia è nel browser: niente icona nel Dock né menu "non risponde"
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
        },
    )
