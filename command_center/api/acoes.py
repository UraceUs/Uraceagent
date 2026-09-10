"""Ações propostas pela IA: argumentos corretos, sem repetir o que já foi decidido.

Três dores do dono (10/09):
1. A invoice chegava com $0 — o agente dizia "$500" no texto, mas o JSON
   vinha com nomes de campo diferentes ("valor", "preco", nome do item no
   lugar do id). Aqui os nomes são normalizados, o item é resolvido pelo
   catálogo do QBO e, se ainda faltar valor, ele é tirado do próprio texto
   da IA (quando há um valor só). O que restar errado vira `problemas` na
   proposta, visível no painel, e a IA recebe uma chance de corrigir.
2. A mesma ação voltava a ser proposta depois de aprovada. Uma ação com a
   mesma assinatura (ex.: mesma tarefa, mesma data) já APROVADA/EXECUTADA
   nos últimos dias não é proposta de novo; uma que ainda estava PENDENTE
   é substituída pela nova (a instrução mais recente manda).
3. O agente não sabia o que já tinha sido aprovado. `estado_do_dia` entra
   em todo comando com as ações do dia e o status de cada uma.
"""
import json
import re

from command_center.db import agora, atualizar, todos, um

ACOES_INVOICE = {"qbo_criar_invoice", "qbo_criar_e_enviar_invoice", "qbo_criar_estimate"}
_ALIAS_LINHA = {
    "item_id": ("item_id", "itemid", "item", "produto_id", "produto", "id_item", "itemref"),
    "unitario": ("unitario", "unit_price", "unitprice", "valor_unitario", "valor", "preco", "price", "amount", "valor_usd"),
    "quantidade": ("quantidade", "qtd", "qty", "quantity"),
    "descricao": ("descricao", "description", "desc", "nome", "name", "item_nome", "servico"),
}
_ALIAS_TOPO = {
    "cliente_id": ("cliente_id", "customer_id", "customerid", "cliente", "customer", "id_cliente"),
    "linhas": ("linhas", "itens", "items", "lines", "line"),
    "vence_em": ("vence_em", "due", "due_date", "duedate", "vencimento"),
    "email": ("email", "e_mail", "email_cobranca", "bill_email"),
    "memo": ("memo", "observacao", "nota", "customer_memo"),
}
_RX_DINHEIRO = re.compile(r"(?<![\w.])\$\s?(\d{1,3}(?:[.,]\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)")


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("US$", "").replace("$", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    elif re.fullmatch(r"\d+,\d{1,2}", s):
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _pega(d, aliases):
    baixo = {str(k).lower(): k for k in d}
    for a in aliases:
        if a in baixo:
            v = d[baixo[a]]
            if isinstance(v, str) and re.fullmatch(r"\s*<[^>]*>\s*", v):      # "<id de qbo_itens_buscar>" = não preencheu
                return None
            return v
    return None


# Ferramentas de LEITURA: o agente executa na hora; nunca viram "ação" para aprovar.
_CONSULTA_RX = re.compile(r"(_buscar|_listar|_ler)$|^(qbo_invoices|qbo_invoice|qbo_empresa|qbo_itens|qbo_estimates|qbo_contas_a_receber|"
                          r"asana_tarefa|asana_tarefas_da_secao|asana_projetos|asana_secoes|asana_comentarios|asana_anexos|"
                          r"docusign_waivers_de|docusign_ambiente|docusign_envelope|gmail_thread|gmail_marcadores|gmail_contas|calendar_eventos|sheets_ler)$")


def eh_consulta(nome):
    return bool(_CONSULTA_RX.search(nome or ""))


def itens_do_cache(con):
    return todos(con, "SELECT id, name, full_name, price FROM qbo_items WHERE active=1 ORDER BY name") if con else []


def _casa_item(nome_ou_desc, itens):
    """Item do catálogo cujo nome está contido na descrição (ou igual). Prefere o nome mais longo."""
    t = (nome_ou_desc or "").lower()
    if not t:
        return None
    exatos = [i for i in itens if (i["name"] or "").lower() == t]
    if len(exatos) == 1:
        return exatos[0]
    contidos = [i for i in itens if len(i["name"] or "") >= 4 and (i["name"] or "").lower() in t]
    if contidos:
        return max(contidos, key=lambda i: len(i["name"]))
    return None


def valores_no_texto(texto):
    """Valores em dólar citados no texto da IA, sem repetição, na ordem."""
    vistos = []
    for m in _RX_DINHEIRO.finditer(texto or ""):
        v = _num(m.group(1))
        if v and v not in vistos:
            vistos.append(v)
    return vistos


PRODUTOS_CONHECIDOS = ("urace daily", "arrive and drive", "academy", "lead and follow", "race support", "trackside", "corrida",
                       "summer camp", "test drive", "security deposit", "practice", "professional coaching", "coaching", "daily")


def _nome_de_produto(*candidatos):
    """Nome para criar o item no QBO: o primeiro candidato que cite um produto conhecido, sem o sufixo ' - piloto - data'."""
    for c in candidatos:
        if not c:
            continue
        base = re.split(r"\s+-\s+", str(c).strip())[0].strip()
        if any(p in base.lower() for p in PRODUTOS_CONHECIDOS) and 3 <= len(base) <= 80 and ":" not in base:
            return base
    return None


def normalizar_invoice(args, texto_ia="", buscar_item=None, buscar_cliente=None, con=None, alvo=None, criar_item=None, notas=None):
    """Devolve (args_normalizados, problemas). `buscar_item(nome)` -> lista de {id, nome};
    `buscar_cliente(texto)` -> lista de {id, nome, email}. Com `con`, usa o catálogo e o
    espelho para resolver item e cliente sem depender do agente."""
    if not isinstance(args, dict):
        return args, ["sem argumentos"]
    cache = itens_do_cache(con) if con else []
    saida = {}
    for chave, aliases in _ALIAS_TOPO.items():
        v = _pega(args, aliases)
        if v is not None:
            saida[chave] = v
    if isinstance(saida.get("cliente_id"), dict):                # {"id": "123", "nome": ...}
        saida["cliente_id"] = saida["cliente_id"].get("id") or saida["cliente_id"].get("value")
    linhas_in = saida.get("linhas")
    if isinstance(linhas_in, dict):
        linhas_in = [linhas_in]
    if not isinstance(linhas_in, list):
        linhas_in = []
    linhas, problemas = [], []
    citados = valores_no_texto(texto_ia)
    for l in linhas_in:
        if not isinstance(l, dict):
            continue
        n = {}
        item = _pega(l, _ALIAS_LINHA["item_id"])
        if isinstance(item, dict):
            item = item.get("id") or item.get("value") or item.get("nome") or item.get("name")
        n["item_id"] = str(item).strip() if item not in (None, "") else None
        n["quantidade"] = _num(_pega(l, _ALIAS_LINHA["quantidade"])) or 1
        unit = _num(_pega(l, _ALIAS_LINHA["unitario"]))
        total = _num(_pega(l, ("total", "valor_total", "subtotal")))
        if (not unit) and total and n["quantidade"]:
            unit = round(total / n["quantidade"], 2)
        n["unitario"] = unit
        desc = _pega(l, _ALIAS_LINHA["descricao"])
        n["descricao"] = str(desc).strip() if desc else None
        # item pelo nome → id numérico do catálogo
        if n["item_id"] and not re.fullmatch(r"\d+", n["item_id"]):
            nome_item = n["item_id"]
            n["item_id"] = None
            if not n["descricao"]:
                n["descricao"] = nome_item
            achado = _casa_item(nome_item, cache) or _casa_item(n["descricao"], cache)
            if achado:
                n["item_id"] = str(achado["id"])
            elif buscar_item:
                try:
                    achados = [x for x in (buscar_item(nome_item) or []) if x.get("id")]
                except Exception:
                    achados = []
                exatos = [x for x in achados if (x.get("nome") or "").strip().lower() == nome_item.strip().lower()]
                if len(exatos) == 1 or len(achados) == 1:
                    n["item_id"] = str((exatos or achados)[0]["id"])
            if not n["item_id"]:
                n["_criar_nome"] = _nome_de_produto(nome_item, n["descricao"])
                if not n["_criar_nome"]:
                    problemas.append(f"item '{nome_item}' não achado no catálogo do QuickBooks (precisa do id numérico)")
        elif not n["item_id"]:
            achado = _casa_item(n["descricao"], cache)
            if achado:
                n["item_id"] = str(achado["id"])
            else:
                n["_criar_nome"] = _nome_de_produto(n["descricao"])
                if not n["_criar_nome"]:
                    problemas.append("linha sem item do QuickBooks")
        linhas.append(n)
    if not linhas:
        problemas.append("invoice sem linhas")
    # valor: se a IA disse UM valor no texto e a linha veio zerada, o texto manda
    zeradas = [l for l in linhas if not l["unitario"]]
    if zeradas and len(citados) == 1 and len(linhas) == 1:
        zeradas[0]["unitario"] = citados[0]
        zeradas[0]["_valor_do_texto"] = True
    for l in linhas:
        if not l["unitario"]:
            problemas.append(f"valor unitário zerado{' em ' + l['descricao'] if l.get('descricao') else ''}")
    # produto que não existe no catálogo: o painel cria (autonomia dada pelo dono, 10/09) — com o valor já resolvido
    for l in linhas:
        nome_novo = l.pop("_criar_nome", None)
        if l.get("item_id") or not nome_novo:
            continue
        if criar_item and l.get("unitario"):
            try:
                novo = criar_item(nome_novo, l["unitario"], l.get("descricao"))
            except Exception as e:
                novo = None
                problemas.append(f"não deu para criar o item '{nome_novo}' no QuickBooks: {str(e)[:120]}")
            if novo and novo.get("id"):
                l["item_id"] = str(novo["id"])
                if notas is not None:
                    notas.append(f"item '{novo.get('nome') or nome_novo}' criado no QuickBooks (id {novo['id']}, ${float(l['unitario']):,.2f}).")
                if con:
                    con.execute("INSERT OR REPLACE INTO qbo_items (id, name, full_name, price, type, active, synced_at) VALUES (?,?,?,?,?,1,?)",
                                (str(novo["id"]), novo.get("nome") or nome_novo, novo.get("nome_completo"), l["unitario"], "Service", agora()))
        if not l.get("item_id"):
            problemas.append(f"item '{nome_novo}' não existe no catálogo do QuickBooks" + ("" if l.get("unitario") else " e sem valor para criá-lo"))
    saida["linhas"] = linhas
    cid = saida.get("cliente_id")
    if cid is None or not re.fullmatch(r"\d+", str(cid).strip()):
        # resolve pelo espelho (última invoice do responsável) ou pelo QBO (e-mail, depois nome)
        email = (saida.get("email") or "").strip().lower() or None
        pessoa = None
        if con:
            if email:
                pessoa = um(con, "SELECT * FROM clients WHERE LOWER(email)=? OR LOWER(email_alt)=?", (email, email))
            if not pessoa and alvo:
                from command_center.providers import identidade
                pessoa, _ = identidade.acha_pessoa(con, nome=alvo, piloto=alvo)
            if pessoa:
                inv = um(con, "SELECT customer_ref, customer_email FROM invoices WHERE client_id=? AND customer_ref IS NOT NULL ORDER BY issued_on DESC LIMIT 1", (pessoa["id"],))
                if inv:
                    cid = inv["customer_ref"]
                    saida.setdefault("email", inv["customer_email"] or pessoa["email"])
                email = email or pessoa["email"]
        if (cid is None or not re.fullmatch(r"\d+", str(cid).strip())) and buscar_cliente:
            for termo in [x for x in (email, (pessoa or {}).get("name") if pessoa else None, alvo) if x]:
                try:
                    achados = [x for x in (buscar_cliente(termo) or []) if x.get("id")]
                except Exception:
                    achados = []
                if len(achados) == 1:
                    cid = achados[0]["id"]
                    saida.setdefault("email", achados[0].get("email"))
                    break
        if cid is None or not re.fullmatch(r"\d+", str(cid).strip()):
            problemas.append("cliente do QuickBooks sem id numérico (busque com qbo_clientes_buscar)")
        else:
            saida["cliente_id"] = str(cid).strip()
    else:
        saida["cliente_id"] = str(cid).strip()
    for k in ("vence_em", "email", "memo"):
        if saida.get(k) is not None:
            saida[k] = str(saida[k])
    return saida, problemas


def normalizar(acao, args, texto_ia="", buscar_item=None, buscar_cliente=None, con=None, alvo=None, criar_item=None, notas=None):
    if acao in ACOES_INVOICE:
        return normalizar_invoice(args, texto_ia, buscar_item, buscar_cliente, con, alvo, criar_item, notas)
    return args, []


def pedido_de_correcao(acao, problemas):
    return ("\n\n[Command Center] A ação " + acao + " que você propôs veio incompleta: " + "; ".join(problemas) + ". "
            "Reescreva SOMENTE as linhas ACAO, com os campos exatos: para invoice, "
            '{"cliente_id":"<id numérico do responsável no QBO, via qbo_clientes_buscar>","linhas":[{"item_id":"<id numérico via qbo_itens_buscar>","quantidade":1,"unitario":<valor em dólares, nunca 0>,"descricao":"…"}],"vence_em":"AAAA-MM-DD","memo":"…","email":"…"}. '
            "Se o dono disse o valor, use exatamente esse valor. Não repita o texto anterior, não explique.")


# ----------------------------------------------------- nome da ferramenta
_PREFIXOS = ("asana__", "docusign__", "google__", "gmail__", "quickbooks__", "qbo__", "mcp__")
MODELO_SESSAO = "1208702559561159"       # "Session Setup | Customer Name_Product…" — modelo oficial do quadro


def nome_canonico(nome):
    """'asana__asana_criar_tarefa' (nome com o prefixo do servidor MCP, como o
    OpenClaw expõe) -> 'asana_criar_tarefa', que é o que a política e o módulo conhecem."""
    n = re.sub(r"[^a-z0-9_]", "", (nome or "").lower())
    mudou = True
    while mudou:
        mudou = False
        for pf in _PREFIXOS:
            if n.startswith(pf):
                n = n[len(pf):]; mudou = True
    return n or "acao_desconhecida"


RACE_PADRAO = "Practice OKC"


def _dbr_us(iso):
    return f"{iso[5:7]}/{iso[8:10]}/{iso[:4]}" if iso and len(iso) >= 10 else (iso or "")


def _idade(dob):
    from datetime import date
    try:
        d = date.fromisoformat((dob or "")[:10]); h = date.today()
        return h.year - d.year - ((h.month, h.day) < (d.month, d.day))
    except ValueError:
        return None


def notas_servico(piloto, responsavel, email=None, telefone=None, dob=None, data=None, produto=None, categoria=None,
                  preco=None, altura=None, peso=None, cintura=None, experiencia=None, extra=None, por=None):
    """A descrição da tarefa de serviço, no bloco padrão do quadro, sempre igual e legível.
    'Invoice link' fica vazio até a invoice sair do QuickBooks (o painel preenche)."""
    idade = _idade(dob)
    v = lambda x: (str(x).strip() if x not in (None, "") else "—")
    linhas = [f"Service Dates for this Month: {_dbr_us(data) if data else '—'}",
              f"Driver's name: {v(piloto)}",
              f"Date of Birth: {_dbr_us(dob) if dob else '—'}",
              f"Age: {idade if idade is not None else '—'}" + ("  (menor: waiver parental)" if idade is not None and idade < 18 else ""),
              f"Height: {v(altura)}",
              f"Weight: {v(peso)}",
              f"Waist: {v(cintura)}",
              f"Karting Experience: {v(experiencia)}",
              "----------------------------------------",
              f"Responsible Name: {v(responsavel)}",
              f"Email: {v(email)}",
              f"Phone: {v(telefone)}",
              "----------------------------------------",
              f"Product: {v(produto)}" + (f" / {categoria}" if categoria else ""),
              "Invoice link: (a IA preenche quando a invoice sair)",
              f"Price: {('$%.2f' % float(preco)) if preco not in (None, '') else '—'}",
              "",
              "Security deposit: —",
              "Price: —"]
    if extra:
        linhas += ["", str(extra).strip()]
    if por:
        linhas += ["", f"[criado pelo Command Center por {por}]"]
    return "\n".join(linhas)


def _partes_do_nome(nome):
    """'David Pera_Urace Daily_Using Own Kart [1/1]' -> (piloto, produto, categoria)."""
    base = re.sub(r"\s*\[[^\]]*\]\s*$", "", nome or "")
    partes = [x.strip() for x in base.split("_")]
    return (partes[0] if partes else None, partes[1] if len(partes) > 1 else None, partes[2] if len(partes) > 2 else None)


def converter(nome, args, con=None, texto=""):
    """Tarefa de serviço numa coluna de dia nasce do modelo oficial (decisão do dono, 04/09):
    asana_criar_tarefa vira asana_criar_do_modelo. Com o espelho (`con`), a descrição é
    montada com os dados do piloto e o campo Race sai 'Practice OKC' (ou Bushnell, se citado)."""
    if nome == "asana_criar_tarefa" and isinstance(args, dict) and not args.get("modelo_gid"):
        from command_center.providers.sync import SECOES_DIAS
        if str(args.get("secao_gid") or "") in SECOES_DIAS:
            novo = {"modelo_gid": MODELO_SESSAO, "nome": args.get("nome"), "secao_gid": str(args.get("secao_gid"))}
            for k in ("notas", "vence_em"):
                if args.get(k):
                    novo[k] = args[k]
            nome, args = "asana_criar_do_modelo", novo
    if nome == "asana_criar_do_modelo" and isinstance(args, dict):
        args = dict(args)
        piloto, produto, categoria = _partes_do_nome(args.get("nome"))
        if con:
            from command_center.api import motor
            cid = motor.cliente_citado(con, (args.get("nome") or "") + " " + (args.get("notas") or "") + " " + (texto or ""))
            c = um(con, "SELECT * FROM clients WHERE id=?", (cid,)) if cid else None
            if c:
                preco = None
                m = re.search(r"Price:\s*\$?\s*([\d.,]+)", args.get("notas") or "")
                if m:
                    preco = _num(m.group(1))
                if preco is None:
                    cit = valores_no_texto(texto)
                    preco = cit[0] if len(cit) == 1 else None
                args["notas"] = notas_servico(c.get("pilot_name") or piloto or c["name"], c["name"], c.get("email"), c.get("phone"), c.get("pilot_dob"),
                                              args.get("vence_em"), produto, categoria, preco, por="IA (AI Command)")
        campos = dict(args.get("campos") or {})
        if not campos.get("Race") and not re.search(r"\b(race|corrida|round|cup|series)\b", (args.get("nome") or "").lower()):
            campos["Race"] = "Practice Bushnell" if re.search(r"bushnell", (args.get("nome") or "") + " " + (texto or ""), re.I) else RACE_PADRAO
        if campos:
            args["campos"] = campos
    return nome, args


# ----------------------------------------------------- assinatura / repetição
def assinatura(acao, args, alvo=None):
    """O que faz duas propostas serem 'a mesma ação'. Curta e estável."""
    a = args if isinstance(args, dict) else {}
    if acao in ACOES_INVOICE:
        total = round(sum((l.get("quantidade") or 1) * (l.get("unitario") or 0) for l in a.get("linhas") or [] if isinstance(l, dict)), 2)
        return f"{acao}|{a.get('cliente_id')}|{a.get('vence_em')}|{total}"
    if acao == "asana_criar_tarefa" or acao == "asana_criar_do_modelo":
        return f"{acao}|{(a.get('nome') or '').strip().lower()}|{a.get('vence_em')}"
    if acao == "docusign_enviar_waiver":
        return f"{acao}|{(a.get('email') or '').strip().lower()}|{a.get('templateId')}"
    if acao == "asana_comentar":
        return f"{acao}|{a.get('gid')}|{(a.get('texto') or '')[:60].strip().lower()}"
    if acao in ("asana_mover_para_secao", "asana_mover_para_finished", "asana_concluir"):
        return f"{acao}|{a.get('gid')}|{a.get('secao_gid') or ''}"
    return f"{acao}|{(alvo or '')[:80].strip().lower()}"


def ja_decidida(con, assin, dias=3):
    """Ação igual já APROVADA/EXECUTADA recentemente (não repropor) ou ainda PENDENTE (substituir)."""
    for a in todos(con, """SELECT id, status, command_id, payload FROM ai_actions
                           WHERE created_at >= datetime('now', ?) ORDER BY id DESC LIMIT 300""", (f"-{dias} days",)):
        try:
            p = json.loads(a["payload"] or "{}")
        except ValueError:
            continue
        if p.get("assinatura") == assin:
            if a["status"] in ("APPROVED", "RUNNING", "DONE"):
                return "feita", a
            if a["status"] == "PROPOSED":
                return "pendente", a
    return None, None


def substituir(con, antiga_id, nova_id):
    atualizar(con, "ai_actions", antiga_id, status="REJECTED", finished_at=agora(),
              result=f"substituída pela proposta #{nova_id} (instrução mais recente do dono)")
    con.execute("UPDATE approvals SET decided_at=?, decision='REJECTED', comment=? WHERE action_id=? AND decided_at IS NULL",
                (agora(), f"substituída pela #{nova_id}", antiga_id))


# ----------------------------------------------------- contexto do dia
_ROTULO = {"PROPOSED": "PENDENTE (esperando o dono)", "APPROVED": "APROVADA (executando)", "RUNNING": "EXECUTANDO",
           "DONE": "FEITA", "FAILED": "FALHOU", "REJECTED": "REJEITADA/SUBSTITUÍDA", "BLOCKED": "BLOQUEADA"}


def estado_do_dia(con, user_id):
    """Bloco que vai no comando: o que já foi proposto hoje e o status de cada ação."""
    rows = todos(con, """SELECT a.id, a.action, a.status, a.payload, a.command_id FROM ai_actions a
                         JOIN ai_commands c ON c.id=a.command_id
                         WHERE c.user_id=? AND a.created_at >= date('now') ORDER BY a.id""", (user_id,))
    if not rows:
        return ""
    linhas = []
    for a in rows[-25:]:
        try:
            p = json.loads(a["payload"] or "{}")
        except ValueError:
            p = {}
        alvo = p.get("alvo") or (p.get("descricao") or "")[:60]
        linhas.append(f"- #{a['id']} {a['action']} → {alvo}: {_ROTULO.get(a['status'], a['status'])}")
    return ("\n\nAÇÕES JÁ PROPOSTAS HOJE (não proponha de novo o que está APROVADA, EXECUTANDO ou FEITA; "
            "se o dono mudou algo — valor, data, pessoa — proponha SÓ a ação que muda, com os dados novos; "
            "o que está PENDENTE pode ser reproposto com correção):\n" + "\n".join(linhas))
