"""Сборка PDF-версии отчёта: docs/report.md -> docs/report.pdf (Markdown -> HTML -> печать браузером).

    pip install markdown
    python scripts/build_report_pdf.py [путь к msedge.exe или chrome]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Segoe UI", system-ui, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #0b0b0b; }
h1 { font-size: 20pt; margin: 0 0 6pt; } h2 { font-size: 14pt; margin: 16pt 0 6pt; border-bottom: 1px solid #e1e0d9; padding-bottom: 3pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; }
table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 6pt 0; page-break-inside: auto; }
th, td { border-bottom: 1px solid #e1e0d9; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { color: #52514e; }
code, pre { font-family: Consolas, monospace; font-size: 9pt; background: #f4f3ef; }
pre { padding: 6pt; white-space: pre-wrap; }
a { color: #1c5cab; text-decoration: none; }
"""


def main() -> None:
    browser = sys.argv[1] if len(sys.argv) > 1 else None
    candidates = [browser, r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe", shutil.which("chromium"), shutil.which("google-chrome")]
    exe = next((c for c in candidates if c and Path(c).exists()), None)
    if exe is None:
        sys.exit("Нужен Edge или Chrome для печати в PDF")
    md = (ROOT / "docs" / "report.md").read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables", "fenced_code"])
    title = md.splitlines()[0].lstrip("# ").strip()
    html = f"<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "report.html"
        src.write_text(html, encoding="utf-8")
        out = ROOT / "docs" / "report.pdf"
        subprocess.run([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()],
                       check=True, capture_output=True, timeout=120)
    shutil.copyfile(out, ROOT / "site" / "report.pdf")  # копия для лендинга на GitHub Pages
    print("готово:", out, out.stat().st_size, "байт")


if __name__ == "__main__":
    main()
