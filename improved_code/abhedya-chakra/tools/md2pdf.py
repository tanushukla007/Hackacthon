#!/usr/bin/env python3
"""
md2pdf.py — Abhedya-Chakra documentation build tool.

Renders a Markdown file to a print-quality A4 PDF with:
  • cover page, running footer, page numbers
  • working internal TOC links
  • monospace ASCII-diagram blocks that do not overflow the page
  • repeating table headers across page breaks
  • Devanagari + monochrome-emoji font fallback

Usage:  python3 tools/md2pdf.py INPUT.md OUTPUT.pdf "Doc Title" "Subtitle"
"""
import re
import sys
from pathlib import Path

import markdown
from weasyprint import HTML, CSS

# ── emoji/symbol substitutions ────────────────────────────────────────────
# Monochrome Noto Emoji covers most of these, but a few read better as
# semantic coloured glyphs in a formal printed document.
SUBS = {
    "🔴": '<span class="dot crit">●</span>',
    "🟠": '<span class="dot high">●</span>',
    "🟡": '<span class="dot mod">●</span>',
    "🟢": '<span class="dot low">●</span>',
    "✅": '<span class="ok">✔</span>',
    "❌": '<span class="no">✘</span>',
    "✔": '<span class="ok">✔</span>',
    "🔥": '<span class="hot">★</span>',
    "⚠": '<span class="warn">⚠</span>',
}

# Glyphs absent from DejaVu Sans Mono would fall back to a proportional emoji
# font and wreck the alignment of the ASCII box diagrams. Inside fenced code
# blocks they are swapped for monospace-safe equivalents.
CODE_SUBS = str.maketrans({
    "⏮": "|", "✅": "✔", "❌": "✘", "⟳": "~", "⤓": "v",
    "⬢": "#", "⬤": "●", "🏦": "$", "📄": "▤", "📌": "+",
})
BODY_SUBS = {"₿": "BTC"}          # absent from every installed font

CSS_TEXT = """
@page {
  size: A4;
  margin: 17mm 14mm 16mm 14mm;
  @bottom-left  { content: "ABHEDYA-CHAKRA · Void Hacks() 8.0";
                  font-family: "DejaVu Sans"; font-size: 7pt; color: #94a3b8; }
  @bottom-center{ content: string(doctitle);
                  font-family: "DejaVu Sans"; font-size: 7pt; color: #94a3b8; }
  @bottom-right { content: counter(page) " / " counter(pages);
                  font-family: "DejaVu Sans"; font-size: 7pt; color: #94a3b8; }
}
@page :first { margin: 0; @bottom-left{content:""} @bottom-center{content:""} @bottom-right{content:""} }

html { font-family: "DejaVu Sans", "Noto Sans Devanagari", "Noto Emoji", sans-serif; }
body { font-size: 9.1pt; line-height: 1.45; color: #0f172a; }

/* ── cover ─────────────────────────────────────────────────────── */
.cover { page-break-after: always; height: 297mm; box-sizing: border-box;
         padding: 42mm 20mm 16mm 20mm; background: #0b1020; color: #e2e8f0; }
.cover .kicker { font-size: 10pt; letter-spacing: 3px; color: #22d3ee; text-transform: uppercase; }
.cover h1 { font-size: 34pt; margin: 6mm 0 2mm 0; color: #ffffff; border: 0; padding: 0;
            page-break-before: avoid; string-set: none; }
.cover .dev { font-size: 20pt; color: #22d3ee; margin: 0 0 8mm 0; font-family: "Noto Sans Devanagari"; }
.cover .sub { font-size: 12.5pt; color: #cbd5e1; line-height: 1.6; max-width: 150mm; }
.cover .rule { height: 2px; background: #22d3ee; width: 60mm; margin: 9mm 0; }
.cover table { width: 100%; margin-top: 10mm; font-size: 9.5pt; border: 0; }
.cover table td, .cover tbody tr:nth-child(even) td { border: 0; padding: 2.1mm 0;
                              color: #e2e8f0; background: none; }
.cover table td:first-child { color: #64748b; width: 42mm; text-transform: uppercase;
                              font-size: 8pt; letter-spacing: 1px; }
.cover .foot { position: absolute; bottom: 16mm; font-size: 8.5pt; color: #64748b; }

/* ── headings ──────────────────────────────────────────────────── */
h1 { string-set: doctitle content(); page-break-before: always; font-size: 17pt;
     color: #0b1020; border-bottom: 2.2px solid #22d3ee; padding-bottom: 2mm;
     margin: 0 0 5mm 0; page-break-after: avoid; }
h1.nobreak { page-break-before: avoid; }
h2 { font-size: 12.6pt; color: #0f172a; margin: 7mm 0 2.5mm 0; page-break-after: avoid;
     border-left: 3.5px solid #22d3ee; padding-left: 3mm; }
h3 { font-size: 10.6pt; color: #1e293b; margin: 5mm 0 2mm 0; page-break-after: avoid; }
h4 { font-size: 9.6pt; color: #334155; margin: 4mm 0 1.5mm 0; page-break-after: avoid; }
p { margin: 0 0 2.6mm 0; }

/* ── tables ────────────────────────────────────────────────────── */
table { width: 100%; border-collapse: collapse; margin: 3mm 0 5mm 0; font-size: 7.9pt;
        page-break-inside: auto; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th { background: #0b1020; color: #e2e8f0; text-align: left; padding: 1.7mm 2mm;
     font-weight: bold; border: 0.5px solid #1e293b; font-size: 7.7pt; }
td { padding: 1.5mm 2mm; border: 0.5px solid #cbd5e1; vertical-align: top; }
tbody tr:nth-child(even) td { background: #f1f5f9; }

/* ── code / ASCII diagrams ─────────────────────────────────────── */
pre { font-family: "DejaVu Sans Mono", "Noto Emoji", monospace; font-size: 7.1pt;
      line-height: 1.22; background: #0b1020; color: #cbd5e1; padding: 3mm 3.5mm;
      border-radius: 1.5mm; border-left: 3px solid #22d3ee; white-space: pre;
      overflow: hidden; page-break-inside: avoid; margin: 3mm 0 4mm 0; }
pre code { font-family: inherit; font-size: inherit; background: none; color: inherit;
           padding: 0; border: 0; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.1pt; background: #e2e8f0;
       color: #0b1020; padding: 0.3mm 1mm; border-radius: 1mm; }
th code, td code { font-size: 7.3pt; }

/* ── lists / quotes / misc ─────────────────────────────────────── */
ul, ol { margin: 0 0 3mm 0; padding-left: 6mm; }
li { margin: 0 0 1.1mm 0; }
blockquote { border-left: 3.5px solid #f59e0b; background: #fffbeb; margin: 3mm 0;
             padding: 2.5mm 3.5mm; font-size: 8.8pt; page-break-inside: avoid; }
blockquote p:last-child { margin-bottom: 0; }
hr { border: 0; border-top: 0.6px solid #cbd5e1; margin: 6mm 0; }
a { color: #0e7490; text-decoration: none; }
strong { color: #0b1020; }

/* ── semantic glyphs ───────────────────────────────────────────── */
.dot { font-size: 11pt; line-height: 0; }
.crit { color: #ef4444; } .high { color: #f97316; }
.mod  { color: #f59e0b; } .low  { color: #22c55e; }
.ok { color: #16a34a; font-weight: bold; }
.no { color: #dc2626; font-weight: bold; }
.hot { color: #ef4444; }
.warn { color: #f59e0b; }

/* table-of-contents block */
.toc-wrap ol { padding-left: 5mm; }
"""

