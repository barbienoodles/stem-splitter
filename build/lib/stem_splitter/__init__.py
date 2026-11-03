"""Stem Splitter: separazione locale di brani in stem con Demucs."""

import os

# Su Apple Silicon alcune operazioni non sono ancora implementate in MPS:
# questa variabile fa ricadere solo quelle sulla CPU invece di fallire.
# Deve essere impostata prima del primo import di torch.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

__version__ = "0.1.0"
