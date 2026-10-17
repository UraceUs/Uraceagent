"""Estoque do site (#309): o que é dropshipping, o que o box tem para enviar e quanto tem.

Dono, 16/10: *"todos os produtos que estão na loja … sejam editáveis … quantidade em estoque também, e fazer ele no nosso
estoque, na seção do site, coloca o estoque do site, o que que a gente tem, aí a gente seleciona, não precisa ficar
aparente essa parte … para os clientes, mas a gente seleciona o que que é dropshipping e o que que a gente tem em estoque
para poder enviar. Um marcador para isso lá, e o que tiver em estoque a gente coloca quanto que tem em estoque."*

Decisões (valem sobre o resto):
- **Um saldo só.** O produto da loja em estoque (ou cada opção: o tamanho da camisa) liga a UM item do estoque interno
  (`store_product_stock`). Balcão, contagem, Compras (receber dá entrada) e o site mexem no mesmo número, e
  `estoque.conferir()` continua batendo. Dois números para a mesma peça física é o que `estoque.py` proíbe.
- **O marcador** (`store_products.fulfillment`) é `dropshipping` (o padrão: no dia do deploy nada muda no site) ou
  `estoque`. O cliente nunca vê o marcador nem a quantidade: só o "Out of stock" derivado (`loja.no_site`).
- **Ligar pede a contagem** ("quanto tem no Galpão agora"): o estoque interno nasceu sem contagem, e ligar sem contar
  mostraria "Out of stock" no site. A contagem é **de um local só**; a tela mostra cada local ("Galpão X · Pista Y") e
  o campo vem com o saldo daquele local. O item que **já tem saldo ou contagem** liga sem contar (a contagem fica
  opcional): pedir o número de novo fazia a pessoa digitar o total do Galpão + Pista num local só e inflar o saldo.
  Item com número de série (kart usado, motor) conta as unidades, uma a uma, pelo Estoque.
- **Locais que contam para o site:** Galpão + Pista. O trailer de corrida fica fora. Peça de cliente nunca conta.
- **A venda paga baixa o estoque** dentro da transação do pagamento (webhook e página de obrigado), uma vez só (o
  movimento fica gravado no pedido). Sem saldo, o pagamento **não cai**: a linha vira "Resolver: sem estoque" em Pedidos
  do site, até alguém tocar em **Resolvido** (`stock_resolved_at`, com auditoria). Nada vira pedido automático em
  Compras. A baixa tira o que cada local tem, fração inclusive: o site vende a soma do Galpão + Pista, e a soma baixada
  bate com o vendido.
"""
import logging
import math
import re
import unicodedata

from command_center.db import agora, atualizar, inserir, todos, um
from command_center.providers import estoque, loja, prateleiras
from command_center.providers.loja import ErroProduto

MODOS = ("todos", "estoque", "dropshipping", "sem_item", "sem_saldo")
KINDS_NOVOS = ("peca", "pneu")       # criar item a partir do produto: o que se conta por quantidade
PROBLEMA = "sem estoque"             # o começo da nota que pede a equipe ("Resolver:" em Pedidos do site)
log = logging.getLogger("urace.loja")


def _locais(con):
    """Os locais que contam para o site, com o nome que a equipe vê no Estoque."""
    return [{"code": loc["code"], "name": loc["name"]} for loc in (estoque.local(con, c) for c in loja.LOCAIS_DO_SITE)]


