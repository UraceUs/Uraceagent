"""MCP por HTTP — o Command Center como conector remoto.

Dono, 23/09: quer o painel ligado como conector, para um Claude de fora usar ferramentas
de verdade em vez de ele virar o terminal.

O servidor MCP do painel **já existia** (`adminai/mcp/command_center_mcp.py`, escrito em
21/09 para isto: *"vai ser um Claude provavelmente"*). O que faltava era só o transporte:
ele fala **stdio**, que serve para quem roda na mesma máquina. Conector remoto precisa de
HTTP. É isso que este módulo acrescenta — as mesmas ferramentas, a mesma trava.

**Só leitura, por construção.** Nenhuma ferramenta aqui escreve. Isso não é confiança no
modelo: a ferramenta que não deve existir simplesmente não é registrada, e não há como
desobedecer o que não existe. A chave de API usada também deve ser `read_only`; as duas
travas valem juntas, de propósito.

Se um dia um Claude de fora precisar **agir**, o caminho certo não é ganhar uma chave que
escreve: é propor a ação no painel, com política e aprovação humana, como a IA de dentro
já faz.

Vai atrás do mesmo `handle /ops*` do Caddy, então não há nada novo para configurar no
servidor web.
"""
import json
import sqlite3

from fastapi import APIRouter, Depends, Request, Response

from command_center.api import atencao, auth
from command_center.db import conectar_somente_leitura, get_db, todos, um
from command_center.providers import estoque

r = APIRouter(prefix="/ops/mcp", tags=["mcp"])

# Versão do protocolo que sabemos falar. Cliente que pedir outra recebe esta de volta —
# é o que a especificação manda, e é melhor que recusar por diferença de data.
PROTOCOLO = "2025-06-18"
NOME, VERSAO = "urace-command-center", "1.0.0"


# ---------------------------------------------------------------- ferramentas
# Cada uma recebe a conexão e devolve dado. Nenhuma escreve. Nenhuma recebe SQL de fora:
# caminho e filtro são fechados aqui, senão a "consulta livre" vira escrita disfarçada.
def _f_atencao(con, **_):
    return {"itens": atencao.coletar(con)}


def _f_estoque(con, busca=None, **_):
    itens = [dict(i) for i in todos(
        con, "SELECT id, name, kind, unit, min_qty, sku FROM stock_items WHERE active=1 ORDER BY name")]
    for i in itens:
        i["total"] = estoque.saldo(con, i["id"])
        i["nosso"] = estoque.vendavel(con, i["id"])
    if busca:
        t = busca.lower()
        itens = [i for i in itens if t in (i["name"] or "").lower() or t in (i["sku"] or "").lower()]
    return {"itens": itens, "repor": estoque.abaixo_do_minimo(con)}


def _f_estoque_item(con, id=None, **_):
    it = um(con, "SELECT * FROM stock_items WHERE id=?", (id,))
    if not it:
        raise ValueError(f"item de estoque {id} não existe")
    movimentos = todos(con, "SELECT kind, qty, reason, at, notes FROM stock_moves "
                            "WHERE item_id=? ORDER BY id DESC LIMIT 50", (id,))
    return {"item": dict(it), "total": estoque.saldo(con, id),
            "nosso": estoque.vendavel(con, id), "movimentos": [dict(m) for m in movimentos]}


def _f_clientes(con, busca=None, limite=50, **_):
    sql = ("SELECT id, name, pilot_name, email, phone, status, vip FROM clients "
           "WHERE COALESCE(kind,'') <> 'separado'")
    p = []
    if busca:
        sql += " AND (name LIKE ? OR pilot_name LIKE ? OR email LIKE ?)"
        p += [f"%{busca}%"] * 3
    sql += " ORDER BY name LIMIT ?"
    p.append(min(int(limite or 50), 200))
    return {"clientes": [dict(c) for c in todos(con, sql, tuple(p))]}


def _f_cliente(con, id=None, **_):
    c = um(con, "SELECT * FROM clients WHERE id=?", (id,))
    if not c:
        raise ValueError(f"cliente {id} não existe")
    return {"cliente": dict(c),
            "servicos": [dict(t) for t in todos(
                con, "SELECT id, title, section, status, due_on FROM tasks WHERE client_id=? "
                     "ORDER BY COALESCE(due_on,'') DESC LIMIT 60", (id,))],
            "invoices": [dict(i) for i in todos(
                con, "SELECT doc_number, amount, balance, status, issued_on, due_on FROM invoices "
                     "WHERE client_id=? ORDER BY COALESCE(issued_on,'') DESC LIMIT 40", (id,))],
            "waivers": [dict(w) for w in todos(
                con, "SELECT signer_name, status, completed_at, expires_at FROM waivers "
                     "WHERE client_id=? ORDER BY id DESC LIMIT 20", (id,))],
            "estoque_dele": estoque.do_cliente(con, id)}


