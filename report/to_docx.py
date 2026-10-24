"""Convert the typst technical report into an editable Word document.

Structure is parsed from the typst source so headings, tables and figure
placement survive. Block equations are embedded as rendered images, because
Word's native equation format cannot be produced from this source; everything
else stays live text that can be edited and marked up.
"""
import re, pathlib
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = pathlib.Path(".")
SRC = ROOT / "report/painface_technical_report.typ"
OUT = ROOT / "report/Pain-Face_Technical_Report.docx"
PAGE_W = 6.3                                   # inches of usable width

INK = RGBColor(0x11, 0x11, 0x11)
MUTED = RGBColor(0x5A, 0x5A, 0x5A)

GREEK = {"kappa":"κ","sigma":"σ","lambda":"λ","delta":"δ","rho":"ρ","epsilon":"ε",
         "mu":"μ","Delta":"Δ","Sigma":"Σ","Omega":"Ω","tau":"τ","alpha":"α","beta":"β"}

# ───────────────────────────── source parsing ─────────────────────────────
src = SRC.read_text()
body = src[src.index("*Abstract.*"):]
body = body[:body.index("#bibliography(")] if "#bibliography(" in body else body

cite_order, cites = [], {}
for key in re.findall(r"@([a-z]+[0-9]{4})", body):
    if key not in cites:
        cite_order.append(key); cites[key] = len(cite_order)

eq_imgs = sorted((ROOT / "report/eq").glob("eq*.png"))
eq_iter = iter(eq_imgs)

def match_bracket(s, i):
    """Index just past the ']' matching the '[' at i."""
    d = 0
    while i < len(s):
        if s[i] == "[": d += 1
        elif s[i] == "]":
            d -= 1
            if d == 0: return i + 1
        i += 1
    return len(s)

def inline(text):
    """Typst inline markup -> a list of (text, style) runs."""
    text = re.sub(r"@([a-z]+[0-9]{4})", lambda m: f"[{cites.get(m.group(1),'?')}]", text)
    text = text.replace("#kw[", "*KW*").replace("\\/", "/").replace("\\_", "_")
    text = re.sub(r"#super\[([^\]]*)\]", r"^\1", text)
    text = re.sub(r"#sub\[([^\]]*)\]", r"\1", text)
    text = re.sub(r"#text\([^)]*\)\[([^\]]*)\]", r"\1", text)
    def demath(m):
        e = m.group(1)
        for k, v in GREEK.items(): e = e.replace(k, v)
        e = (e.replace("<=", "≤").replace(">=", "≥").replace("times", "×")
               .replace("dot", "·").replace("->", "→").replace("in ", "∈ ")
               .replace("sqrt", "√").replace("macron(C)", "C̄").replace("_", "")
               .replace("^", "^").replace("quad", "  ").replace('"', ""))
        return e.strip()
    text = re.sub(r"\$([^$]*)\$", demath, text)
    runs, pos = [], 0
    for m in re.finditer(r"\*KW\*([^\]]*)\]|\*([^*]+?)\*|`([^`]+)`", text):
        if m.start() > pos: runs.append((text[pos:m.start()], ""))
        runs.append(((m.group(1) or m.group(2) or m.group(3)),
                     "b" if (m.group(1) or m.group(2)) else "c"))
        pos = m.end()
    if pos < len(text): runs.append((text[pos:], ""))
    return [(t.replace("\n", " "), s) for t, s in runs if t]

def clean_head(t):
    t = re.sub(r"#sub\[([^\]]*)\]", r"\1", t)
    t = re.sub(r"#super\[([^\]]*)\]", r"\1", t)
    t = re.sub(r"[#*`$]", "", t)
    return t.strip()