COVER = """
<div class="cover">
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <div class="dev">{dev}</div>
  <div class="rule"></div>
  <div class="sub">{sub}</div>
  <table>{rows}</table>
  <div class="foot">{foot}</div>
</div>
"""


def build(src: Path, out: Path, title: str, sub: str, kicker: str,
          dev: str = "अभेद्य चक्र", meta: list | None = None,
          foot: str = "Confidential — hackathon working document"):
    text = src.read_text(encoding="utf-8")

    # Strip the leading H1: the cover page replaces it.
    text = re.sub(r"\A#\s+.*?\n", "", text, count=1)

    # Monospace-safe glyphs inside fenced blocks (keeps ASCII diagrams aligned).
    text = re.sub(r"```[a-z]*\n.*?```",
                  lambda m: m.group(0).translate(CODE_SUBS), text, flags=re.S)
    for k, v in BODY_SUBS.items():
        text = text.replace(k, v)

    html_body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "toc", "attr_list", "sane_lists", "md_in_html"],
        extension_configs={"toc": {"permalink": False}},
    )
    for k, v in SUBS.items():
        html_body = html_body.replace(k, v)

    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in (meta or []))
    cover = COVER.format(kicker=kicker, title=title, dev=dev, sub=sub, rows=rows, foot=foot)

    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
           f"<title>{title}</title></head><body>{cover}{html_body}</body></html>")

    # Docs whose top level is H2 (no H1) drive the running footer from H2 instead.
    css = CSS_TEXT
    if "<h1" not in html_body:
        css += "\nh2 { string-set: doctitle content(); }\n"

    HTML(string=doc, base_url=str(src.parent)).write_pdf(
        out, stylesheets=[CSS(string=css)])
    print(f"✓ {out}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    a = sys.argv[1:]
    build(Path(a[0]), Path(a[1]),
          a[2] if len(a) > 2 else Path(a[0]).stem,
          a[3] if len(a) > 3 else "",
          a[4] if len(a) > 4 else "Void Hacks() 8.0")
