"""Etiquetas QR de prateleira e duplicatas do catálogo do QuickBooks (#187).

Dono, 12/10: *"leia os produtos que a gente tem no QuickBooks … se tiver duplicata, identifica
a duplicata, normalmente tem produtos que são para chassis diferentes … esses são produtos
diferentes, mas alguns produtos são gerais"* e *"monta uma arte com o QR Code e o nome da peça
em inglês para ser colocado em cada prateleira … só de colocar a câmera em cima, já lê"*.

- **Produtos**: o espelho `qbo_items` (o catálogo inteiro, paginado), sem categoria, serviço,
  pacote nem o que é de aluguel ou serviço.
- **Duplicatas**: só um relatório; nada é unido nem apagado no QuickBooks. Dois nomes são o
  mesmo produto quando, normalizados, ficam iguais ou quase iguais **e** têm as mesmas marcas,
  chassis, motores e medidas. "OTK Clamp 30mm" e "OTK Clamp 32mm" são produtos diferentes.
- **QR**: `URQ<id no QuickBooks>`. O balcão, na primeira leitura, cria o item de estoque ligado
  ao QuickBooks (nome e preço do catálogo) e o código; daí em diante é uma peça como as outras.
"""
import difflib
import io
import os
import re
import unicodedata

from command_center.db import atualizar, um, todos

PREFIXO = "URQ"
RX_URQ = re.compile(r"^URQ(\d{1,12})$", re.I)
TIPOS_FORA = {"category", "service", "group", "bundle"}
CATEGORIAS_FORA = {"Rental", "Service"}           # aluguel e serviço não vão para a prateleira
PARECIDO = 0.88

# O que faz dois nomes parecidos serem produtos DIFERENTES: marca, chassi, motor, categoria do kart.
DISTINGUE = {
    "otk", "tonykart", "tony", "kosmic", "exprit", "redspeed", "parolin", "crg", "birel", "birelart", "compkart",
    "benik", "pkt", "senzo", "greyhound", "kartech", "jecko", "rev", "energy", "ipk", "praga", "kart republic", "kr",
    "iame", "x30", "ka100", "swift", "rotax", "max", "evo", "tillotson", "briggs", "lo206", "vortex", "rok", "tm",
    "kz", "okn", "ok", "honda", "yamaha", "comer", "micro", "mini", "cadet", "junior", "jr", "senior", "sr",
    "shifter", "4t", "2t", "4stroke", "2stroke", "front", "rear", "left", "right", "upper", "lower", "inner",
    "outer", "aim", "mychron", "alpinestars", "arai", "bell", "sparco", "bengio", "evs", "evinco", "levanto",
    "maxxis", "mg", "vega", "dellorto", "hilliard", "hillard", "rain", "dry", "set", "pair", "kit", "unit",
}
_VAZIAS = {"for", "the", "with", "w", "of", "a", "an", "and", "de", "do", "da", "e", "para", "to", "in", "on"}
_TROCAS = {"chassi": "chassis", "tony kart": "tonykart", "birel art": "birelart", "mini swift": "swift",
           "jr/sr": "junior senior", "jr/senior": "junior senior", "micro/mini": "micro mini",
           "cadet/mini": "cadet mini", "4 stroke": "4stroke", "2 stroke": "2stroke", "ok-n": "okn"}


class ErroEtiqueta(ValueError):
    """Regra violada. A mensagem é para a tela."""


# ------------------------------------------------------------------ o catálogo
def categoria(full_name, name):
    fn = full_name or name or ""
    return fn.split(":")[0].strip() if ":" in fn else ""


def produtos(con, categorias=None, incluir_fora=False):
    """Os produtos físicos do catálogo, com a categoria do QuickBooks."""
    out = []
    for q in todos(con, "SELECT id, name, full_name, price, type FROM qbo_items WHERE active=1 ORDER BY full_name, name"):
        if (q["type"] or "").lower() in TIPOS_FORA:
            continue
        cat = categoria(q["full_name"], q["name"])
        if not incluir_fora and cat in CATEGORIAS_FORA:
            continue
        if categorias and cat not in categorias:
            continue
        out.append({"id": q["id"], "name": (q["name"] or "").strip(), "full_name": q["full_name"], "price": q["price"],
                    "type": q["type"], "categoria": cat, "codigo": PREFIXO + str(q["id"])})
    return out