# ------------------------------------------------------------------ a lista (Site › Estoque do site)
def _linha(p, ls):
    """Um produto na lista: o marcador, cada opção com o item ligado e o que tem, e o que o site mostra."""
    site = loja.no_site(p, ls)
    nomes = [" / ".join(v["attrs"]) for v in p["variations"]]
    ops = []
    for i, nome in enumerate(nomes or [""]):
        ligado = ls.get(nome)
        ops.append({"variation": nome,
                    "ligado": loja._ligacao(ligado) if ligado else None,
                    "manual": bool(p["variations"][i].get("in_stock", True) if nomes else p["in_stock"]),
                    "no_site": bool(site["variations"][i].get("in_stock", True) if nomes else site["in_stock"])})
    orfas = [loja._ligacao(l) for k, l in ls.items() if k not in (nomes or [""])]
    ligadas = [o for o in ops if o["ligado"]]
    return {"id": p["id"], "slug": p["slug"], "name": p["name"], "active": p["active"], "fulfillment": p["fulfillment"],
            "foto": p["images"][0]["src"] if p["images"] else None, "price": p["price"], "price_min": p["price_min"],
            "price_max": p["price_max"], "no_site": bool(site["in_stock"]), "opcoes": ops, "orfas": orfas,
            "tem": round(sum(o["ligado"]["tem"] for o in ligadas), 4) if ligadas else None,
            "faltam_ligar": sum(1 for o in ops if not o["ligado"]),
            "sem_saldo": sum(1 for o in ligadas if o["ligado"]["tem"] < 1),
            "prateleira": prateleiras.sugerir("peca", p["name"])}       # a sugestão para o item novo (a pessoa troca)


def _no_modo(x, modo):
    em = x["fulfillment"] == "estoque"
    return {"todos": True, "estoque": em, "dropshipping": not em, "sem_item": em and x["faltam_ligar"] > 0,
            "sem_saldo": em and x["sem_saldo"] > 0}[modo]


def lista(con, termo="", modo="todos", limit=20, offset=0):
    """Os produtos da loja com o estoque deles, paginados no servidor. Os filtros: em estoque, dropshipping, em estoque
    sem item ligado (falta ligar) e sem saldo (ligado, mas acabou: o site já mostra "Out of stock")."""
    if modo not in MODOS:
        raise ErroProduto("filtro inválido")
    onde, args = [], []
    t = re.sub(r"\s+", " ", (termo or "").strip())[:80]
    if t:
        onde.append("(LOWER(name) LIKE ? OR LOWER(COALESCE(sku,'')) LIKE ? OR slug LIKE ?)")
        args += [f"%{t.lower()}%"] * 3
    w = (" WHERE " + " AND ".join(onde)) if onde else ""
    rs = todos(con, f"SELECT * FROM store_products{w} ORDER BY active DESC, sort, id", tuple(args))
    ls = loja.ligados(con, [r["id"] for r in rs]) if rs else {}
    linhas = [_linha(loja._produto(r), ls.get(r["id"], {})) for r in rs]
    contagem = {m: sum(1 for x in linhas if _no_modo(x, m)) for m in MODOS}
    escolhidos = [x for x in linhas if _no_modo(x, modo)]
    limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
    return {"produtos": escolhidos[offset:offset + limit], "total": len(escolhidos), "limit": limit, "offset": offset,
            "contagem": contagem, "locais": _locais(con),
            "prateleiras": [{"code": x["code"], "nome": x["nome"]} for x in prateleiras.PRATELEIRAS if x["kind"] in KINDS_NOVOS]}


# ------------------------------------------------------------------ os itens do estoque para ligar
def _palavras(s):
    t = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return [w for w in re.split(r"[^a-z0-9]+", t) if len(w) >= 3]


def itens(con, termo="", pid=None, limit=20, offset=0):
    """O estoque interno para ligar ao produto: a busca pelo nome; sem busca, o que se parece com o nome do produto
    (a sugestão). Cada item com quanto a URACE tem para o site e, se já vende no site, por qual produto."""
    ativos = todos(con, """SELECT i.id, i.name, i.kind, i.tracking, i.unit, i.size, i.category, i.price, i.sku,
                                  s.product_id AS ligado_pid, s.variation AS ligado_var, p.name AS ligado_nome,
                                  p.fulfillment AS ligado_fulfillment
                             FROM stock_items i LEFT JOIN store_product_stock s ON s.item_id=i.id
                             LEFT JOIN store_products p ON p.id=s.product_id
                            WHERE i.active=1 ORDER BY i.name""")
    t = (termo or "").strip()[:80]
    if t:
        alvo = _palavras(t) or [t.lower()]
        achados = [i for i in ativos if all(w in " ".join(_palavras(f"{i['name']} {i['sku'] or ''} {i['size'] or ''}"))
                                            for w in alvo)]
        sugestao = False
    else:
        prod = um(con, "SELECT name FROM store_products WHERE id=?", (pid,)) if pid else None
        alvo = set(_palavras(prod["name"])) if prod else set()
        nota = [(len(alvo & set(_palavras(i["name"]))), i) for i in ativos]
        achados = [i for n, i in sorted(nota, key=lambda x: -x[0]) if n > 0] if alvo else []
        sugestao = bool(achados)
        if not achados:
            achados = ativos
    total = len(achados)
    limit, offset = max(1, min(int(limit), 50)), max(0, int(offset))
    pagina = achados[offset:offset + limit]
    pl = loja.por_local(con, [i["id"] for i in pagina])
    contados = _contados(con, [i["id"] for i in pagina])
    return {"itens": [{**i, "tem": round(sum(pl[i["id"]].values()), 4), "por_local": pl[i["id"]],
                       "contado": i["id"] in contados} for i in pagina],
            "total": total, "limit": limit, "offset": offset, "sugestao": sugestao}


