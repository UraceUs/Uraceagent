"""Serviços da agenda e os preços deles (#50).

Dono, 01/10: *"deixe o campo dos preços para ter a possibilidade de ser facilmente
alterados"*. Quem muda o preço é o gerente, numa tela do site interno, sem código:
- o **preço vive no banco**, não no código nem no WordPress;
- o **agendamento guarda o serviço e o valor do dia em que foi marcado**: mudar o preço
  depois não muda a cobrança de quem já marcou;
- **desativar não apaga**: o serviço some da área do cliente, e o histórico continua;
- cada serviço aponta para um **item do QuickBooks**, que é o que vai na linha da invoice.

Nada é inventado: sem serviço cadastrado pela equipe, o cliente não consegue marcar
(NO FAKE DATA).
"""
import re

from command_center.db import agora, atualizar, inserir, todos, um

MAX_PRECO = 100_000


class ErroServico(ValueError):
    pass


def preco(v):
    """'719', '719.9', '$1,856.90' → 719.0 / 719.9 / 1856.9. Nada de negativo nem absurdo."""
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        t = re.sub(r"[\s$]", "", str(v or "")).replace(",", "")
        if not re.fullmatch(r"\d+(\.\d{1,2})?", t):
            raise ErroServico("preço inválido: use números, como 719 ou 719.90")
        n = float(t)
    if not 0 <= n <= MAX_PRECO:
        raise ErroServico(f"preço fora do limite (0 a {MAX_PRECO:,})")
    return round(n, 2)


def _texto(v, n):
    v = re.sub(r"\s+", " ", (v or "").strip())
    return v[:n] or None


def lista(con, ativos=False):
    sql = ("SELECT s.*, q.name AS qbo_item_name, qe.name AS extra_item_name FROM booking_services s"
           " LEFT JOIN qbo_items q ON q.id=s.qbo_item_id LEFT JOIN qbo_items qe ON qe.id=s.extra_item_id"
           + (" WHERE s.active=1" if ativos else "") + " ORDER BY s.active DESC, s.sort, s.name")
    return [dict(s) for s in todos(con, sql)]


def cartao_do_site(s):
    """#297 (dono, 16/10): *"os serviços que estão lá em cada página, a gente consiga alterar o valor, alterar o
    nome, alterar as coisas ali pelo Command Center"*. O que o cartão do kart mostra no site sai do serviço do
    painel; o campo vazio cai no texto de sempre do kart (`conteudo.KARTS`), e um kart novo, que não está lá,
    cai no nome do serviço."""
    from command_center.vitrine.conteudo import kart_da_chave
    k = kart_da_chave(s.get("site_kart")) or {}
    proprio = s.get("own_kart")
    return {"titulo": s.get("site_title") or k.get("nome") or s.get("site_kart") or s.get("name"),
            "linha": s.get("site_subtitle") or k.get("idade") or "",
            "aviso": s.get("site_note") or k.get("aviso") or "",
            "proprio": bool(k.get("proprio")) if proprio is None else bool(proprio)}


def para_cliente(con, cartao=False):
    """O que a área do cliente mostra para marcar sessão: nome, descrição e preço. Nada do QuickBooks.

    `site_kart` (#263) é a chave do kart do site que este serviço vende: é por ela que a página do
    Arrive and Drive e a reserva acham o serviço do kart escolhido — nunca pelo nome. #297: `cartao=True`
    (a página do site) traz também o cartão que o site mostra — nome no site, linha de baixo, aviso, kart próprio."""
    return [{"id": s["id"], "name": s["name"], "description": s["description"], "price": s["price"],
             "deposit": s["deposit"] or 0, "site_kart": s["site_kart"],
             **({"sort": s["sort"], **cartao_do_site(s)} if cartao else {})}
            for s in lista(con, True) if (s["kind"] or "session") == "session"]