def parse(txt):
    """Walk the source into an ordered block list."""
    out, i = [], 0
    while i < len(txt):
        while i < len(txt) and txt[i] in " \t\n":    # align to the next real token
            i += 1
        if i >= len(txt): break
        if txt.startswith("#shot(", i) or txt.startswith("#figure(", i):
            j = txt.index("caption:", i) if txt.startswith("#figure(", i) else None
            path = re.search(r'"([^"]+\.(?:png|svg))"', txt[i:i+200]).group(1)
            cb = txt.index("[", j if j else i + 6)
            ce = match_bracket(txt, cb)
            w = re.search(r"w:\s*(\d+)%|width:\s*(\d+)%", txt[i:ce])
            frac = int((w.group(1) or w.group(2))) / 100 if w else 1.0
            out.append(("fig", path.replace(".svg", ".png"), txt[cb+1:ce-1], frac))
            i = txt.index("\n", ce) if "\n" in txt[ce:] else len(txt); continue
        if txt.startswith("#block(", i) and "#table(" in txt[i:i+60]:
            i = txt.index("#table(", i)
        if txt.startswith("#table(", i):
            depth, j = 0, i + 6
            while j < len(txt):
                if txt[j] == "(": depth += 1
                elif txt[j] == ")":
                    depth -= 1
                    if depth == 0: break
                j += 1
            blk = txt[i:j+1]
            ncol = len(re.search(r"columns:\s*\(([^)]*)\)", blk).group(1).split(","))
            cells, k = [], blk.index(")") + 1
            while k < len(blk):
                if blk[k] == "[":
                    e = match_bracket(blk, k); cells.append(blk[k+1:e-1]); k = e
                else: k += 1
            out.append(("table", ncol, cells)); i = j + 1; continue
        if txt.startswith("#note[", i):
            e = match_bracket(txt, i + 5)
            out.append(("note", txt[i+6:e-1])); i = e; continue
        if txt.startswith("```", i):
            e = txt.index("```", i + 3) + 3
            out.append(("code", txt[i:e].strip("`").split("\n", 1)[-1])); i = e; continue
        m = re.match(r"(?m)^(=+) (.+)$", txt[i:])
        if m:
            out.append(("h", len(m.group(1)), clean_head(m.group(2).strip()))); i += m.end(); continue
        m = re.match(r"(?ms)^\$ .*?\$\s*$", txt[i:])
        if m:
            try: out.append(("eq", str(next(eq_iter))))
            except StopIteration: pass
            i += m.end(); continue
        if txt.startswith("#text(", i):
            b = txt.index("[", i); e = match_bracket(txt, b)
            out.append(("small", txt[b+1:e-1])); i = e; continue
        nl = txt.find("\n\n", i)
        nl = len(txt) if nl < 0 else nl
        chunk = txt[i:nl].strip()
        if chunk and not chunk.startswith(("#v(", "#line(", "#pagebreak", "#align", "//")):
            if chunk.startswith("+ ") or chunk.startswith("- "):
                for line in re.split(r"(?m)^[+-] ", chunk):
                    if line.strip(): out.append(("li", line.strip()))
            else:
                out.append(("p", chunk))
        i = nl + 2
    return out

# ───────────────────────────── docx emission ──────────────────────────────
doc = Document()
st = doc.styles["Normal"]
st.font.name = "Calibri"; st.font.size = Pt(10.5); st.font.color.rgb = INK
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
for s in doc.sections:
    s.left_margin = s.right_margin = Inches(1.0)
    s.top_margin = s.bottom_margin = Inches(0.9)

def para(runs, size=10.5, italic=False, color=INK, space=6, align=None):
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(space)
    if align: p.alignment = align
    for t, style in runs:
        r = p.add_run(t); r.font.size = Pt(size); r.font.color.rgb = color
        r.bold = style == "b"; r.italic = italic
        if style == "c": r.font.name = "Consolas"; r.font.size = Pt(size - 0.8)
    return p

ttl = doc.add_paragraph(); ttl.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = ttl.add_run("Pain-Face: A Multimodal Platform Combining Facial Action-Unit "
                "Analysis with Remote Photoplethysmography for Automatic Pain Assessment")