def _contados(con, ids):
    """Os itens que já têm saldo da URACE (em qualquer local) ou alguma contagem: ligar a eles não pede contar de novo."""
    if not ids:
        return set()
    m = ",".join("?" * len(ids))
    return {r["item_id"] for r in todos(con, f"""
        SELECT item_id FROM stock_levels WHERE item_id IN ({m}) AND client_id IS NULL AND qty<>0
        UNION SELECT item_id FROM stock_moves WHERE item_id IN ({m}) AND kind='contagem' AND client_id IS NULL
        UNION SELECT item_id FROM stock_units WHERE item_id IN ({m}) AND client_id IS NULL""", (*ids, *ids, *ids))}


# ------------------------------------------------------------------ ligar, desligar, contar
def _produto(con, pid):
    p = loja.do_painel(con, pid)
    if not p:
        raise ErroProduto("produto não existe")
    return p


def _opcao(p, variacao):
    v = (variacao or "").strip()
    nomes = loja.opcoes(p)
    if nomes == [""]:
        if v:
            raise ErroProduto("este produto não tem opções: ligue o produto inteiro")
        return ""
    if v not in nomes:
        raise ErroProduto("escolha a opção do produto (tamanho, cor…) que este item é")
    return v


def _vazio(v):
    return v is None or (isinstance(v, str) and not v.strip())


def _qtd(v):
    if _vazio(v):
        raise ErroProduto("informe quanto tem agora (a contagem): é o que o site passa a vender")
    if isinstance(v, bool):
        raise ErroProduto("a contagem precisa ser um número, como 3")
    try:
        q = float(str(v).replace(",", "."))
    except ValueError:
        raise ErroProduto("a contagem precisa ser um número, como 3")
    if not math.isfinite(q) or not 0 <= q <= 100_000:          # "nan" passava pelas duas comparações (revisão)
        raise ErroProduto("a contagem vai de 0 a 100.000")
    return q


def _local(code):
    code = code or loja.LOCAIS_DO_SITE[0]
    if code not in loja.LOCAIS_DO_SITE:
        raise ErroProduto("conte no Galpão ou na Pista: o trailer de corrida não vende pelo site")
    return code