def do_kart(con, chave):
    """O serviço ativo deste kart do site, quando é um só. #263: dois serviços com a mesma chave (ou
    nenhum) não viram escolha automática — o site trata como kart sem serviço."""
    achados = [s for s in para_cliente(con) if (s["site_kart"] or "").strip().lower() == (chave or "").strip().lower()]
    return achados[0] if len(achados) == 1 else None


def addon_do_site(con, chave=None):
    """#279: o add-on do dia de treino que o site vende (hoje, o Lead and Follow): o serviço ativo de tipo
    'addon' com essa chave. Preço do painel (#50). Nenhum ou dois com a mesma chave: None (ninguém escolhe
    no lugar da pessoa)."""
    from command_center.vitrine.conteudo import LEAD_AND_FOLLOW
    chave = (chave or LEAD_AND_FOLLOW["chave"]).strip().lower()
    achados = [s for s in lista(con, True) if s["kind"] == "addon" and (s["site_kart"] or "").strip().lower() == chave]
    if len(achados) != 1:
        return None
    s = achados[0]
    # #297: o nome e o texto da caixa no site também são do painel (vazio: o texto de sempre)
    return {"id": s["id"], "name": s["name"], "price": s["price"], "key": s["site_kart"],
            "titulo": s["site_title"] or s["name"], "texto": s["description"] or LEAD_AND_FOLLOW["texto"]}


def paginas_do_site():
    """#312 (dono, 16/10): *"a gente escolhe em qual página que esse serviço vai estar"*. As páginas do site em que
    um serviço do painel ou um cartão de preço entra, com o endereço de cada uma: as que o site tem de verdade
    (o Arrive and Drive de `conteudo.ARRIVE` e as três dos cartões de `cartoes_site.PAGINAS`), nenhuma a mais."""
    from command_center.providers.cartoes_site import PAGINAS
    from command_center.vitrine.conteudo import ARRIVE
    return [{"id": "arrive-and-drive", "nome": "Arrive and Drive", "caminho": ARRIVE["caminho"], "cartoes": False},
            {"id": "academy", "nome": "Academy", "caminho": PAGINAS["academy"], "cartoes": True},
            {"id": "pro-team", "nome": "Pro Team", "caminho": PAGINAS["pro-team"], "cartoes": True},
            {"id": "for-beginners", "nome": "For Beginners", "caminho": PAGINAS["for-beginners"], "cartoes": True}]


def _chave(s):
    return " ".join(str(s.get("site_kart") or "").split()).lower()


def onde_no_site(servicos):
    """#312: onde cada serviço aparece hoje no site, pela mesma regra que monta as páginas — é o que o seletor de
    página do painel mostra para o serviço que já existe.

    - `kart`: sessão ativa com a chave de um kart, a única com essa chave → cartão do kart no Arrive and Drive e na
      reserva (`paginas._karts_do_painel`);
    - `addon`: add-on ativo com a chave do Lead and Follow, o único → caixa da reserva do Arrive and Drive
      (`addon_do_site`); add-on com outra chave o site não mostra (`nenhum`);
    - `plano`: plano ativo → página da Academy (`planos_para_cliente`);
    - `area`: sessão ativa sem kart → só na área do cliente;
    - `repetido`: dois ou mais ativos do mesmo tipo com a mesma chave → o site não mostra nenhum (`com`: os outros);
    - `desativado`: fora do site e da área do cliente.

    Devolve {id: {"onde", "pagina", "chave", "com"}}."""
    from command_center.vitrine.conteudo import LEAD_AND_FOLLOW
    lf = LEAD_AND_FOLLOW["chave"].lower()
    grupos = {}
    for s in servicos:
        if s["active"] and _chave(s) and (s["kind"] or "session") in ("session", "addon"):
            grupos.setdefault(((s["kind"] or "session"), _chave(s)), []).append(s)
    out = {}
    for s in servicos:
        kind, k = s["kind"] or "session", _chave(s)
        d = {"onde": "desativado", "pagina": None, "chave": s.get("site_kart"), "com": []}
        if not s["active"]:
            pass
        elif kind == "plan":
            d.update(onde="plano", pagina="academy")
        elif kind == "addon" and k != lf:
            d.update(onde="nenhum")
        elif not k:
            d.update(onde="area")
        elif len(grupos[(kind, k)]) > 1:
            d.update(onde="repetido", com=[o["name"] for o in grupos[(kind, k)] if o["id"] != s["id"]])
        else:
            d.update(onde="addon" if kind == "addon" else "kart", pagina="arrive-and-drive")
        out[s["id"]] = d
    return out


