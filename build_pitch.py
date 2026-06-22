"""Render PITCH.md -> PITCH.pdf (one-page A4).

pandoc turns the markdown into an HTML fragment; we wrap it in print CSS and let
headless Chromium (via Playwright) print to PDF — which handles unicode (macrons,
em-dashes) and links cleanly without a LaTeX toolchain.

    pip install playwright && playwright install chromium   # one-time
    python build_pitch.py
"""

import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "PITCH.md")
PDF = os.path.join(HERE, "PITCH.pdf")

CSS = """
@page { size: A4; margin: 12mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Helvetica Neue', Arial, sans-serif; color:#1e293b; line-height:1.36; font-size:9.7pt; margin:0; }
h1 { font-size:17pt; color:#0f172a; margin:0 0 2px; }
h2 { font-size:11.5pt; color:#0f172a; margin:11px 0 4px; border-bottom:1px solid #e2e8f0; padding-bottom:2px; }
p { margin:5px 0; }
h1 + p em { color:#475569; }
em { color:#475569; }
a { color:#1e5fa0; text-decoration:none; }
strong { color:#0f172a; }
ul, ol { padding-left:18px; margin:4px 0; }
li { margin:2px 0; }
code { background:#f1f5f9; padding:1px 4px; border-radius:3px; font-size:8.8pt; }
"""


def main():
    body = subprocess.run(["pandoc", MD, "-t", "html"], capture_output=True, text=True, check=True).stdout
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    html_path = os.path.join(HERE, "_pitch_print.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + html_path, wait_until="networkidle")
        pg.pdf(path=PDF, format="A4", print_background=True,
               margin={"top": "12mm", "bottom": "12mm", "left": "16mm", "right": "16mm"})
        b.close()
    os.remove(html_path)
    print(f"wrote {PDF}")


if __name__ == "__main__":
    main()