def categorias(con):
    contagem = {}
    for p in produtos(con):
        contagem[p["categoria"]] = contagem.get(p["categoria"], 0) + 1
    return [{"nome": k, "itens": v} for k, v in sorted(contagem.items(), key=lambda x: (x[0] == "", x[0].lower()))]


# ------------------------------------------------------------------ duplicatas
def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def tokens(nome):
    s = _sem_acento((nome or "").lower()).replace("∕", "/").replace("’", "'")
    for de, para in _TROCAS.items():
        s = s.replace(de, para)
    s = re.sub(r"(\d)\s*(mm|cm|ft|in|v|ah|t|l)\b", r"\1\2", s)      # "30 mm" = "30mm"
    s = re.sub(r"[^a-z0-9/#.]+", " ", s)
    out = []
    for t in s.replace("/", " ").split():
        t = t.strip(".#")
        if not t or t in _VAZIAS:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss") and not re.search(r"\d", t):
            t = t[:-1]                                           # walls = wall
        out.append(t)
    return out


def _marcas(toks):
    """Medidas, números e marcas: se diferirem, são produtos diferentes (chassi, motor, tamanho)."""
    return frozenset(t for t in toks if t in DISTINGUE or re.search(r"\d", t))


def duplicatas(itens):
    """[{motivo, itens}] — grupos de nomes que parecem o mesmo produto. Nunca une nada sozinho."""
    info = [(p, tokens(p["name"])) for p in itens]
    pai = list(range(len(info)))
    motivo = {}

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    chaves = {}
    for i, (_, t) in enumerate(info):
        if t:
            chaves.setdefault(" ".join(sorted(t)), []).append(i)
    for grupo in chaves.values():
        for j in grupo[1:]:
            pai[raiz(j)] = raiz(grupo[0])
            motivo[raiz(grupo[0])] = "mesmo nome"
    juntos = [(i, " ".join(sorted(t)), _marcas(t)) for i, (_, t) in enumerate(info) if t]
    for a in range(len(juntos)):
        ia, sa, ma = juntos[a]
        for b in range(a + 1, len(juntos)):
            ib, sb, mb = juntos[b]
            if ma != mb or raiz(ia) == raiz(ib):
                continue
            sm = difflib.SequenceMatcher(None, sa, sb)
            if sm.real_quick_ratio() < PARECIDO or sm.quick_ratio() < PARECIDO or sm.ratio() < PARECIDO:
                continue
            ra, rb = raiz(ia), raiz(ib)
            pai[rb] = ra
            motivo[ra] = motivo.get(ra) or motivo.get(rb) or "nome parecido"
    grupos = {}
    for i in range(len(info)):
        grupos.setdefault(raiz(i), []).append(info[i][0])
    out = [{"motivo": motivo.get(r, "nome parecido"), "itens": g} for r, g in grupos.items() if len(g) > 1]
    return sorted(out, key=lambda g: g["itens"][0]["name"].lower())


# ------------------------------------------------------------------ o balcão lê o QR
def item_do_qr(con, codigo, por=None):
    """`URQ<id>` → o item de estoque ligado àquele item do QuickBooks (criado na primeira leitura).
    Devolve o id do item de estoque, ou None se o código não é desta etiqueta ou o item sumiu."""
    from command_center.providers import balcao, estoque
    m = RX_URQ.match((codigo or "").strip())
    if not m:
        return None
    q = um(con, "SELECT id, name, full_name, price FROM qbo_items WHERE id=? AND active=1", (m.group(1),))
    if not q:
        return None
    it = um(con, "SELECT id FROM stock_items WHERE qbo_item_id=? AND active=1 ORDER BY id LIMIT 1", (q["id"],))
    if it:
        iid = it["id"]
    else:
        preco = q["price"] if q["price"] and q["price"] > 0 else None
        iid = estoque.criar_item(con, "peca", q["name"] or q["full_name"], price=preco)
        atualizar(con, "stock_items", iid, qbo_item_id=q["id"], qbo_item_name=q["full_name"] or q["name"])
    balcao.cadastrar_codigo(con, PREFIXO + q["id"], iid, por, origem="urace")
    return iid


