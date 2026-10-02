"""Aligned ASCII box builder — guarantees equal line widths in mockups."""
def box(lines, width=None, pad=1):
    body = [l for l in lines if l not in ("---", "===")]
    w = width or (max(len(l) for l in body) + pad * 2)
    out = ["┌" + "─" * w + "┐"]
    for l in lines:
        if l == "---":
            out.append("├" + "─" * w + "┤")
        else:
            out.append("│" + " " * pad + l.ljust(w - pad * 2) + " " * pad + "│")
    out.append("└" + "─" * w + "┘")
    return "\n".join(out)

def check(md_path):
    import re
    txt = open(md_path).read()
    bad = []
    for m in re.finditer(r"```[a-z]*\n(.*?)```", txt, re.S):
        run = []
        for ln in m.group(1).split("\n") + [""]:
            if ln[:1] in "┌│├└":
                run.append(ln)
            else:
                if len(run) > 2 and len(set(len(x) for x in run)) > 1:
                    bad.append(run[0][:50] + " widths=" + str(sorted(set(len(x) for x in run))))
                run = []
    return bad