def ligar(con, por, pid, variacao="", item_id=None, criar=None, contagem=None, local=None):
    """Liga o produto (ou a opção) a um item do estoque e conta o que tem agora **naquele local**. Liga = "em estoque": o
    produto passa a vender pelo saldo. `criar` ({name, kind, category, size, price}) cria o item a partir do produto.
    O item que já tem saldo ou contagem liga sem `contagem` (nada muda no número). Devolve o que mudou (vai para a
    auditoria). Quem chama abre a transação."""
    p = _produto(con, pid)
    var = _opcao(p, variacao)
    nome = p["name"] + (f" · {var}" if var else "")
    if um(con, "SELECT 1 AS x FROM store_product_stock WHERE product_id=? AND variation=?", (pid, var)):
        raise ErroProduto(f"{nome} já está ligado a um item: desligue antes de trocar")
    criado = False
    try:
        if item_id:
            it = estoque.item(con, int(item_id))
            if not it["active"]:
                raise ErroProduto(f"{it['name']} foi excluído do estoque")
            ja = um(con, """SELECT p.name, p.fulfillment, s.variation FROM store_product_stock s
                             JOIN store_products p ON p.id=s.product_id WHERE s.item_id=?""", (it["id"],))
            if ja:
                onde = ja["name"] + (f" ({ja['variation']})" if ja["variation"] else "")
                if ja["fulfillment"] != "estoque":       # o produto passou a dropshipping e a ligação ficou
                    raise ErroProduto(f"{it['name']} ainda está ligado a {onde} (dropshipping): desligue lá em Estoque do "
                                      "site antes de ligar a este produto")
                raise ErroProduto(f"{it['name']} já vende no site como {onde}: um item, um produto")
            if it["tracking"] != "quantidade":
                conta = None
            elif _vazio(contagem) and it["id"] in _contados(con, [it["id"]]):
                conta = None    # já tem saldo ou contagem: liga sem mexer no número (contar é outro passo, por local)
            else:
                conta = (_qtd(contagem), _local(local))
        elif criar:
            kind = (criar.get("kind") or ("pneu" if criar.get("category") == "pneus" else "peca")).strip()
            if kind not in KINDS_NOVOS:
                raise ErroProduto("o item novo é peça ou pneu (kart e motor, com número de série, entram pelo Estoque)")
            conta = (_qtd(contagem), _local(local))             # antes de criar: recusado não deixa item pela metade
            nome_item = re.sub(r"\s+", " ", str(criar.get("name") or "").strip())[:120] or nome.replace(" · ", " ")
            preco = criar.get("price")
            it = estoque.item(con, estoque.criar_item(
                con, kind, nome_item, category=criar.get("category") or None, size=(criar.get("size") or var or None),
                price=None if preco in (None, "") else preco, notes=f"criado a partir do produto da loja: {p['name']}"))
            criado = True
        else:
            raise ErroProduto("escolha o item do estoque, ou crie um a partir do produto")
        contou = None
        if conta:              # série (kart usado, motor): as unidades, cada uma com o número dela, são a contagem
            contou = estoque.contar(con, it["id"], conta[0], onde=conta[1], client_id=None, by_user_id=por,
                                    source="site", notes=f"ao ligar à loja do site: {nome}")
    except estoque.ErroEstoque as e:
        raise ErroProduto(str(e))
    inserir(con, "store_product_stock", product_id=pid, variation=var, item_id=it["id"], created_by=por)
    if p["fulfillment"] != "estoque":
        atualizar(con, "store_products", pid, fulfillment="estoque", updated_by=por, updated_at=agora())
    return {"produto": p["slug"], "opcao": var or None, "item_id": it["id"], "item": it["name"], "item_criado": criado,
            "contagem": contou and {"local": conta[1], **contou}, "fulfillment": "estoque"}


def desligar(con, por, pid, variacao=""):
    """Tira a ligação (o item continua no estoque com o saldo e o histórico; a venda deixa de baixar dele)."""
    p = _produto(con, pid)
    var = (variacao or "").strip()
    l = um(con, """SELECT s.id, s.item_id, i.name FROM store_product_stock s JOIN stock_items i ON i.id=s.item_id
                    WHERE s.product_id=? AND s.variation=?""", (pid, var))
    if not l:
        raise ErroProduto("esta opção não está ligada a nenhum item")
    con.execute("DELETE FROM store_product_stock WHERE id=?", (l["id"],))
    return {"produto": p["slug"], "opcao": var or None, "item_id": l["item_id"], "item": l["name"]}


def contar(con, por, pid, variacao, qty, local=None, nota=None):
    """A contagem do item ligado (a mesma de Estoque › Quantidade): o que a mão contou vira o saldo daquele local."""
    p = _produto(con, pid)
    var = (variacao or "").strip()
    l = p["estoque"]["ligados"].get(var)
    if not l:
        raise ErroProduto("ligue a opção a um item do estoque antes de contar")
    if l["tracking"] == "serie":
        raise ErroProduto(f"{l['item']} tem número de série: confira as unidades uma a uma em Estoque")
    try:
        r = estoque.contar(con, l["item_id"], _qtd(qty), onde=_local(local), client_id=None, by_user_id=por, source="site",
                           notes=(re.sub(r"\s+", " ", nota.strip())[:300] if nota and nota.strip() else None)
                           or f"Estoque do site: {p['name']}" + (f" · {var}" if var else ""))
    except estoque.ErroEstoque as e:
        raise ErroProduto(str(e))
    return {"produto": p["slug"], "opcao": var or None, "item_id": l["item_id"], "local": _local(local), **r}