r.bold = True; r.font.size = Pt(17); r.font.color.rgb = INK
para([("Mohammed Naveed Shariff", "")], size=11.5, align=WD_ALIGN_PARAGRAPH.CENTER, space=2)
para([("Technical Report", "")], size=9, color=MUTED, align=WD_ALIGN_PARAGRAPH.CENTER, space=14)

figno = 0
for blk in parse(body):
    kind = blk[0]
    if kind == "h":
        lvl, text = blk[1], blk[2]
        h = doc.add_heading(text, level=min(lvl, 3))
        for rr in h.runs: rr.font.color.rgb = INK
    elif kind == "p":
        para(inline(blk[1]), align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    elif kind == "li":
        p = doc.add_paragraph(style="List Bullet"); p.paragraph_format.space_after = Pt(3)
        for t, s_ in inline(blk[1]):
            r = p.add_run(t); r.bold = s_ == "b"; r.font.size = Pt(10.5)
            if s_ == "c": r.font.name = "Consolas"
    elif kind == "note":
        p = para(inline(blk[1]), size=10)
        p.paragraph_format.left_indent = Inches(0.3)
        p.paragraph_format.right_indent = Inches(0.3)
    elif kind == "eq":
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(8)
        try: p.add_run().add_picture(blk[1], height=Inches(0.26))
        except Exception: pass
    elif kind == "small":
        para(inline(blk[1]), size=8.5, color=MUTED, space=10)
    elif kind == "code":
        p = doc.add_paragraph(); p.paragraph_format.left_indent = Inches(0.25)
        r = p.add_run(blk[1]); r.font.name = "Consolas"; r.font.size = Pt(8.5)
    elif kind == "fig":
        _, path, cap, frac = blk
        f = (ROOT / "report" / path).resolve()
        if not f.exists(): f = (ROOT / path.replace("../", "")).resolve()
        if f.exists():
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(3)
            p.add_run().add_picture(str(f), width=Inches(PAGE_W * min(frac, 1.0)))
            figno += 1
            c = para([(f"Figure {figno}: ", "b")] + inline(cap), size=8.5, color=MUTED,
                     space=12, align=WD_ALIGN_PARAGRAPH.CENTER)
    elif kind == "table":
        _, ncol, cells = blk
        rows = max(len(cells) // ncol, 1)
        t = doc.add_table(rows=rows, cols=ncol); t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for idx, cell in enumerate(cells[:rows * ncol]):
            tc = t.cell(idx // ncol, idx % ncol)
            tc.text = ""
            p = tc.paragraphs[0]; p.paragraph_format.space_after = Pt(2)
            for tx, s_ in inline(cell):
                r = p.add_run(tx); r.font.size = Pt(8.5)
                r.bold = (s_ == "b") or idx < ncol
                if s_ == "c": r.font.name = "Consolas"
        doc.add_paragraph().paragraph_format.space_after = Pt(6)

# references, taken from the compiled PDF so the numbering matches exactly
doc.add_heading("References", level=1)
from pypdf import PdfReader
pdf = PdfReader(str(ROOT / "report/Pain-Face_Technical_Report.pdf"))
txt = "\n".join((pg.extract_text() or "") for pg in pdf.pages)
refs = re.findall(r"\[\d+\]\s+(.+?)(?=\n\[\d+\]|\Z)", txt[txt.rindex("References"):], re.S)
for i, ref in enumerate(refs, 1):
    clean = " ".join(ref.split())
    clean = re.sub(r"Pain-Face\s+.\s+Technical Report\s*\d*", "", clean).strip()
    para([(f"[{i}] ", "b"), (clean, "")], size=9, space=4)

doc.save(str(OUT))
print(f"{OUT}  |  {figno} figures  |  {len(refs)} references  |  {len(cite_order)} cited works")