def _f_invoices(con, status=None, limite=80, **_):
    sql = "SELECT id, client_id, doc_number, amount, balance, status, issued_on, due_on FROM invoices"
    p = []
    if status:
        sql += " WHERE UPPER(status)=UPPER(?)"
        p.append(status)
    sql += " ORDER BY COALESCE(issued_on,'') DESC LIMIT ?"
    p.append(min(int(limite or 80), 300))
    linhas = [dict(i) for i in todos(con, sql, tuple(p))]
    aberto = sum(float(i["balance"] or 0) for i in linhas)
    return {"invoices": linhas, "total_em_aberto": round(aberto, 2)}


def _f_corridas(con, limite=40, **_):
    return {"corridas": [dict(x) for x in todos(
        con, "SELECT id, name, series, track, date_start, date_end FROM races "
             "WHERE COALESCE(active,1)=1 ORDER BY COALESCE(date_start,'') DESC LIMIT ?",
        (min(int(limite or 40), 200),))]}


def _f_auditoria(con, limite=100, **_):
    return {"registros": [dict(a) for a in todos(
        con, "SELECT at, event, actor, entity_type, entity_id FROM audit_logs "
             "ORDER BY id DESC LIMIT ?", (min(int(limite or 100), 500),))]}


def _f_resumo(con, **_):
    def n(tabela, onde=""):
        return um(con, f"SELECT COUNT(*) n FROM {tabela} {onde}")["n"]
    return {
        "clientes": n("clients", "WHERE COALESCE(kind,'') <> 'separado'"),
        "servicos": n("tasks"),
        "invoices_abertas": n("invoices", "WHERE COALESCE(balance,0) > 0"),
        "waivers": n("waivers"),
        "corridas": n("races"),
        "itens_de_estoque": n("stock_items", "WHERE active=1"),
        "itens_a_repor": len(estoque.abaixo_do_minimo(con)),
        "catalogo_fornecedor": n("supplier_products"),
        "precisa_de_atencao": len(atencao.coletar(con)),
    }


FERRAMENTAS = {
    "urace_resumo": (
        "Panorama do negócio em números: clientes, serviços, invoices em aberto, waivers, "
        "corridas, estoque e quantos itens precisam de reposição. É a melhor primeira pergunta.",
        {}, [], _f_resumo),
    "urace_atencao": (
        "O que precisa de ação humana hoje, já priorizado: waiver parada, invoice vencida, "
        "conversa sem resposta, e-mail devolvido.", {}, [], _f_atencao),
    "urace_estoque": (
        "Estoque da URACE: cada item com saldo total, quanto é nosso (o resto é peça de "
        "cliente guardada com a gente) e o que está abaixo do mínimo.",
        {"busca": {"type": "string", "description": "filtra por nome ou SKU"}}, [], _f_estoque),
    "urace_estoque_item": (
        "Uma peça do estoque com o histórico de movimentos — é o razão que explica o saldo.",
        {"id": {"type": "integer", "description": "id do item"}}, ["id"], _f_estoque_item),
    "urace_clientes": (
        "Clientes da URACE: responsável, piloto, contato e situação.",
        {"busca": {"type": "string", "description": "nome, piloto ou e-mail"},
         "limite": {"type": "integer", "description": "quantos (padrão 50, teto 200)"}},
        [], _f_clientes),
    "urace_cliente": (
        "Ficha completa de um cliente: serviços, invoices, waivers e as peças dele que "
        "estão com a gente.",
        {"id": {"type": "integer", "description": "id do cliente"}}, ["id"], _f_cliente),
    "urace_invoices": (
        "Invoices espelhadas do QuickBooks: quem deve, quanto e desde quando.",
        {"status": {"type": "string", "description": "opcional: paid, sent, overdue"},
         "limite": {"type": "integer"}}, [], _f_invoices),
    "urace_corridas": (
        "Calendário de corridas da equipe.", {"limite": {"type": "integer"}}, [], _f_corridas),
    "urace_auditoria": (
        "Rastro de auditoria do painel: quem fez o quê e quando. Append-only por gatilho "
        "no banco — nem um bug apaga.",
        {"limite": {"type": "integer", "description": "padrão 100, teto 500"}}, [], _f_auditoria),
}


# ------------------------------------------------------------------ protocolo
def _resposta(ident, resultado):
    return {"jsonrpc": "2.0", "id": ident, "result": resultado}


