"""Render the graph hover card in both sheets, without a browser.

Uses the real token/graph CSS and the real fact rows emitted by
src/utils/hoverFacts.js, so what is rendered here is what the component shows.
"""
import json, pathlib, sys
import weasyprint, pypdfium2

ROOT = pathlib.Path(__file__).resolve().parents[1]
S = ROOT / "frontend" / "src" / "styles"
facts = json.loads((ROOT / ".hoverfacts.json").read_text())

def card(title, rows, foot):
    body = "".join(
        "<tr class='g-%s'><td class='k'>%s</td><td class='v mono'>%s</td></tr>"
        % (r["group"], r["k"], r["v"]) for r in rows)
    return ("<div class='hovercard'><div class='hc-head mono'>%s</div>"
            "<table><tbody>%s</tbody></table>"
            "<div class='hc-foot'>%s</div></div>" % (title, body, foot))

panel = (card("545470146222", facts["node"],
              "index and role are assessments \u00b7 click to open the inspector") +
         card("row 163638", facts["edge"], "one transaction, cited by source_row_id"))

DOC = """<html data-theme="%s"><head><meta charset="utf-8"><style>
%s
%s
@page { size: 150mm 78mm; margin: 7mm; }
body { background: var(--ink); font-family: ui-sans-serif, system-ui, sans-serif; }
.wrap { position: relative; display: flex; gap: 10mm; }
.hovercard { position: static; }
.lbl { color: var(--muted); font-size: 8pt; letter-spacing: .14em;
       text-transform: uppercase; margin-bottom: 4px; }
</style></head><body>
<div class="lbl">hover card &mdash; %s sheet</div>
<div class="wrap">%s</div>
</body></html>"""

out = ROOT / "samples" / "_hovercard"
for theme in ("dark", "light"):
    html = DOC % (theme, (S / "tokens.css").read_text(), (S / "graph.css").read_text(),
                  theme, panel)
    pdf = "%s_%s.pdf" % (out, theme)
    weasyprint.HTML(string=html).write_pdf(pdf)
    pypdfium2.PdfDocument(pdf)[0].render(scale=2.6).to_pil().save("%s_%s.png" % (out, theme))
    print("wrote %s_%s.png" % (out, theme))