# ------------------------------------------------------------------ a arte
# A identidade do site (vitrine/static/site.css): preto, vermelho de corrida, Archivo Expanded
# nos títulos e Inter no texto, e a logo do urace.us desenhada a partir do mesmo SVG.
PRETO, VERMELHO, CINZA = "#0B0B0F", "#D91617", "#717286"
FONTES = os.path.join(os.path.dirname(__file__), "fontes")
LOGO = os.path.join(os.path.dirname(__file__), "..", "vitrine", "static", "img", "logo.svg")
_RX_CMD = re.compile(r"[MLHVCZ]|-?\d*\.?\d+(?:e-?\d+)?")


def _fontes():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for nome in ("Archivo-Expanded-ExtraBold", "Inter-Regular", "Inter-SemiBold"):
        if nome not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(nome, os.path.join(FONTES, nome + ".ttf")))


def _logo():
    """[(cor, [(comando, números)])] do logo.svg (só M L H V C Z absolutos, que é o que ele usa)."""
    svg = open(LOGO, encoding="utf-8").read()
    out = []
    for d, cor in re.findall(r'<path[^>]*?\sd="([^"]+)"[^>]*?fill="(#[0-9A-Fa-f]{6})"', svg):
        cmds, atual = [], None
        for tok in _RX_CMD.findall(d):
            if tok.isalpha():
                atual = [tok, []]
                cmds.append(atual)
            else:
                atual[1].append(float(tok))
        out.append((cor, cmds))
    return out


def _desenha_logo(cv, x, y, largura):
    """A logo (120 × 20 no SVG) com a base em (x, y)."""
    from reportlab.lib.colors import HexColor
    k = largura / 120.0
    for cor, cmds in _logo():
        p = cv.beginPath()
        cx = cy = 0.0

        def pt(a, b):
            return x + a * k, y + (20 - b) * k
        for c, n in cmds:
            if c == "M":
                cx, cy = n[0], n[1]
                p.moveTo(*pt(cx, cy))
                for i in range(2, len(n), 2):
                    cx, cy = n[i], n[i + 1]
                    p.lineTo(*pt(cx, cy))
            elif c == "L":
                for i in range(0, len(n), 2):
                    cx, cy = n[i], n[i + 1]
                    p.lineTo(*pt(cx, cy))
            elif c == "H":
                for v in n:
                    cx = v
                    p.lineTo(*pt(cx, cy))
            elif c == "V":
                for v in n:
                    cy = v
                    p.lineTo(*pt(cx, cy))
            elif c == "C":
                for i in range(0, len(n), 6):
                    p.curveTo(*pt(n[i], n[i + 1]), *pt(n[i + 2], n[i + 3]), *pt(n[i + 4], n[i + 5]))
                    cx, cy = n[i + 4], n[i + 5]
            elif c == "Z":
                p.close()
        cv.setFillColor(HexColor(cor))
        cv.drawPath(p, stroke=0, fill=1)


def _linhas(cv, texto, fonte, tam, largura, maximo):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if cv.stringWidth(teste, fonte, tam) <= largura:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    if len(linhas) > maximo:
        linhas = linhas[:maximo]
        while linhas[-1] and cv.stringWidth(linhas[-1] + "…", fonte, tam) > largura:
            linhas[-1] = linhas[-1][:-1]
        linhas[-1] += "…"
    return linhas