# ------------------------------------------------------------------ a venda paga baixa o estoque
def _ultimo_movimento(con, item_id):
    return um(con, "SELECT MAX(id) AS id FROM stock_moves WHERE item_id=?", (item_id,))["id"]


def _baixar_linha(con, oid, x, ordem):
    """(nota, movimento) de uma linha paga. (None, None): dropshipping ou produto que não existe mais (nada a baixar)."""
    p = um(con, "SELECT id, name, fulfillment FROM store_products WHERE slug=?", (x["product_slug"],))
    if not p or p["fulfillment"] != "estoque":
        return None, None
    var = x["variation"] or ""
    nome = p["name"] + (f" ({var})" if var else "")
    qtd = max(1, int(x["quantity"] or 1))
    l = um(con, """SELECT s.item_id, i.tracking FROM store_product_stock s JOIN stock_items i ON i.id=s.item_id
                    WHERE s.product_id=? AND s.variation=?""", (p["id"], var))
    if not l:
        return f"{PROBLEMA} ligado: {nome} × {qtd} — baixe à mão no Estoque", None
    nota_mov = f"loja do site · pedido #{oid}"
    primeiro, baixou, onde, seriais = None, 0, [], []
    con.execute("SAVEPOINT baixa_site")
    try:
        for code in ordem:
            if baixou >= qtd - 1e-9:
                break
            loc = estoque.local(con, code)
            n = 0
            if l["tracking"] == "serie":
                for u in todos(con, """SELECT id, serial FROM stock_units WHERE item_id=? AND client_id IS NULL
                                         AND status='disponivel' AND location_id=? ORDER BY id LIMIT ?""",
                               (l["item_id"], loc["id"], qtd - baixou)):
                    estoque.saida(con, l["item_id"], unit_id=u["id"], de=loc, reason="venda", source="site", notes=nota_mov)
                    primeiro = primeiro or _ultimo_movimento(con, l["item_id"])
                    seriais.append(u["serial"])      # a equipe separa ESTA unidade (garantia e procedência do kart usado)
                    n += 1
            else:
                # o que o local tem, fração inclusive (sem `int`): o site vende a SOMA do Galpão + Pista arredondada
                # para baixo, e 0,5 + 0,5 vende 1; arredondar por local baixava 0 (revisão do #309)
                n = min(estoque.saldo(con, l["item_id"], loc["id"], client_id=None), qtd - baixou)
                if n > 1e-9:
                    estoque.saida(con, l["item_id"], qty=n, de=loc, client_id=None, reason="venda", source="site", notes=nota_mov)
                    primeiro = primeiro or _ultimo_movimento(con, l["item_id"])
                else:
                    n = 0
            if n:
                baixou += n
                onde.append(f"{loc['name']} {n:g}")
        con.execute("RELEASE baixa_site")
    except Exception as e:                                  # noqa: BLE001 — o pagamento nunca cai pela baixa
        con.execute("ROLLBACK TO baixa_site")
        con.execute("RELEASE baixa_site")
        log.warning("baixa do estoque do pedido %s falhou: %s", oid, str(e)[:200])
        return f"{PROBLEMA}: {nome} × {qtd} — não baixou ({str(e)[:120]}); baixe à mão no Estoque", None
    serie = f"; série: {', '.join(seriais)}" if seriais else ""
    if baixou < qtd - 1e-9:
        return (f"{PROBLEMA}: {nome} — pediu {qtd}, tinha {baixou:g}"
                + (f" (baixou {baixou:g}; falta {qtd - baixou:g}{serie})" if baixou else "")), primeiro
    return f"baixou {qtd} do estoque ({', '.join(onde)}{serie})", primeiro


