"""ESTOQUE — o que existe, onde está e de quem é.

Três decisões do dono mandam no modelo inteiro (22/09):

1. **Dois tipos.** *"Chassi e motor: ficha individual com número de série. Pneu e peça
   de consumo: quantidade."* São dois comportamentos, e por isso dois lugares onde o
   saldo mora: `stock_units` (uma linha = uma coisa que existe) e `stock_levels` (um
   número por item × local × dono). Misturar num modelo só é o erro clássico que trava
   o sistema depois — quem tenta guardar chassi como "quantidade 3" perde de vista qual
   dos três está no trailer.
2. **Dois locais:** sede e trailer de corrida. Transferir é um MOVIMENTO, nunca uma
   edição de número.
3. **A base das peças é o catálogo da Comet Kart Sales**, e o SKU é **referência de
   compra**: é o que o módulo de compras (futuro) vai usar para pedir. Não é a identidade
   do item — peça avulsa e usado existem sem SKU. Quem prepara essa ponte é
   `abaixo_do_minimo()`, que devolve SKU e link do fornecedor junto do quanto falta.

E uma decisão de arquitetura, que é minha e está escrita para poder ser contestada: **o
painel manda no estoque físico, o QuickBooks manda no financeiro.** Controlar quantidade
dos dois lados garante divergência, e divergência garante que ninguém acredite em nenhum
dos dois números.

**O razão é a verdade.** Todo movimento vira linha em `stock_moves`, com saldo antes e
depois. `stock_levels` é o saldo corrente, mantido na mesma transação — é cache rápido,
não fonte. `conferir()` refaz tudo a partir dos movimentos e acusa qualquer diferença.
É isso que impede o número de virar opinião.

**A trava que não se negocia:** peça que está com a URACE mas é do cliente (`client_id`
preenchido) nunca sai para outro cliente. É a mesma regra dos cards — *"nunca colocar
serviço de outro cliente em card de outro cliente"* — aplicada ao que é físico.
"""
from command_center.db import agora, inserir, todos, um

SEDE, TRAILER = "sede", "trailer"

# kind → como o saldo é contado. Explícito porque um dia haverá peça cara com série.
TRACKING = {"chassi": "serie", "motor": "serie", "pneu": "quantidade", "peca": "quantidade"}
KINDS = tuple(TRACKING)
MOVIMENTOS = ("entrada", "saida", "ajuste", "transferencia", "contagem")
# Status de unidade que ainda conta como "está com a gente".
EM_CASA = ("disponivel", "em_uso", "em_servico", "emprestado")


class ErroEstoque(ValueError):
    """Regra de estoque violada. A mensagem é para ser lida por gente, no painel."""


class _Todos:
    """Sentinela para "de qualquer dono".

    Existe porque `client_id=None` já quer dizer uma coisa precisa — **o que é da
    URACE** — e usar o mesmo None para "não filtre" foi um defeito de verdade, pego no
    teste: `saldo(item)` devolvia o total da casa, peça de cliente inclusive. O PDV
    perguntaria "quanto posso vender?" e receberia o que não é nosso.
    """

    def __repr__(self):
        return "estoque.TODOS"


TODOS = _Todos()


# --------------------------------------------------------------------- leitura
def local(con, ref):
    """Aceita id, código ('sede') ou a própria linha. Erra claro quando não existe."""
    if isinstance(ref, dict) or hasattr(ref, "keys"):
        return ref
    if isinstance(ref, int):
        r = um(con, "SELECT * FROM stock_locations WHERE id=?", (ref,))
    else:
        r = um(con, "SELECT * FROM stock_locations WHERE code=?", (str(ref),))
    if not r:
        raise ErroEstoque(f"local de estoque desconhecido: {ref!r}")
    return r


def item(con, item_id):
    r = um(con, "SELECT * FROM stock_items WHERE id=?", (item_id,))
    if not r:
        raise ErroEstoque(f"item de estoque {item_id} não existe")
    return r


