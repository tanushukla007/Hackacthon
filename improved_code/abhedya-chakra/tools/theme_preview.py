"""Render the workstation palette in both sheets without a browser.

Playwright cannot run in this sandbox, so the light theme is proofed by
feeding the real token file to WeasyPrint and rasterising the result. This is
a palette/contrast proof, not a layout screenshot.
"""
import pathlib, sys
import weasyprint, pypdfium2

SRC = pathlib.Path("frontend/src/styles")
tokens = (SRC / "tokens.css").read_text()

def panel(theme):
    return """
    <section class="sheet">
      <div class="strip">
        <b>ABHEDYA-CHAKRA</b>
        <span class="ro"><i>dataset</i> READY</span>
        <span class="ro"><i>rows</i> 250,000</span>
        <span class="ro"><i>fingerprint</i> sha256:977ae37100b38785</span>
        <span class="sw">%s</span>
      </div>
      <div class="body">
        <div class="rail">
          <div class="nav on">Dashboard</div><div class="nav">Investigate</div>
          <div class="nav">Accounts</div><div class="nav">Cases</div><div class="nav">System</div>
        </div>
        <div class="main">
          <div class="card">
            <div class="ct">Risk bands</div>
            <div class="bands">
              <span class="band low">&#9679; LOW 3,833</span>
              <span class="band med">&#9632; MEDIUM 2,234</span>
              <span class="band high">&#9650; HIGH 2</span>
              <span class="band crit">&#9733; CRITICAL 0</span>
            </div>
            <table>
              <tr><th>ACCOUNT</th><th>MRI</th><th>BAND</th><th>ROLE</th></tr>
              <tr><td class="m">545470146222</td><td class="m">65.7</td><td class="high">&#9650; HIGH</td><td>DISTRIBUTOR</td></tr>
              <tr><td class="m">409802925607</td><td class="m">55.0</td><td class="med">&#9632; MEDIUM</td><td>COLLECTOR</td></tr>
            </table>
            <p class="note">OBSERVED &mdash; 2 inbound, 49 outbound transfers, median hold 1 h 4 m.</p>
            <p class="note warn">INFERRED &mdash; fan-out above the 85th percentile for this dataset.</p>
            <p class="note stop">The index is an investigative aid, not a finding of guilt.</p>
            <div class="btns">
              <span class="btn primary">Run trace</span><span class="btn">Export</span>
              <span class="btn on">Layered only</span>
            </div>
            <div class="canvas">
              <span class="chip">source_row_id 163638</span>
              <span class="chip">trc_Z6X7G8Z5ZZZ7BH4B</span>
            </div>
          </div>
        </div>
      </div>
    </section>""" % ("LIGHT" if theme == "dark" else "DARK",)

DOC = """<html data-theme="%s"><head><meta charset="utf-8"><style>
%s
@page { size: 300mm 102mm; margin: 6mm; }
body { background: #808080; font-family: sans-serif; }
.sheet { background: var(--ink); color: var(--text); border: 1px solid var(--line);
         margin-bottom: 6mm; font-size: 9pt; }
.strip { background: var(--surface); border-bottom: 1px solid var(--line); padding: 6px 10px; }
.strip b { font-family: serif; letter-spacing: .12em; color: var(--text); }
.ro { margin-left: 14px; color: var(--muted); font-size: 7.5pt; font-family: monospace; }
.ro i { color: var(--faint); font-style: normal; letter-spacing: .1em; }
.sw { float: right; border: 1px solid var(--line); color: var(--muted); padding: 1px 7px; font-size: 7pt; }
.body { display: table; width: 100%%; table-layout: fixed; }
.rail { display: table-cell; width: 120px; vertical-align: top; background: var(--ink-2); border-right: 1px solid var(--line); padding: 6px 0; }
.nav { padding: 5px 10px; color: var(--text-2); font-size: 8pt; }
.nav.on { color: var(--brass); border-left: 2px solid var(--brass); background: var(--surface-2); }
.main { display: table-cell; vertical-align: top; padding: 10px; }
.card { background: var(--surface); border: 1px solid var(--line); padding: 10px; }
.ct { font-family: serif; color: var(--text); border-bottom: 1px solid var(--line-soft);
      padding-bottom: 5px; margin-bottom: 7px; letter-spacing: .06em; }
.bands span { margin-right: 12px; font-size: 8pt; }
.low { color: var(--moss); } .med { color: var(--ochre); }
.high { color: var(--oxide); } .crit { color: var(--rust); }
table { width: 100%%; border-collapse: collapse; margin: 8px 0; font-size: 8pt; }
th { text-align: left; color: var(--faint); font-weight: 400; font-size: 7pt;
     letter-spacing: .12em; border-bottom: 1px solid var(--line); padding: 4px 6px; }
td { padding: 4px 6px; border-bottom: 1px solid var(--line-soft); color: var(--text-2); }
td.m { font-family: monospace; color: var(--text); }
.note { border-left: 2px solid var(--brass-dim); background: var(--tint-note);
        padding: 6px 9px; margin: 5px 0; color: var(--text-2); font-size: 8pt; }
.note.warn { border-left-color: var(--oxide); background: var(--tint-warn); }
.note.stop { border-left-color: var(--rust); background: var(--tint-stop); }
.btns { margin: 9px 0; }
.btn { border: 1px solid var(--line); padding: 4px 11px; margin-right: 7px;
       color: var(--text-2); font-size: 8pt; }
.btn.primary { background: var(--brass); border-color: var(--brass); color: var(--on-brass); }
.btn.on { border-color: var(--brass); color: var(--brass); background: var(--tint-brass); }
.canvas { background: var(--canvas-bg); border: 1px solid var(--line); padding: 10px; }
.chip { font-family: monospace; font-size: 7.5pt; color: var(--slate-blue);
        border: 1px solid var(--chip-line); background: var(--chip-bg); padding: 1px 5px; margin-right: 8px; }
</style></head><body>%s</body></html>"""

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "samples/_theme_proof")
for theme in ("dark", "light"):
    doc = DOC % (theme, tokens, panel(theme))
    pdf = "%s_%s.pdf" % (out, theme)
    weasyprint.HTML(string=doc).write_pdf(pdf)
    pypdfium2.PdfDocument(pdf)[0].render(scale=2.1).to_pil().save("%s_%s.png" % (out, theme))
    print("wrote %s_%s.png" % (out, theme))
