"""Genera icon.png / icon.ico / icon.icns da icon.svg (serve Playwright + Pillow).

Uso: python packaging/make_icons.py   — i file generati sono già nel repository,
va rilanciato solo se cambia icon.svg.
"""

import os
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent


def main() -> None:
    svg = (HERE / "icon.svg").read_text()
    png = HERE / "icon.png"
    with sync_playwright() as p:
        # CHROMIUM_PATH: per usare un Chromium già installato invece di quello di Playwright
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1024, "height": 1024})
        page.set_content(f"<style>html,body{{margin:0;background:transparent}}svg{{display:block;width:1024px;height:1024px}}</style>{svg}")
        page.locator("svg").screenshot(path=str(png), omit_background=True)
        browser.close()
    img = Image.open(png).convert("RGBA")
    img.save(HERE / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.save(HERE / "icon.icns")
    print("ok:", ", ".join(f.name for f in sorted(HERE.glob("icon.*"))))


if __name__ == "__main__":
    main()