def criar_item(con, kind, name, sku=None, supplier="comet", supplier_url=None,
               part_number=None, unit="un", min_qty=None, notes=None,
               chassis_id=None, engine_id=None, part_id=None, tracking=None):
    """Cria o QUE é. Não cria saldo: saldo só nasce de movimento."""
    if kind not in KINDS:
        raise ErroEstoque(f"tipo de item inválido: {kind!r} (use {', '.join(KINDS)})")
    tracking = tracking or TRACKING[kind]
    if not (name or "").strip():
        raise ErroEstoque("item de estoque precisa de nome")
    if sku:
        ja = um(con, "SELECT id, name FROM stock_items WHERE supplier=? AND sku=?", (supplier, sku))
        if ja:
            raise ErroEstoque(f"o SKU {sku} já é do item #{ja['id']} ({ja['name']})")
    if tracking == "serie" and min_qty:
        # Mínimo é contagem; em ficha individual ele não quer dizer nada.
        raise ErroEstoque("estoque mínimo não vale para item com número de série")
    return inserir(con, "stock_items", kind=kind, tracking=tracking, name=name.strip(),
                   sku=sku, supplier=supplier if sku else None, supplier_url=supplier_url,
                   part_number=part_number, unit=unit, min_qty=min_qty, notes=notes,
                   chassis_id=chassis_id, engine_id=engine_id, part_id=part_id)


# --------------------------------------------------------------------- saldo
def _linha_saldo(con, item_id, location_id, client_id):
    return um(con, "SELECT * FROM stock_levels WHERE item_id=? AND location_id=? "
                   "AND COALESCE(client_id,0)=COALESCE(?,0)", (item_id, location_id, client_id))


def saldo(con, item_id, location_id=None, client_id=TODOS):
    """Quanto tem. Em item de série conta unidades; em quantidade lê o saldo.

    `client_id` tem três sentidos, e a diferença entre eles é dinheiro dos outros:
      - `TODOS` (padrão): tudo que está fisicamente com a gente, de quem quer que seja;
      - `None`: o que é **da URACE** — é este que o PDV tem de perguntar;
      - um id: o que é daquele cliente.
    """
    it = item(con, item_id)
    if it["tracking"] == "serie":
        marcas = ",".join("?" * len(EM_CASA))
        sql = f"SELECT COUNT(*) n FROM stock_units WHERE item_id=? AND status IN ({marcas})"
        p = [item_id, *EM_CASA]
        if location_id is not None:
            sql += " AND location_id=?"
            p.append(location_id)
        if client_id is not TODOS:
            sql += " AND client_id IS ?" if client_id is None else " AND client_id=?"
            p.append(client_id)
        return float(um(con, sql, tuple(p))["n"])
    sql = "SELECT COALESCE(SUM(qty),0) q FROM stock_levels WHERE item_id=?"
    p = [item_id]
    if location_id is not None:
        sql += " AND location_id=?"
        p.append(location_id)
    if client_id is not TODOS:
        sql += " AND COALESCE(client_id,0)=COALESCE(?,0)"
        p.append(client_id)
    return float(um(con, sql, tuple(p))["q"])


def vendavel(con, item_id, location_id=None):
    """O que dá para vender: só o que é nosso. É o atalho que o PDV deve usar, para que
    a pergunta certa seja a mais fácil de fazer."""
    return saldo(con, item_id, location_id, client_id=None)


def _mexer_saldo(con, item_id, location_id, client_id, delta):
    """Move o saldo de quantidade e devolve (antes, depois). Não deixa ficar negativo:
    saldo negativo é sempre erro de lançamento, e engolir isso é perder a contagem."""
    linha = _linha_saldo(con, item_id, location_id, client_id)
    antes = float(linha["qty"]) if linha else 0.0
    depois = antes + delta
    if depois < 0:
        it = item(con, item_id)
        raise ErroEstoque(f"não dá para tirar {abs(delta):g} {it['unit']} de "
                          f"{it['name']}: tem {antes:g}")
    if linha:
        con.execute("UPDATE stock_levels SET qty=?, updated_at=? WHERE id=?",
                    (depois, agora(), linha["id"]))
    else:
        inserir(con, "stock_levels", item_id=item_id, location_id=location_id,
                client_id=client_id, qty=depois)
    return antes, depois


def _registrar(con, kind, it, **campos):
    campos.setdefault("qty", 0)
    return inserir(con, "stock_moves", kind=kind, item_id=it["id"], **campos)