def lista_no_painel(con):
    """A lista de Serviços e preços com o lugar de cada serviço no site (#312)."""
    ss = lista(con)
    onde = onde_no_site(ss)
    return [{**s, "no_site": onde[s["id"]]} for s in ss]


def planos_para_cliente(con):
    """#169: os planos mensais que o site vende (Academy, Boost): preço por mês, meses, sessões por mês."""
    return [{"id": s["id"], "name": s["name"], "description": s["description"], "price": s["price"],
             "months": s["months"] or 1, "sessions_month": s["sessions_month"] or 0,
             "total": round(s["price"] * (s["months"] or 1), 2)}
            for s in lista(con, True) if s["kind"] == "plan"]


def plano(con, sid):
    s = um(con, "SELECT * FROM booking_services WHERE id=? AND active=1 AND kind='plan'", (sid,)) if sid else None
    if not s:
        raise ErroServico("Choose a plan.")
    return s


def itens_qbo(con):
    """Itens do QuickBooks (espelho local) que a equipe pode escolher. Dono, 01/10: *"por
    enquanto deixe só os academies e o race daily using own kart"*."""
    return [dict(i) for i in todos(con, """SELECT id, name, full_name, price FROM qbo_items
                                            WHERE active=1 AND COALESCE(type,'Service')='Service'
                                              AND (LOWER(COALESCE(full_name, name)) LIKE '%academy%'
                                                   OR (LOWER(COALESCE(full_name, name)) LIKE '%daily%'
                                                       AND LOWER(COALESCE(full_name, name)) LIKE '%own kart%'))
                                            ORDER BY name""")]


