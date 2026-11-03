# Punto di ingresso per PyInstaller: importa il pacchetto (che imposta
# PYTORCH_ENABLE_MPS_FALLBACK prima di torch) e avvia l'app desktop.
from stem_splitter.app import main

if __name__ == "__main__":
    main()
