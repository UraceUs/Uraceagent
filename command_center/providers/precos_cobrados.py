"""Preços já cobrados — o histórico das invoices do QuickBooks, linha por linha.

Dono, 28/09: montando invoices pelo AI Command, a IA parou e perguntou o preço de cada peça
("não consigo puxar o histórico de faturas nem o catálogo de peças"). O dado existe: está nas
invoices que a URACE já mandou. Este módulo o lê do espelho (`invoice_lines`, preenchido pela
sincronia do QuickBooks) e responde três perguntas:

- quanto se cobrou desta peça, e de quem, e quando (`historico`);
- qual o preço de referência de cada item — o último, o mais comum, a faixa (`tabela`);
- o valor proposto bate com algo que já foi cobrado? (`ja_cobrado`).

Só leitura, só do espelho: nada aqui chama o QuickBooks nem inventa valor. Sem histórico, a
resposta é "sem histórico" — e aí vale o que o dono disser.
"""
import re
from collections import Counter

from command_center.db import todos

_BASE = """SELECT l.item_id, l.item_name, l.description, l.qty, l.unit_price, l.amount,
                  i.issued_on, i.doc_number, i.customer_ref, c.name AS cliente, i.customer_email
             FROM invoice_lines l JOIN invoices i ON i.id = l.invoice_id
             LEFT JOIN clients c ON c.id = i.client_id
            WHERE l.unit_price IS NOT NULL AND l.unit_price > 0"""


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def historico(con, termo=None, item_id=None, customer_ref=None, limite=15):
    """Cobranças (mais recentes primeiro) cujo item ou descrição contém o termo, ou do item_id."""
    sql, p = _BASE, []
    if item_id:
        sql += " AND l.item_id = ?"
        p.append(str(item_id))
    if customer_ref:
        sql += " AND i.customer_ref = ?"
        p.append(str(customer_ref))
    linhas = todos(con, sql + " ORDER BY COALESCE(i.issued_on,'') DESC, l.id DESC", tuple(p))
    if termo:
        alvo = _norm(termo)
        linhas = [l for l in linhas if alvo and (alvo in _norm(l["item_name"]) or alvo in _norm(l["description"]))]
    return [dict(l) for l in linhas[:limite]]


def _resume(linhas):
    valores = [float(l["unit_price"]) for l in linhas]
    ult = linhas[0]
    return {"item_id": ult["item_id"], "item": ult["item_name"], "vezes": len(valores),
            "ultimo": valores[0], "ultimo_em": ult["issued_on"], "ultimo_cliente": ult["cliente"] or ult["customer_email"],
            "mais_comum": Counter(valores).most_common(1)[0][0], "minimo": min(valores), "maximo": max(valores)}


def tabela(con, termos=None, limite=60):
    """Um resumo por item (agrupado pelo id do QuickBooks; sem id, pelo nome). Com `termos`,
    só os itens cujo nome ou descrição contém algum deles; sem termos, os mais cobrados."""
    grupos = {}
    for l in todos(con, _BASE + " ORDER BY COALESCE(i.issued_on,'') DESC, l.id DESC"):
        chave = l["item_id"] or _norm(l["item_name"])
        if chave:
            grupos.setdefault(chave, []).append(l)
    if termos:
        alvos = [_norm(t) for t in termos if _norm(t)]
        grupos = {k: v for k, v in grupos.items()
                  if any(a in _norm(v[0]["item_name"]) or any(a in _norm(x["description"]) for x in v) for a in alvos)}
    resumo = [_resume(v) for v in grupos.values()]
    resumo.sort(key=lambda r: (-r["vezes"], r["item"] or ""))
    return resumo[:limite]


def ja_cobrado(con, item_id, valor):
    """Se `valor` já foi cobrado deste item, a cobrança mais recente com esse valor; senão None."""
    if not item_id or valor is None:
        return None
    for l in historico(con, item_id=item_id, limite=500):
        if abs(float(l["unit_price"]) - float(valor)) < 0.01:
            return l
    return None


def termos_do_catalogo(con, texto):
    """Itens do catálogo cujo nome aparece no texto (palavras de 3+ letras, todas presentes).
    É assim que "Chain 108" e "rear bumper bolt" viram consulta sem o dono digitar id."""
    t = f" {_norm(texto)} "
    achados = []
    nomes = {r["item_name"] for r in todos(con, "SELECT DISTINCT item_name FROM invoice_lines WHERE item_name IS NOT NULL")}
    nomes |= {r["name"] for r in todos(con, "SELECT name FROM qbo_items WHERE active=1")}
    for nome in nomes:
        palavras = [p for p in _norm(nome).split() if len(p) >= 3]
        if palavras and all(f" {p} " in t or f" {p}s " in t for p in palavras):
            achados.append(nome)
    # palavras soltas que o dono usa para peça ("chain", "tires", "fuel") pegam as variações
    for p in re.findall(r"[a-z]{4,}", t):
        if p in PECAS_COMUNS:
            achados.append(p)
    return sorted(set(achados))


PECAS_COMUNS = {"chain", "tire", "tires", "fuel", "sprocket", "bumper", "bolt", "rubber", "spark", "plug", "brake",
                "pads", "pad", "rod", "sticker", "engine", "axle", "seat", "steering", "column", "clutch", "carb",
                "carburetor", "exhaust", "radiator", "hub", "wheel", "rim", "bearing", "pinion", "nassau", "nose",
                "sidepod", "floor", "pedal", "cable", "battery", "oil", "gear", "mix"}