def baixar_do_pedido(con, oid):
    """A venda paga sai do estoque (o produto em estoque com item ligado): `reason=venda, source=site`. Corre dentro da
    transação do pagamento e uma vez só por linha (o movimento, ou a nota, fica no pedido). Envio sai primeiro do Galpão;
    retirada, primeiro da Pista. Sem saldo, baixa o que tem e devolve a frase para "Resolver" — nunca derruba o pagamento.
    Devolve as frases que pedem a equipe (vazio: nada a resolver)."""
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if not o:
        return []
    if o.get("kind") == "carrinho":
        linhas = [("store_order_items", x) for x in todos(
            con, "SELECT * FROM store_order_items WHERE order_id=? AND kind='produto' ORDER BY id", (oid,))]
    else:
        linhas = [("store_orders", o)]
    ordem = loja.LOCAIS_DO_SITE if o["delivery"] == "envio" else tuple(reversed(loja.LOCAIS_DO_SITE))
    resolver = []
    for tabela, x in linhas:
        if x.get("stock_move_id") or x.get("stock_note"):
            if _aberto(x):
                resolver.append(x["stock_note"])
            continue
        nota, mov = _baixar_linha(con, oid, x, ordem)
        if nota is None:
            continue
        nota = nota[:300]                  # a mesma frase no pedido e no "Resolver" (o Resolvido a tira de lá)
        atualizar(con, tabela, x["id"], stock_move_id=mov, stock_note=nota)
        if nota.startswith(PROBLEMA):
            resolver.append(nota)
    return resolver


# ------------------------------------------------------------------ "Resolvido" (revisão do #309)
def _aberto(x):
    """A linha (ou o pedido do Buy now) pago sem estoque que ninguém marcou como resolvido."""
    return (x.get("stock_note") or "").startswith(PROBLEMA) and not x.get("stock_resolved_at")


def baixas(con, o):
    """O que a venda paga tirou do estoque, linha a linha, para a equipe separar (e, no item de série, QUAL unidade):
    [(nome da linha, frase)]. O que está "sem estoque" fica no "Resolver"."""
    if o.get("stock_note") and not o["stock_note"].startswith(PROBLEMA):
        return [(o.get("product_name") or "", o["stock_note"])]
    return [(x["name"], x["stock_note"]) for x in todos(
        con, "SELECT name, stock_note FROM store_order_items WHERE order_id=? AND kind='produto' AND stock_note IS NOT NULL "
             "ORDER BY id", (o["id"],)) if not x["stock_note"].startswith(PROBLEMA)]


def pendentes(con, o):
    """As frases de "sem estoque" ainda abertas de um pedido (vazio: nada a resolver)."""
    out = [o["stock_note"]] if _aberto(o) else []
    out += [x["stock_note"] for x in todos(con, "SELECT stock_note, stock_resolved_at FROM store_order_items "
                                                "WHERE order_id=? AND kind='produto' ORDER BY id", (o["id"],)) if _aberto(x)]
    return out


def resolver(con, oid, por=None):
    """A equipe resolveu o pedido pago sem estoque (separou o que tinha, combinou com o cliente, devolveu pelo Stripe):
    marca `stock_resolved_at` no pedido e nas linhas, e o "sem estoque" sai do "Resolver" do pedido e da contagem do
    Painel do site. Nada se apaga: a frase continua na linha (`stock_note`) e no histórico. Quem chama abre a transação
    e audita."""
    o = um(con, "SELECT * FROM store_orders WHERE id=?", (oid,))
    if not o:
        raise ErroProduto("pedido não existe")
    abertas = pendentes(con, o)
    if not abertas:
        raise ErroProduto("este pedido não tem nada sem estoque para resolver")
    quando = agora()
    if _aberto(o):
        atualizar(con, "store_orders", oid, stock_resolved_at=quando, stock_resolved_by=por)
    con.execute("""UPDATE store_order_items SET stock_resolved_at=?, stock_resolved_by=? WHERE order_id=? AND kind='produto'
                    AND stock_note LIKE ? AND stock_resolved_at IS NULL""", (quando, por, oid, PROBLEMA + "%"))
    from command_center.providers import carrinho
    atencao = carrinho.atencao(con, um(con, "SELECT * FROM store_orders WHERE id=?", (oid,)))
    atualizar(con, "store_orders", oid, attention=atencao, updated_at=quando)
    return {"pedido": oid, "resolvidas": len(abertas), "notas": abertas, "atencao": atencao}