def _erro(ident, codigo, mensagem):
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": codigo, "message": mensagem}}


def _lista_ferramentas():
    return [{"name": nome, "description": desc,
             "inputSchema": {"type": "object", "properties": props,
                             "required": obrig, "additionalProperties": False}}
            for nome, (desc, props, obrig, _) in FERRAMENTAS.items()]


def _texto(dado):
    """O MCP devolve conteúdo; JSON legível é o que um modelo usa melhor."""
    return [{"type": "text", "text": json.dumps(dado, ensure_ascii=False, indent=1, default=str)}]


def tratar(mensagem, con, quem):
    """Uma mensagem JSON-RPC. Devolve o dicionário de resposta, ou None para notificação."""
    ident = mensagem.get("id")
    metodo = mensagem.get("method")
    params = mensagem.get("params") or {}

    # Notificação (sem id): a especificação manda não responder com corpo.
    if ident is None and metodo and metodo.startswith("notifications/"):
        return None

    if metodo == "initialize":
        return _resposta(ident, {
            "protocolVersion": PROTOCOLO,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": NOME, "version": VERSAO},
            "instructions": (
                "Painel de operações da URACE.US (kart racing, Orlando). Todas as "
                "ferramentas são SÓ LEITURA: não existe aqui nada que escreva, por "
                "construção. Comece por urace_resumo para o panorama, ou urace_atencao "
                "para o que precisa de gente hoje."),
        })

    if metodo == "ping":
        return _resposta(ident, {})

    if metodo == "tools/list":
        return _resposta(ident, {"tools": _lista_ferramentas()})

    if metodo == "tools/call":
        nome = params.get("name")
        args = params.get("arguments") or {}
        if nome not in FERRAMENTAS:
            return _erro(ident, -32602, f"ferramenta desconhecida: {nome}")
        _, props, obrigatorios, fn = FERRAMENTAS[nome]
        faltando = [k for k in obrigatorios if k not in args]
        if faltando:
            return _erro(ident, -32602, f"faltou informar: {', '.join(faltando)}")
        extras = [k for k in args if k not in props]
        if extras:
            # Argumento que não existe costuma ser modelo inventando parâmetro. Recusar
            # é melhor que ignorar em silêncio e devolver um resultado que não responde.
            return _erro(ident, -32602, f"parâmetro que não existe: {', '.join(extras)}")
        try:
            dado = fn(con, **args)
        except ValueError as e:
            # Erro de uso vira resultado com isError, não erro de protocolo: o modelo
            # precisa LER o motivo para corrigir a chamada.
            return _resposta(ident, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception as e:                       # noqa: BLE001
            return _erro(ident, -32603, f"erro ao executar {nome}: {e}")
        return _resposta(ident, {"content": _texto(dado), "isError": False})

    return _erro(ident, -32601, f"método não suportado: {metodo}")


@r.post("")
async def rota_mcp(request: Request, u=Depends(auth.exige("VIEWER"))):
    """MCP sobre HTTP. Autentica com a mesma chave de API do painel
    (`Authorization: Bearer urk_…`), criada como **somente leitura**.

    As ferramentas rodam numa conexão aberta em `mode=ro`: o SQLite **recusa** qualquer
    escrita por ela. É o que sustenta a isenção da trava por método HTTP — sem isso,
    "só leitura" aqui seria só uma promessa minha."""
    try:
        corpo = json.loads(await request.body() or b"{}")
    except ValueError:
        return Response(json.dumps(_erro(None, -32700, "JSON inválido")),
                        media_type="application/json", status_code=400)

    lote = isinstance(corpo, list)
    mensagens = corpo if lote else [corpo]
    con = conectar_somente_leitura()
    try:
        respostas = [x for x in (tratar(m, con, u) for m in mensagens) if x is not None]
    finally:
        con.close()
    if not respostas:
        return Response(status_code=202)          # só notificações
    saida = respostas if lote else respostas[0]
    return Response(json.dumps(saida, ensure_ascii=False, default=str),
                    media_type="application/json")


@r.get("")
def rota_mcp_get(u=Depends(auth.exige("VIEWER"))):
    """Fluxo por SSE do servidor para o cliente: não há. Este servidor só responde ao que
    é perguntado — não envia nada por conta própria, e dizer isso é melhor que abrir um
    canal que nunca manda nada."""
    return Response(json.dumps({"ok": True, "transporte": "streamable-http (só POST)",
                                "servidor": NOME, "versao": VERSAO,
                                "ferramentas": len(FERRAMENTAS), "somente_leitura": True},
                               ensure_ascii=False),
                    media_type="application/json", status_code=200)
