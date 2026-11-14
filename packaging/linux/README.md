# File per l'AppImage

- `AppRun`, `banana-split.desktop`: avvio e voce di menu.
- `runtime-x86_64`: runtime dell'AppImage (la parte che monta ed esegue l'immagine), copia del
  binario ufficiale <https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64>
  scaricato il 14/11/2026, SHA-256 `617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46`.
  È incluso qui perché quel rilascio non ha versioni numerate: così la build non scarica codice non
  verificato. La CI controlla l'impronta prima di usarlo. Per aggiornarlo: scaricare la nuova versione,
  aggiornare file, impronta qui e in `.github/workflows/build.yml`.