# --------------------------------------------------------------------- movimentos
def entrada(con, item_id, qty=None, serial=None, para=SEDE, client_id=None,
            reason=None, by_user_id=None, source="painel", notes=None, acquired_at=None):
    """Chegou. Em item de série, `serial` é obrigatório e nasce uma ficha."""
    it, loc = item(con, item_id), local(con, para)
    if it["tracking"] == "serie":
        if not (serial or "").strip():
            raise ErroEstoque(f"{it['name']} é controlado por número de série: informe o serial")
        serial = serial.strip()
        ja = um(con, "SELECT id FROM stock_units WHERE item_id=? AND serial=?", (it["id"], serial))
        if ja:
            raise ErroEstoque(f"o serial {serial} já está cadastrado (unidade #{ja['id']})")
        uid = inserir(con, "stock_units", item_id=it["id"], serial=serial, location_id=loc["id"],
                      client_id=client_id, status="disponivel", acquired_at=acquired_at, notes=notes)
        _registrar(con, "entrada", it, unit_id=uid, qty=1, to_location_id=loc["id"],
                   client_id=client_id, reason=reason or "compra", by_user_id=by_user_id,
                   source=source, notes=notes, qty_before=0, qty_after=1)
        return {"unit_id": uid, "serial": serial}
    qty = _quantidade(qty, it)
    antes, depois = _mexer_saldo(con, it["id"], loc["id"], client_id, qty)
    _registrar(con, "entrada", it, qty=qty, to_location_id=loc["id"], client_id=client_id,
               reason=reason or "compra", by_user_id=by_user_id, source=source, notes=notes,
               qty_before=antes, qty_after=depois)
    return {"qty": depois}


def _quantidade(qty, it):
    if qty is None:
        raise ErroEstoque(f"{it['name']} é controlado por quantidade: informe quanto")
    qty = float(qty)
    if qty <= 0:
        raise ErroEstoque("quantidade tem de ser maior que zero "
                          "(para tirar do estoque use a saída, não um número negativo)")
    return qty


def saida(con, item_id, qty=None, unit_id=None, de=SEDE, client_id=None, para_cliente_id=None,
          reason="uso em serviço", by_user_id=None, source="painel", notes=None,
          task_id=None, invoice_id=None):
    """Saiu: venda, uso em serviço, envio, perda.

    `client_id` diz de quem é a peça que está saindo (NULL = da URACE).
    `para_cliente_id` diz para quem ela vai. É no encontro desses dois que mora a trava:
    **peça de um cliente nunca sai para outro.**
    """
    it, loc = item(con, item_id), local(con, de)
    if it["tracking"] == "serie":
        u = _unidade(con, unit_id, it)
        _travar_peca_de_cliente(con, u["client_id"], para_cliente_id, it, reason)
        novo = "vendido" if reason == "venda" else "baixado"
        con.execute("UPDATE stock_units SET status=?, updated_at=? WHERE id=?", (novo, agora(), u["id"]))
        _registrar(con, "saida", it, unit_id=u["id"], qty=1, from_location_id=u["location_id"],
                   client_id=u["client_id"], reason=reason, by_user_id=by_user_id, source=source,
                   notes=notes, task_id=task_id, invoice_id=invoice_id, qty_before=1, qty_after=0)
        return {"unit_id": u["id"], "status": novo}
    _travar_peca_de_cliente(con, client_id, para_cliente_id, it, reason)
    qty = _quantidade(qty, it)
    antes, depois = _mexer_saldo(con, it["id"], loc["id"], client_id, -qty)
    _registrar(con, "saida", it, qty=qty, from_location_id=loc["id"], client_id=client_id,
               reason=reason, by_user_id=by_user_id, source=source, notes=notes,
               task_id=task_id, invoice_id=invoice_id, qty_before=antes, qty_after=depois)
    return {"qty": depois}


def _unidade(con, unit_id, it):
    if not unit_id:
        raise ErroEstoque(f"{it['name']} é controlado por número de série: diga qual unidade")
    u = um(con, "SELECT * FROM stock_units WHERE id=? AND item_id=?", (unit_id, it["id"]))
    if not u:
        raise ErroEstoque(f"unidade #{unit_id} não é de {it['name']}")
    if u["status"] not in EM_CASA:
        raise ErroEstoque(f"a unidade {u['serial']} já saiu do estoque (está como {u['status']})")
    return u


def _travar_peca_de_cliente(con, dono_id, para_cliente_id, it, reason):
    """A regra dos cards, aplicada ao que é físico: o que é de um cliente não vai para
    outro. Devolver para o próprio dono pode; vender o que não é nosso, não."""
    if not dono_id:
        return
    dono = um(con, "SELECT name, pilot_name FROM clients WHERE id=?", (dono_id,))
    nome = (dono["pilot_name"] or dono["name"]) if dono else f"cliente #{dono_id}"
    if para_cliente_id and int(para_cliente_id) != int(dono_id):
        raise ErroEstoque(f"{it['name']} é do {nome} e não pode sair para outro cliente. "
                          f"Se ele vendeu a peça, registre a troca de dono primeiro.")
    if reason == "venda" and not para_cliente_id:
        raise ErroEstoque(f"{it['name']} é do {nome}: não é nosso para vender.")


