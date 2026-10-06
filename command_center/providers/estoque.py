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
               chassis_id=None, engine_id=None, part_id=None, tracking=None,
               category=None, subcategory=None, size=None, cost=None, markup=None, price=None):
    """Cria o QUE é. Não cria saldo: saldo só nasce de movimento."""
    extras = _campos_de_vitrine(category=category, subcategory=subcategory, size=size,
                                cost=cost, markup=markup, price=price)
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
                   chassis_id=chassis_id, engine_id=engine_id, part_id=part_id, **extras)


def _texto(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return v or None


def _dinheiro(v, rotulo):
    if v is None or v == "":
        return None
    try:
        v = float(str(v).replace("$", "").replace(",", ".").strip())
    except ValueError:
        raise ErroEstoque(f"{rotulo} precisa ser um número")
    if v < 0:
        raise ErroEstoque(f"{rotulo} não pode ser negativo")
    return round(v, 2)


def _campos_de_vitrine(**c):
    """Prateleira, subcategoria, medida e preço — validados e com o preço final resolvido.

    Preço final digitado vale como está (o dono às vezes fecha um valor redondo). Sem ele,
    sai do custo + margem. A margem é texto livre ("15%", "20") e é lida na hora, para
    que um valor que o painel não entende seja recusado em vez de virar preço errado."""
    from command_center.providers import prateleiras
    out = {}
    if "category" in c:
        cat = _texto(c["category"])
        if cat and cat not in prateleiras.POR_CODIGO:
            raise ErroEstoque(f"prateleira desconhecida: {cat!r}")
        out["category"] = cat
    for k in ("subcategory", "size"):
        if k in c:
            out[k] = _texto(c[k])
    if "cost" in c:
        out["cost"] = _dinheiro(c["cost"], "o valor de compra")
    if "markup" in c:
        out["markup"] = _texto(c["markup"])
        try:
            prateleiras.ler_margem(out["markup"])
        except prateleiras.MargemInvalida as e:
            raise ErroEstoque(str(e))
    if "price" in c:
        out["price"] = _dinheiro(c["price"], "o preço final")
        if out["price"] is None and out.get("cost") is not None:
            out["price"] = prateleiras.preco_final(out["cost"], out.get("markup"))
    return out


EDITAVEIS = ("name", "notes", "unit", "min_qty", "category", "subcategory", "size")
DE_PRECO = ("cost", "markup", "price")


def remover_item(con, item_id):
    """Tira a peça das prateleiras (dono, 06/10: "um íconezinho de lixeira… deseja realmente
    excluir essa peça?"). A ficha fica com `active=0` e **nada se apaga**: movimentos, cobranças
    e auditoria continuam apontando para ela, e o razão segue batendo.

    Peça **de cliente** guardada com a gente não sai assim: sumiria da prateleira algo que não é
    nosso. Primeiro devolve ou entrega; depois exclui."""
    it = item(con, item_id)
    if not it["active"]:
        raise ErroEstoque("esta peça já foi excluída")
    dele = um(con, "SELECT COALESCE(SUM(qty), 0) AS n FROM stock_levels WHERE item_id=? AND client_id IS NOT NULL AND qty > 0",
              (item_id,))["n"]
    marcas = ",".join("?" * len(EM_CASA))
    dele += um(con, f"SELECT COUNT(*) AS n FROM stock_units WHERE item_id=? AND client_id IS NOT NULL AND status IN ({marcas})",
               (item_id, *EM_CASA))["n"]
    if dele:
        raise ErroEstoque("Esta peça tem unidade de cliente guardada com a gente. "
                          "Devolva ou entregue ao cliente antes de excluir.")
    con.execute("UPDATE stock_items SET active=0 WHERE id=?", (item_id,))
    return dict(it)


def atualizar_item(con, item_id, **campos):
    """Edita a ficha. `kind` e `tracking` ficam de fora de propósito: trocar uma peça de
    quantidade para número de série apagaria o sentido do saldo que ela já tem."""
    it = item(con, item_id)
    desconhecidos = set(campos) - set(EDITAVEIS) - set(DE_PRECO)
    if desconhecidos:
        raise ErroEstoque(f"campo não editável: {', '.join(sorted(desconhecidos))}")
    mudar = {}
    if "name" in campos:
        if not _texto(campos["name"]):
            raise ErroEstoque("item de estoque precisa de nome")
        mudar["name"] = campos["name"].strip()
    if "notes" in campos:
        mudar["notes"] = _texto(campos["notes"])
    if "unit" in campos:
        mudar["unit"] = _texto(campos["unit"]) or "un"
    if "min_qty" in campos:
        mq = campos["min_qty"]
        if mq not in (None, "") and it["tracking"] == "serie":
            raise ErroEstoque("estoque mínimo não vale para item com número de série")
        mudar["min_qty"] = None if mq in (None, "") else float(mq)
    vitrine = {k: campos[k] for k in ("category", "subcategory", "size") if k in campos}
    if any(k in campos for k in DE_PRECO):
        # custo, margem e preço são uma conta só: o que não veio é o que já estava
        preco = {k: campos.get(k, it[k]) for k in DE_PRECO}
        if "price" not in campos and ("cost" in campos or "markup" in campos):
            preco["price"] = None          # custo ou margem mudou: o preço final é refeito
        vitrine.update(preco)
    mudar.update(_campos_de_vitrine(**vitrine))
    if mudar:
        sets = ", ".join(f"{k}=?" for k in mudar)
        con.execute(f"UPDATE stock_items SET {sets} WHERE id=?", (*mudar.values(), item_id))
    return {k: (it[k], v) for k, v in mudar.items() if it[k] != v}


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


def trocar_dono(con, item_id, para_cliente_id=None, de_cliente_id=None, qty=None, unit_id=None,
                onde=SEDE, by_user_id=None, source="painel", notes=None):
    """Assinalar a peça para um cliente — ou devolvê-la para a URACE.

    Dono, 29/09: *"assinalar aqueles dois sets de pneus para o cliente"*, pelo estoque ou
    pelo card dele. A peça não sai da prateleira; muda de quem ela é. No razão viram dois
    movimentos (sai da URACE, entra no cliente), para `conferir()` continuar refazendo o
    saldo sem nenhuma regra nova.

    De um cliente para **outro** não: é a mesma trava de sempre. Primeiro volta para a
    URACE (quem vendeu a peça de volta), depois vai para o outro — dois passos, cada um
    com nome e hora no histórico.
    """
    it, loc = item(con, item_id), local(con, onde)
    if bool(para_cliente_id) == bool(de_cliente_id):
        raise ErroEstoque("a troca de dono é da URACE para um cliente, ou de um cliente de volta "
                          "para a URACE — nunca de um cliente direto para outro")
    alvo = para_cliente_id or de_cliente_id
    c = um(con, "SELECT id, name, pilot_name FROM clients WHERE id=?", (alvo,))
    if not c:
        raise ErroEstoque(f"cliente #{alvo} não existe")
    nome = c["pilot_name"] or c["name"]
    motivo = f"assinalado para {nome}" if para_cliente_id else f"devolvido por {nome} para a URACE"
    if it["tracking"] == "serie":
        u = _unidade(con, unit_id, it)
        if (u["client_id"] or None) != (de_cliente_id or None):
            dono = "da URACE" if not u["client_id"] else "de outro cliente"
            raise ErroEstoque(f"a unidade {u['serial']} é {dono}")
        con.execute("UPDATE stock_units SET client_id=?, updated_at=? WHERE id=?",
                    (para_cliente_id, agora(), u["id"]))
        _registrar(con, "transferencia", it, unit_id=u["id"], qty=1, from_location_id=u["location_id"],
                   to_location_id=u["location_id"], client_id=para_cliente_id, reason=motivo,
                   by_user_id=by_user_id, source=source, notes=notes)
        return {"unit_id": u["id"], "cliente": nome}
    qty = _quantidade(qty, it)
    a0, a1 = _mexer_saldo(con, it["id"], loc["id"], de_cliente_id, -qty)
    b0, b1 = _mexer_saldo(con, it["id"], loc["id"], para_cliente_id, qty)
    _registrar(con, "saida", it, qty=qty, from_location_id=loc["id"], client_id=de_cliente_id,
               reason=motivo, by_user_id=by_user_id, source=source, notes=notes,
               qty_before=a0, qty_after=a1)
    _registrar(con, "entrada", it, qty=qty, to_location_id=loc["id"], client_id=para_cliente_id,
               reason=motivo, by_user_id=by_user_id, source=source, notes=notes,
               qty_before=b0, qty_after=b1)
    return {"qty": qty, "cliente": nome, "local": loc["code"]}


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


def ultimos_movimentos(con):
    """{item_id: {"ultimo": at, "contagem": at da última contagem física}} — o que diz se a
    ficha tem história. Ficha sem movimento nenhum **nunca foi contada**: o zero dela é
    "ninguém olhou", não "acabou" (25/09: os 16 itens semeados das invoices estavam todos
    assim, e o painel os mostrava como falta)."""
    out = {}
    for m in todos(con, """SELECT item_id, MAX(at) AS ultimo,
                                  MAX(CASE WHEN kind='contagem' THEN at END) AS contagem
                             FROM stock_moves GROUP BY item_id"""):
        out[m["item_id"]] = {"ultimo": m["ultimo"], "contagem": m["contagem"]}
    return out


def nunca_contados(con):
    """Fichas de quantidade, ativas, sem movimento nenhum — a folha da primeira contagem."""
    mov = ultimos_movimentos(con)
    return [dict(i) for i in todos(con, """SELECT id, name, unit, min_qty, kind FROM stock_items
                                             WHERE active=1 AND tracking='quantidade' ORDER BY name""")
            if i["id"] not in mov]


def do_cliente(con, client_id):
    """O que é dele e está com a gente — para aparecer no card do cliente."""
    unidades = todos(con, """SELECT u.*, i.name, i.kind, i.price, lo.name AS local, lo.code AS local_code
                               FROM stock_units u JOIN stock_items i ON i.id=u.item_id
                               LEFT JOIN stock_locations lo ON lo.id=u.location_id
                              WHERE u.client_id=? AND u.status IN {}""".format(
        "(" + ",".join("?" * len(EM_CASA)) + ")"), (client_id, *EM_CASA))
    pecas = todos(con, """SELECT l.*, i.name, i.unit, i.size, i.subcategory, i.image_path IS NOT NULL AS tem_foto,
                                 lo.name AS local, lo.code AS local_code
                            FROM stock_levels l JOIN stock_items i ON i.id=l.item_id
                            JOIN stock_locations lo ON lo.id=l.location_id
                           WHERE l.client_id=? AND l.qty > 0""", (client_id,))
    return {"unidades": [dict(u) for u in unidades], "pecas": [dict(p) for p in pecas]}


# --------------------------------------------------------------------- preço de tabela
def _norm(s):
    """Só letras e números, sem espaço: "O-Ring" e "Oring" são a mesma peça."""
    import re
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def tabela_de_precos(con):
    """Peças com preço final definido no painel — o que vai para a invoice de quem usou a
    peça (dono, 29/09). Só leitura, e só o que alguém de fato preencheu."""
    return [dict(r) for r in todos(con, """SELECT id, name, subcategory, size, unit, price FROM stock_items
                                            WHERE active=1 AND price IS NOT NULL AND price > 0
                                            ORDER BY name""")]


def preco_de_tabela(con, nomes, valor):
    """A peça do estoque cujo nome bate com algum dos `nomes` e cujo preço final é `valor`,
    ou None. É o que faz a invoice montada pela IA não ser marcada "de onde veio este
    valor?" quando ele saiu da tabela do estoque."""
    if valor is None:
        return None
    alvos = [n for n in (_norm(x) for x in nomes) if len(n) >= 3]
    for t in tabela_de_precos(con):
        nome = _norm(t["name"])
        if abs(float(t["price"]) - float(valor)) < 0.01 and any(a == nome or a in nome or nome in a for a in alvos):
            return t
    return None


# --------------------------------------------------------------------- peça usada → cobrança
def registrar_cobranca(con, item_id, client_id, qty, move_id=None, by_user_id=None, task_id=None, notes=None):
    """A peça da URACE foi usada no kart deste cliente: fica a cobrar, com o preço de agora.
    Sem preço final na ficha, a cobrança nasce sem valor — e o gerente vê isso no card."""
    it = item(con, item_id)
    if not um(con, "SELECT 1 AS x FROM clients WHERE id=?", (client_id,)):
        raise ErroEstoque(f"cliente #{client_id} não existe")
    return inserir(con, "stock_charges", client_id=client_id, item_id=it["id"], move_id=move_id, task_id=task_id,
                   qty=float(qty), unit_price=it["price"], notes=notes, created_by=by_user_id)


def cobrancas(con, client_id=None, status="pending"):
    sql = """SELECT ch.*, i.name, i.unit, i.size, i.subcategory, COALESCE(c.pilot_name, c.name) AS cliente,
                    u.name AS por, inv.doc_number
               FROM stock_charges ch JOIN stock_items i ON i.id=ch.item_id JOIN clients c ON c.id=ch.client_id
               LEFT JOIN users u ON u.id=ch.created_by LEFT JOIN invoices inv ON inv.id=ch.invoice_id WHERE 1=1"""
    p = []
    if client_id:
        sql += " AND ch.client_id=?"; p.append(client_id)
    if status:
        sql += " AND ch.status=?"; p.append(status)
    return [dict(r, total=None if r["unit_price"] is None else round(r["unit_price"] * r["qty"], 2))
            for r in todos(con, sql + " ORDER BY ch.id DESC", tuple(p))]


def conciliar_cobrancas(con, invoice_id):
    """A invoice chegou do QuickBooks: as peças a cobrar do cliente que estão nela saem de
    pendente. Bate pelo nome (a peça aparece no item ou na descrição da linha) E pelo preço
    unitário — nome sem preço igual não conta, porque aí a cobrança não é esta."""
    inv = um(con, "SELECT id, client_id FROM invoices WHERE id=?", (invoice_id,))
    if not inv or not inv["client_id"]:
        return []
    pend = [c for c in cobrancas(con, inv["client_id"]) if c["unit_price"] is not None]
    if not pend:
        return []
    linhas = [dict(l, sobra=float(l["qty"] or 1)) for l in todos(
        con, "SELECT item_name, description, qty, unit_price FROM invoice_lines WHERE invoice_id=?", (invoice_id,))]
    baixadas = []
    for ch in sorted(pend, key=lambda x: x["id"]):
        nome = _norm(ch["name"])
        for l in linhas:
            texto = _norm(l["item_name"]) + "|" + _norm(l["description"])
            if (l["unit_price"] is not None and abs(float(l["unit_price"]) - ch["unit_price"]) < 0.01
                    and nome and nome in texto and l["sobra"] >= ch["qty"] - 1e-9):
                l["sobra"] -= ch["qty"]
                con.execute("UPDATE stock_charges SET status='invoiced', invoice_id=?, resolved_at=? WHERE id=?",
                            (invoice_id, agora(), ch["id"]))
                baixadas.append(ch["id"])
                break
    return baixadas
