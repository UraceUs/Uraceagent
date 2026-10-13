"""Gera o PDF do playbook dos mecânicos (markdown -> HTML com a marca -> Chromium).

Uso (na raiz do repositório):
    python3 docs/playbooks/gerar_pdf_mecanicos.py . docs/playbooks/playbook-mecanicos-e-coaches.pdf

Dono, 13/10 (#199): "O playbook para os mecânicos pode ser em PDF ... focar na parte de
calendários, balcão de peças". Mudou o .md, rode de novo e suba o PDF no mesmo PR.
"""
import base64, pathlib, re, sys
import markdown
from playwright.sync_api import sync_playwright

repo = pathlib.Path(sys.argv[1]); saida = pathlib.Path(sys.argv[2])
md = (repo / "docs/playbooks/playbook-mecanicos-e-coaches.md").read_text(encoding="utf-8")
md = md.replace("O guia do painel inteiro está no playbook geral (`docs/playbooks/playbook-geral.md`).",
                "O guia do painel inteiro está no playbook geral da equipe.")
# sublistas com 2-3 espaços viram 4 (o python-markdown só aninha com 4)
md = re.sub(r"(?m)^ {2,3}(- |\d+\. )", r"    \1", md)
html_corpo = markdown.markdown(md, extensions=["tables", "sane_lists"])
fontes = repo / "command_center/providers/fontes"
def b64(p): return base64.b64encode(p.read_bytes()).decode()
logo = (repo / "command_center/vitrine/static/img/logo.svg").read_text(encoding="utf-8")
logo = re.sub(r"<\?xml[^>]*>", "", logo)
# capa: o primeiro h1 + o parágrafo de subtítulo
html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Playbook dos mecânicos e coaches</title>
<style>
@font-face{{font-family:Archivo;src:url(data:font/ttf;base64,{b64(fontes/'Archivo-Expanded-ExtraBold.ttf')});font-weight:800}}
@font-face{{font-family:Inter;src:url(data:font/ttf;base64,{b64(fontes/'Inter-Regular.ttf')});font-weight:400}}
@font-face{{font-family:Inter;src:url(data:font/ttf;base64,{b64(fontes/'Inter-SemiBold.ttf')});font-weight:600}}
@page{{size:Letter;margin:18mm 16mm 18mm 16mm}}
:root{{--brand:#C4321F;--ink:#1B1B1B;--muted:#5B5650;--rule:#E3DDD5;--wash:#F6F3EF;--azul:#0057B4}}
html{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
body{{font-family:Inter,sans-serif;font-size:10.5pt;line-height:1.5;color:var(--ink);margin:0}}
.capa{{height:236mm;display:flex;flex-direction:column;justify-content:space-between;page-break-after:always;
  border-left:6mm solid var(--brand);padding-left:12mm}}
.capa .logo svg{{width:62mm;height:auto}}
.capa h1{{font-family:Archivo;font-weight:800;font-size:30pt;line-height:1.1;margin:0 0 6mm;text-transform:uppercase;letter-spacing:.01em}}
.capa .sub{{font-size:14pt;font-weight:600;color:var(--brand);margin:0 0 8mm}}
.capa .foco{{display:flex;gap:6mm}}
.capa .foco div{{flex:1;background:var(--wash);border-radius:3mm;padding:5mm}}
.capa .foco b{{display:block;font-family:Archivo;font-size:12pt;text-transform:uppercase;margin-bottom:2mm}}
.capa .rodape{{font-size:9pt;color:var(--muted)}}
h1{{display:none}}
h2{{margin-top:8mm !important;font-family:Archivo;font-weight:800;text-transform:uppercase;font-size:15pt;color:var(--ink);margin:0 0 4mm;
  padding:3mm 0 2mm;border-bottom:1.2mm solid var(--brand);page-break-after:avoid}}
h2.novo{{page-break-before:always}}
h3{{font-size:12pt;font-weight:600;color:var(--brand);margin:6mm 0 2mm;page-break-after:avoid}}
h4{{font-size:10.5pt;font-weight:600;margin:4mm 0 1.5mm;page-break-after:avoid}}
p{{margin:0 0 2.5mm}} ul,ol{{margin:0 0 3mm;padding-left:6mm}} li{{margin:0 0 1mm}}
strong{{font-weight:600}}
code{{font-family:Inter;background:var(--wash);padding:0 1mm;border-radius:1mm}}
table{{width:100%;border-collapse:collapse;margin:2mm 0 4mm;font-size:9.5pt;page-break-inside:auto}}
tr{{page-break-inside:avoid}}
th{{background:var(--ink);color:#fff;text-align:left;font-weight:600;padding:2mm 2.5mm}}
td{{border-bottom:.3mm solid var(--rule);padding:2mm 2.5mm;vertical-align:top}}
tr:nth-child(even) td{{background:var(--wash)}}
hr{{display:none}}
</style></head><body>
<section class="capa">
  <div class="logo">{logo}</div>
  <div>
    <h1 style="display:block">Playbook dos mecânicos e coaches</h1>
    <p class="sub">Calendário e balcão de peças, no Command Center</p>
    <div class="foco">
      <div><b>Calendário</b>Meu dia: quem está marcado hoje, na semana e no mês, e o que fazer em cada kart.</div>
      <div><b>Balcão de peças</b>Ler a peça com a câmera e tocar no piloto que usou. O gerente revisa e cobra.</div>
    </div>
  </div>
  <div class="rodape">URACE · Orlando, Flórida · atualizado em 13/10/2026 · uso interno da equipe</div>
</section>
{html_corpo}
</body></html>"""
# cada capítulo (h2) começa numa página nova, menos o primeiro
n = [0]
QUEBRA = {3, 4, 6}          # calendário, balcão e checklists começam numa página nova
def h2(m):
    n[0] += 1
    return m.group(0).replace("<h2>", '<h2 class="novo">') if n[0] in QUEBRA else m.group(0)
html = re.sub(r"<h2>", lambda m: h2(m), html)
# o primeiro bloco do markdown (título e subtítulo) já está na capa
html = re.sub(r'<h1>.*?</h1>\s*<p><strong>Command Center.*?</p>\s*<p>Para quem.*?</p>', "", html, count=1, flags=re.S)
tmp = pathlib.Path(__import__("tempfile").mkdtemp()) / "playbook.html"; tmp.write_text(html, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=__import__("os").environ.get("PW_CHROMIUM") or None)
    pg = b.new_page(); pg.goto(tmp.as_uri()); pg.wait_for_timeout(300)
    pg.pdf(path=str(saida), format="Letter", print_background=True, display_header_footer=True,
           header_template="<span></span>",
           footer_template='<div style="font-family:sans-serif;font-size:8px;color:#5B5650;width:100%;padding:0 16mm;display:flex;justify-content:space-between">'
                           '<span>URACE · Playbook dos mecânicos e coaches</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
           margin={"top": "16mm", "bottom": "16mm", "left": "16mm", "right": "16mm"})
    b.close()
print(saida)