def transferir(con, item_id, qty=None, unit_id=None, de=SEDE, para=TRAILER, client_id=None,
               by_user_id=None, source="painel", notes=None):
    """Sede ↔ trailer. Não cria nem consome nada: o total da casa não muda."""
    it, o, d = item(con, item_id), local(con, de), local(con, para)
    if o["id"] == d["id"]:
        raise ErroEstoque("origem e destino são o mesmo local")
    if it["tracking"] == "serie":
        u = _unidade(con, unit_id, it)
        con.execute("UPDATE stock_units SET location_id=?, updated_at=? WHERE id=?",
                    (d["id"], agora(), u["id"]))
        _registrar(con, "transferencia", it, unit_id=u["id"], qty=1, from_location_id=o["id"],
                   to_location_id=d["id"], client_id=u["client_id"], by_user_id=by_user_id,
                   source=source, notes=notes)
        return {"unit_id": u["id"], "local": d["code"]}
    qty = _quantidade(qty, it)
    antes, _ = _mexer_saldo(con, it["id"], o["id"], client_id, -qty)
    _, depois = _mexer_saldo(con, it["id"], d["id"], client_id, qty)
    _registrar(con, "transferencia", it, qty=qty, from_location_id=o["id"], to_location_id=d["id"],
               client_id=client_id, by_user_id=by_user_id, source=source, notes=notes,
               qty_before=antes, qty_after=depois)
    return {"de": o["code"], "para": d["code"], "qty": qty}


def contar(con, item_id, qty, onde=SEDE, client_id=None, by_user_id=None,
           source="painel", notes=None):
    """Contagem física: o que a mão contou vira o saldo, e a diferença fica registrada.

    Não é "corrigir o número": é dizer que o número estava errado e guardar de quanto
    era o erro. Sem isso não há como saber se o estoque está sendo furtado, perdido ou
    só mal lançado.
    """
    it, loc = item(con, item_id), local(con, onde)
    if it["tracking"] == "serie":
        raise ErroEstoque(f"{it['name']} tem ficha individual: a contagem é conferir as "
                          "unidades uma a uma, não digitar um total")
    qty = float(qty)
    if qty < 0:
        raise ErroEstoque("contagem não pode ser negativa")
    tinha = saldo(con, it["id"], loc["id"], client_id=client_id)   # dono explícito, nunca TODOS
    antes, depois = _mexer_saldo(con, it["id"], loc["id"], client_id, qty - tinha)
    _registrar(con, "contagem", it, qty=qty, to_location_id=loc["id"], client_id=client_id,
               by_user_id=by_user_id, source=source, notes=notes,
               reason="contagem física", qty_before=antes, qty_after=depois)
    return {"antes": antes, "depois": depois, "diferenca": round(depois - antes, 4)}


def ajustar(con, item_id, delta, onde=SEDE, client_id=None, reason=None, by_user_id=None,
            source="painel", notes=None):
    """Acerto pontual com motivo obrigatório — quebra, perda, erro de lançamento.

    Motivo é obrigatório de propósito: ajuste sem motivo é exatamente como um estoque
    deixa de bater sem ninguém perceber.
    """
    it, loc = item(con, item_id), local(con, onde)
    if not (reason or "").strip():
        raise ErroEstoque("ajuste precisa de motivo (quebra, perda, erro de lançamento…)")
    if it["tracking"] == "serie":
        raise ErroEstoque(f"{it['name']} tem ficha individual: use entrada, saída ou transferência")
    delta = float(delta)
    if delta == 0:
        raise ErroEstoque("ajuste de zero não é ajuste")
    antes, depois = _mexer_saldo(con, it["id"], loc["id"], client_id, delta)
    _registrar(con, "ajuste", it, qty=abs(delta), client_id=client_id,
               from_location_id=loc["id"] if delta < 0 else None,
               to_location_id=loc["id"] if delta > 0 else None,
               reason=reason.strip(), by_user_id=by_user_id, source=source, notes=notes,
               qty_before=antes, qty_after=depois)
    return {"antes": antes, "depois": depois}


