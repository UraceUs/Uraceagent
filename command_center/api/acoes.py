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
            return d[baixo[a]]
    return None


def valores_no_texto(texto):
    """Valores em dólar citados no texto da IA, sem repetição, na ordem."""
    vistos = []
    for m in _RX_DINHEIRO.finditer(texto or ""):
        v = _num(m.group(1))
        if v and v not in vistos:
            vistos.append(v)
    return vistos


def normalizar_invoice(args, texto_ia="", buscar_item=None):
    """Devolve (args_normalizados, problemas). `buscar_item(nome)` -> lista de {id, nome}."""
    if not isinstance(args, dict):
        return args, ["sem argumentos"]
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
            if buscar_item:
                try:
                    achados = [x for x in (buscar_item(nome_item) or []) if x.get("id")]
                except Exception:
                    achados = []
                exatos = [x for x in achados if (x.get("nome") or "").strip().lower() == nome_item.strip().lower()]
                if len(exatos) == 1 or len(achados) == 1:
                    n["item_id"] = str((exatos or achados)[0]["id"])
            if not n["item_id"]:
                problemas.append(f"item '{nome_item}' não achado no catálogo do QuickBooks (precisa do id numérico)")
        elif not n["item_id"]:
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
    saida["linhas"] = linhas
    cid = saida.get("cliente_id")
    if cid is None or not re.fullmatch(r"\d+", str(cid).strip()):
        problemas.append("cliente do QuickBooks sem id numérico (busque com qbo_clientes_buscar)")
    else:
        saida["cliente_id"] = str(cid).strip()
    for k in ("vence_em", "email", "memo"):
        if saida.get(k) is not None:
            saida[k] = str(saida[k])
    return saida, problemas


def normalizar(acao, args, texto_ia="", buscar_item=None):
    if acao in ACOES_INVOICE:
        return normalizar_invoice(args, texto_ia, buscar_item)
    return args, []


def pedido_de_correcao(acao, problemas):
    return ("\n\n[Command Center] A ação " + acao + " que você propôs veio incompleta: " + "; ".join(problemas) + ". "
            "Reescreva SOMENTE as linhas ACAO, com os campos exatos: para invoice, "
            '{"cliente_id":"<id numérico do responsável no QBO, via qbo_clientes_buscar>","linhas":[{"item_id":"<id numérico via qbo_itens_buscar>","quantidade":1,"unitario":<valor em dólares, nunca 0>,"descricao":"…"}],"vence_em":"AAAA-MM-DD","memo":"…","email":"…"}. '
            "Se o dono disse o valor, use exatamente esse valor. Não repita o texto anterior, não explique.")


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