def _dados(con, d, parcial):
    s = {}
    if not parcial or "name" in d:
        nome = _texto(d.get("name"), 80)
        if not nome or len(nome) < 3:
            raise ErroServico("dê um nome ao serviço (o cliente lê, em inglês)")
        s["name"] = nome
    if not parcial or "price" in d:
        s["price"] = preco(d.get("price"))
    if "description" in d:
        s["description"] = _texto(d.get("description"), 300)
    if "qbo_item" in d:
        # dono, 01/10: "que seja possível que seja um texto personalizado". O que bate com
        # o nome de um item vira o item; o resto é o texto da linha da invoice.
        t = re.sub(r"\s+", " ", (d["qbo_item"] or "").strip())[:120]
        item = um(con, """SELECT id FROM qbo_items WHERE active=1
                           AND (LOWER(name)=LOWER(?) OR LOWER(COALESCE(full_name,''))=LOWER(?))""", (t, t)) if t else None
        s["qbo_item_id"] = item["id"] if item else None
        s["invoice_text"] = None if item else (t or None)
    if "qbo_item_id" in d and "qbo_item" not in d:
        item = (str(d["qbo_item_id"]).strip() if d["qbo_item_id"] is not None else "") or None
        if item and not um(con, "SELECT 1 AS x FROM qbo_items WHERE id=?", (item,)):
            raise ErroServico("item do QuickBooks não encontrado (sincronize o QuickBooks e tente de novo)")
        s["qbo_item_id"] = item
    if "site_kart" in d:
        # #263: a chave do kart do site que este serviço vende; vazio = serviço que não é do site. Nome
        # parecido não vale: a chave é exata. #297 (dono, 16/10: "se a gente quiser adicionar algum outro"):
        # além dos karts de `conteudo.KARTS`, uma chave nova é um kart novo na página do Arrive and Drive.
        from command_center.vitrine.conteudo import LEAD_AND_FOLLOW, kart_da_chave
        t = " ".join(str(d["site_kart"] or "").split())
        if not t:
            s["site_kart"] = None
        elif t.lower() == LEAD_AND_FOLLOW["chave"].lower():      # #279: o add-on do dia de treino
            s["site_kart"] = LEAD_AND_FOLLOW["chave"]
        elif kart_da_chave(t):
            s["site_kart"] = kart_da_chave(t)["nome"]
        else:
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .+\-/]{1,39}", t):
                raise ErroServico("kart novo: dê um nome curto (2 a 40 letras ou números), como 'Rental 2-stroke Pro'")
            s["site_kart"] = t
    # #297: o cartão do kart no site — nome, linha de baixo, aviso e "o cliente traz o kart". Vazio volta ao de sempre.
    if "site_title" in d:
        s["site_title"] = _texto(d.get("site_title"), 60)
    if "site_subtitle" in d:
        s["site_subtitle"] = _texto(d.get("site_subtitle"), 90)
    if "site_note" in d:
        s["site_note"] = _texto(d.get("site_note"), 240)
    if "own_kart" in d:
        s["own_kart"] = None if d["own_kart"] is None else (1 if d["own_kart"] else 0)
    if "deposit" in d:
        # #50: depósito por sessão (Arrive and Drive: US$ 400); vazio ou 0 = sem depósito
        s["deposit"] = preco(d["deposit"]) if d["deposit"] not in (None, "", 0, "0") else 0.0
    if "deposit_required" in d and d["deposit_required"] is not None:
        s["deposit_required"] = 1 if d["deposit_required"] else 0     # #317: o checkout não passa sem o depósito
    if "kind" in d and d["kind"] is not None:
        if d["kind"] not in ("session", "plan", "addon"):
            raise ErroServico("tipo inválido: session (sessão avulsa), plan (plano mensal) ou addon (add-on do dia)")
        s["kind"] = d["kind"]
    if "months" in d:
        m = int(d["months"]) if d["months"] not in (None, "") else None
        if m is not None and not 1 <= m <= 36:
            raise ErroServico("meses do plano: de 1 a 36")
        s["months"] = m
    if "sessions_month" in d:
        n = int(d["sessions_month"]) if d["sessions_month"] not in (None, "") else None
        if n is not None and not 0 <= n <= 31:
            raise ErroServico("sessões por mês: de 0 a 31")
        s["sessions_month"] = n
    if "extra_price" in d:
        # #314: o valor da sessão extra do plano (vazio: o mensal ÷ sessões por mês)
        s["extra_price"] = preco(d["extra_price"]) if d["extra_price"] not in (None, "", 0, "0") else None
    if "extra_item" in d:
        # #314: o item do QuickBooks da sessão extra do plano, pelo nome (vazio: o item "Extra session" do QuickBooks)
        t = re.sub(r"\s+", " ", (d["extra_item"] or "").strip())[:120]
        item = um(con, """SELECT id FROM qbo_items WHERE active=1
                           AND (LOWER(name)=LOWER(?) OR LOWER(COALESCE(full_name,''))=LOWER(?))""", (t, t)) if t else None
        if t and not item:
            raise ErroServico("item da sessão extra não encontrado no QuickBooks (escolha da lista)")
        s["extra_item_id"] = item["id"] if item else None
    if "active" in d and d["active"] is not None:
        s["active"] = 1 if d["active"] else 0
    if "sort" in d and d["sort"] is not None:
        s["sort"] = int(d["sort"])
    return s