# --------------------------------------------------------------------- conferência
def _saldo_pelo_razao(con):
    """Refaz o saldo de quantidade a partir dos movimentos, do zero.

    Contagem NÃO soma: ela redefine. Por isso o razão é lido em ordem, e uma contagem
    apaga o que veio antes dela naquela prateleira — é o mesmo que a mão fez.
    """
    conta = {}
    for m in todos(con, """SELECT m.*, i.tracking FROM stock_moves m
                            JOIN stock_items i ON i.id = m.item_id
                           WHERE i.tracking='quantidade' ORDER BY m.id"""):
        dono = m["client_id"] or 0
        if m["kind"] == "contagem":
            conta[(m["item_id"], m["to_location_id"], dono)] = float(m["qty"])
            continue
        if m["kind"] in ("entrada", "ajuste", "transferencia") and m["to_location_id"]:
            conta[(m["item_id"], m["to_location_id"], dono)] = \
                conta.get((m["item_id"], m["to_location_id"], dono), 0.0) + float(m["qty"])
        if m["kind"] in ("saida", "ajuste", "transferencia") and m["from_location_id"]:
            conta[(m["item_id"], m["from_location_id"], dono)] = \
                conta.get((m["item_id"], m["from_location_id"], dono), 0.0) - float(m["qty"])
    return conta


def conferir(con):
    """O saldo corrente bate com o razão? Devolve as divergências, sem consertar nada.

    Consertar em silêncio seria esconder o defeito que produziu a diferença. Quem
    conserta é gente, por contagem física — e a contagem também fica no razão.
    """
    esperado = _saldo_pelo_razao(con)
    achados = []
    vistos = set()
    for l in todos(con, "SELECT * FROM stock_levels"):
        chave = (l["item_id"], l["location_id"], l["client_id"] or 0)
        vistos.add(chave)
        e = round(esperado.get(chave, 0.0), 4)
        if round(float(l["qty"]), 4) != e:
            achados.append({"item_id": l["item_id"], "location_id": l["location_id"],
                            "client_id": l["client_id"], "saldo": float(l["qty"]), "razao": e})
    for chave, q in esperado.items():
        if chave not in vistos and round(q, 4) != 0:
            achados.append({"item_id": chave[0], "location_id": chave[1],
                            "client_id": chave[2] or None, "saldo": 0.0, "razao": round(q, 4)})
    return achados


def abaixo_do_minimo(con):
    """Item que vai faltar — a lista de reposição, e a ponte para o módulo de compras.

    Devolve SKU e link do fornecedor junto do quanto falta, porque é exatamente isso que
    o comprador precisa para pedir. Enquanto o módulo de compras não existe, esta lista
    já serve para avisar em "Precisa de atenção" antes de a peça acabar.

    Só conta o estoque da URACE: peça de cliente não é nossa para repor, e misturar as
    duas coisas faria o painel mandar comprar o que é dos outros.
    """
    linhas = todos(con, """SELECT i.id, i.name, i.unit, i.min_qty, i.sku, i.supplier, i.supplier_url,
                                  COALESCE((SELECT SUM(l.qty) FROM stock_levels l
                                             WHERE l.item_id=i.id AND l.client_id IS NULL), 0) AS tem
                             FROM stock_items i
                            WHERE i.active=1 AND i.tracking='quantidade'
                              AND i.min_qty IS NOT NULL AND i.min_qty > 0""")
    return [dict(l, falta=round(float(l["min_qty"]) - float(l["tem"]), 4))
            for l in linhas if float(l["tem"]) < float(l["min_qty"])]


def do_cliente(con, client_id):
    """O que é dele e está com a gente — para aparecer no card do cliente."""
    unidades = todos(con, """SELECT u.*, i.name, i.kind, lo.name AS local
                               FROM stock_units u JOIN stock_items i ON i.id=u.item_id
                               LEFT JOIN stock_locations lo ON lo.id=u.location_id
                              WHERE u.client_id=? AND u.status IN {}""".format(
        "(" + ",".join("?" * len(EM_CASA)) + ")"), (client_id, *EM_CASA))
    pecas = todos(con, """SELECT l.*, i.name, i.unit, lo.name AS local
                            FROM stock_levels l JOIN stock_items i ON i.id=l.item_id
                            JOIN stock_locations lo ON lo.id=l.location_id
                           WHERE l.client_id=? AND l.qty > 0""", (client_id,))
    return {"unidades": [dict(u) for u in unidades], "pecas": [dict(p) for p in pecas]}