def _etiqueta(cv, p, x, y, larg, alt):
    """Uma etiqueta: faixa preta com a logo e o corte em diagonal vermelho (o "racing" do site),
    QR grande, o nome em inglês em Archivo Expanded, a categoria em vermelho e o código."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import mm
    preto, vermelho, cinza = HexColor(PRETO), HexColor(VERMELHO), HexColor(CINZA)
    cv.saveState()
    caixa = cv.beginPath()
    caixa.roundRect(x, y, larg, alt, 2.5 * mm)
    cv.clipPath(caixa, stroke=0, fill=0)
    cv.setFillColor(white)
    cv.rect(x, y, larg, alt, stroke=0, fill=1)
    faixa = 11 * mm
    cv.setFillColor(preto)
    cv.rect(x, y + alt - faixa, larg, faixa, stroke=0, fill=1)
    corte = cv.beginPath()                          # a diagonal vermelha no canto da faixa
    corte.moveTo(x + larg - 26 * mm, y + alt)
    corte.lineTo(x + larg, y + alt)
    corte.lineTo(x + larg, y + alt - faixa)
    corte.lineTo(x + larg - 26 * mm - faixa * 0.6, y + alt - faixa)
    corte.close()
    cv.setFillColor(vermelho)
    cv.drawPath(corte, stroke=0, fill=1)
    cv.setFillColor(vermelho)
    cv.rect(x, y, larg, 1.6 * mm, stroke=0, fill=1)  # a linha vermelha da base
    _desenha_logo(cv, x + 4 * mm, y + alt - faixa + (faixa - 5 * mm) / 2, 30 * mm)
    cv.setFillColor(white)
    cv.setFont("Archivo-Expanded-ExtraBold", 6.5)
    cv.drawRightString(x + larg - 4 * mm, y + alt - faixa + faixa / 2 - 1.1 * mm, "SCAN · PARTS")
    lado = min(alt - faixa - 7 * mm, larg * 0.44)
    w = QrCodeWidget(p["codigo"], barLevel="M", barFillColor=preto)
    b = w.getBounds()
    d = Drawing(lado, lado, transform=[lado / (b[2] - b[0]), 0, 0, lado / (b[3] - b[1]), 0, 0])
    d.add(w)
    renderPDF.draw(d, cv, x + 2.5 * mm, y + 1.6 * mm + (alt - faixa - 1.6 * mm - lado) / 2)
    tx = x + 2.5 * mm + lado + 2.5 * mm
    tl = x + larg - 4 * mm - tx
    tam = 11 if len(p["name"]) <= 40 else 9.5
    topo = y + alt - faixa - 6 * mm
    cv.setFillColor(preto)
    for i, linha in enumerate(_linhas(cv, p["name"], "Archivo-Expanded-ExtraBold", tam, tl, 4)):
        cv.setFont("Archivo-Expanded-ExtraBold", tam)
        cv.drawString(tx, topo - i * tam * 0.42 * mm, linha)
    if p.get("categoria"):
        cv.setFillColor(vermelho)
        cv.setFont("Inter-SemiBold", 7.5)
        cv.drawString(tx, y + 9.5 * mm, p["categoria"].upper()[:40])
    cv.setFillColor(cinza)
    cv.setFont("Inter-Regular", 8)
    cv.drawString(tx, y + 5 * mm, p["codigo"])
    cv.restoreState()
    cv.setStrokeColor(HexColor("#D8D8DE"))
    cv.setLineWidth(0.5)
    cv.roundRect(x, y, larg, alt, 2.5 * mm, stroke=1, fill=0)


def pdf(itens, formato="folha"):
    """`folha`: 8 por página Letter (2 × 4), para recortar. `uma`: uma etiqueta grande por página."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    if not itens:
        raise ErroEtiqueta("nenhum produto para imprimir")
    if formato not in ("folha", "uma"):
        raise ErroEtiqueta("formato: folha ou uma")
    _fontes()
    buf = io.BytesIO()
    if formato == "uma":
        larg, alt = 100 * mm, 62 * mm
        cv = canvas.Canvas(buf, pagesize=(larg + 8 * mm, alt + 8 * mm))
        cv.setTitle("URACE shelf labels")
        for p in itens:
            _etiqueta(cv, p, 4 * mm, 4 * mm, larg, alt)
            cv.showPage()
    else:
        cv = canvas.Canvas(buf, pagesize=letter)
        cv.setTitle("URACE shelf labels")
        pw, ph = letter
        margem, gap = 8 * mm, 4 * mm
        larg = (pw - 2 * margem - gap) / 2
        alt = (ph - 2 * margem - 3 * gap) / 4
        for n, p in enumerate(itens):
            pos = n % 8
            col, lin = pos % 2, pos // 2
            _etiqueta(cv, p, margem + col * (larg + gap), ph - margem - (lin + 1) * alt - lin * gap, larg, alt)
            if pos == 7:
                cv.showPage()
        if len(itens) % 8:
            cv.showPage()
    cv.save()
    return buf.getvalue()