MSG_DEPOSITO_OBRIGATORIO = ("Security deposit obrigatório: informe o valor do depósito (maior que zero) "
                            "ou desmarque \"obrigatório\".")


def _confere_deposito(s):
    """#317 (dono, 16/10): "coloca em cada serviço … um checkbox para marcar que ele é obrigatório". Marcado, a
    sessão nunca fica sem depósito: nem ao salvar, nem no checkout."""
    if (s.get("kind") or "session") == "session" and s.get("deposit_required") and not float(s.get("deposit") or 0) > 0:
        raise ErroServico(MSG_DEPOSITO_OBRIGATORIO)


class ChaveRepetida(ErroServico):
    """#312 (revisão): o serviço ficaria ativo com a chave de outro ativo do mesmo tipo (409)."""


def _confere_chave(con, s, sid=None):
    """#312 (revisão): dois serviços ativos do mesmo tipo com a mesma chave tiram o kart (ou a caixa do add-on) do site
    — é a regra de `onde_no_site` e da página. Quem cria esse conflito (criar, trocar a chave, o tipo, ou reativar) é
    recusado com o que fazer; a tela, a API e o MCP passam por aqui."""
    kind, k = s.get("kind") or "session", _chave(s)
    if not s.get("active", 1) or not k or kind not in ("session", "addon"):
        return
    outros = [o for o in todos(con, "SELECT id, name, kind, site_kart FROM booking_services WHERE active=1 AND id IS NOT ?", (sid,))
              if (o["kind"] or "session") == kind and _chave(o) == k]
    if not outros:
        return
    if kind == "addon":
        raise ChaveRepetida(f'O add-on {s["site_kart"]} já é vendido por "{outros[0]["name"]}": dois add-ons ativos com a mesma '
                            "chave tiram a caixa da reserva do site. Desative aquele antes.")
    raise ChaveRepetida(f'O kart {s["site_kart"]} já é vendido por "{outros[0]["name"]}": dois serviços ativos com o mesmo kart '
                        "tiram o kart do site. Desative aquele antes ou escolha outro kart.")


def criar(con, por, d):
    s = _dados(con, d, parcial=False)
    if s.get("kind") == "plan" and not s.get("months"):
        s["months"] = 1
    s.setdefault("deposit_required", 0)
    _confere_deposito(s)
    if um(con, "SELECT 1 AS x FROM booking_services WHERE lower(name)=lower(?) AND active=1", (s["name"],)):
        raise ErroServico("já existe um serviço ativo com esse nome")
    _confere_chave(con, s)
    return inserir(con, "booking_services", **s, updated_by=por, updated_at=agora())


def mudar(con, por, sid, d):
    """Devolve {campo: (antes, depois)} — vai para a auditoria."""
    atual = um(con, "SELECT * FROM booking_services WHERE id=?", (sid,))
    if not atual:
        raise ErroServico("serviço não existe")
    s = _dados(con, d, parcial=True)
    _confere_deposito({**dict(atual), **s})
    mud = {k: (atual[k], v) for k, v in s.items() if atual[k] != v}
    # #312 (revisão): só barra a mudança que CRIA o conflito (trocar a chave ou o tipo, ou reativar). Dois repetidos que
    # já existem continuam editáveis (preço, nome…), senão ninguém consegue arrumar.
    if {"site_kart", "kind"} & set(mud) or ("active" in mud and mud["active"][1]):
        _confere_chave(con, {**dict(atual), **s}, sid)
    if mud:
        atualizar(con, "booking_services", sid, **{k: v for k, (_, v) in mud.items()}, updated_by=por, updated_at=agora())
    return mud


def do_agendamento(con, sid):
    """O serviço escolhido pelo cliente: tem de existir e estar ativo."""
    s = um(con, "SELECT * FROM booking_services WHERE id=? AND active=1", (sid,)) if sid else None
    if not s:
        raise ErroServico("Choose the type of session.")
    return s
