"""Balcão no celular, com uma mão (#180).

Dono, 09/10: *"o primeiro passo não vai ser ler o QR Code do cliente. O passo vai ser ler a
peça … escaneou a peça, identificou ali, isso o sistema faz sozinho … já abre um pop-up para
selecionar os pilotos que estão no dia … quando ele clicar no cliente, já registra aquela
peça"* e *"já sobe … no balcão, no Command Center, só que na seção de revisão para poder só
confirmar depois aquelas peças, mas eles não precisam ter acesso disso pelo celular"*.

Por isso a leitura do celular NÃO mexe em estoque nem em invoice: ela entra em
`counter_pending`. O gerente confirma na Revisão do balcão (aí sim `balcao.lancar`, com as
regras de sempre: peça do cliente, preço, item do QuickBooks, invoice de peças daquele dia) ou
descarta. Código que o sistema ainda não conhece também entra: o gerente diz que peça é.

Os pilotos do dia saem das mesmas fontes do "Meu dia" (#92): sessões do site, corridas e
serviços daquela data. Sem valor e sem contato do cliente — só o nome no botão.
"""
from command_center.db import agora, atualizar, todos, um
from command_center.providers import balcao as b, estoque


class ErroRapido(ValueError):
    """Regra violada. A mensagem é para a tela."""


def _nome(c):
    return (c.get("pilot_name") or c.get("name") or "").strip()


def pilotos_do_dia(con, data):
    """Os botões da tela: um por piloto que tem algo marcado na data. Card primeiro (client_id);
    piloto do site ainda sem card entra pelo `pilot_id`, e a revisão liga depois."""
    vistos, out = {}, []

    def junta(chave, client_id, pilot_id, nome, origem):
        if not nome:
            return
        if chave in vistos:
            if origem not in vistos[chave]["origens"]:
                vistos[chave]["origens"].append(origem)
            return
        p = {"chave": chave, "client_id": client_id, "pilot_id": pilot_id, "nome": nome, "origens": [origem]}
        vistos[chave] = p
        out.append(p)

    for s in todos(con, """SELECT b.id, p.id AS pilot_id, p.name AS piloto, p.client_id, c.name, c.pilot_name
                             FROM bookings b JOIN portal_pilots p ON p.id=b.pilot_id
                             LEFT JOIN clients c ON c.id=p.client_id
                            WHERE b.date=? AND b.status IN ('confirmada','pendente') ORDER BY b.period, b.id""", (data,)):
        if s["client_id"]:
            junta(f"c:{s['client_id']}", s["client_id"], s["pilot_id"], _nome(s) or s["piloto"], "sessão")
        else:
            junta(f"p:{s['pilot_id']}", None, s["pilot_id"], s["piloto"], "sessão")
    for r in todos(con, """SELECT i.client_id, c.name, c.pilot_name, r.name AS corrida FROM race_invites i
                             JOIN races r ON r.id=i.race_id JOIN clients c ON c.id=i.client_id
                            WHERE r.active=1 AND r.date_start<=? AND COALESCE(r.date_end, r.date_start)>=?
                              AND i.status IN ('invited','confirmed') ORDER BY r.date_start, c.name""", (data, data)):
        junta(f"c:{r['client_id']}", r["client_id"], None, _nome(r), "corrida")
    for t in todos(con, """SELECT t.client_id, c.name, c.pilot_name FROM tasks t JOIN clients c ON c.id=t.client_id
                            WHERE substr(t.due_on,1,10)=? ORDER BY c.name""", (data,)):
        junta(f"c:{t['client_id']}", t["client_id"], None, _nome(t), "serviço")
    pend = {}
    for x in todos(con, """SELECT client_id, pilot_id, COUNT(*) AS n FROM counter_pending
                            WHERE service_date=? AND status='pendente' GROUP BY client_id, pilot_id""", (data,)):
        chave = f"c:{x['client_id']}" if x["client_id"] else (f"p:{x['pilot_id']}" if x["pilot_id"] else None)
        if chave:
            pend[chave] = pend.get(chave, 0) + x["n"]
    for p in out:
        p["pecas"] = pend.get(p["chave"], 0)
    return sorted(out, key=lambda p: p["nome"].lower())


def _publica(con, p):
    it = um(con, "SELECT id, name FROM stock_items WHERE id=?", (p["item_id"],)) if p["item_id"] else None
    return {**dict(p), "peca": it["name"] if it else None}


def registrar(con, codigo, data, client_id=None, pilot_id=None, por=None):
    """Um toque no piloto: a leitura entra pendente. Nunca cobra, nunca mexe no estoque."""
    cod = b._codigo(codigo)                       # QR de cliente aqui é erro: o passo é a peça
    item = um(con, """SELECT i.id FROM stock_barcodes bc JOIN stock_items i ON i.id=bc.item_id
                       WHERE bc.code=? AND i.active=1""", (cod,))
    nome = None
    if pilot_id:
        pp = um(con, "SELECT id, name, client_id FROM portal_pilots WHERE id=?", (pilot_id,))
        if not pp:
            raise ErroRapido("piloto não encontrado")
        client_id = client_id or pp["client_id"]
        if client_id and pp["client_id"] and int(client_id) != int(pp["client_id"]):
            raise ErroRapido("o piloto e o card não batem")    # nunca a peça de um no card de outro
        nome = pp["name"]
    if client_id:
        c = um(con, "SELECT id, name, pilot_name FROM clients WHERE id=?", (client_id,))
        if not c:
            raise ErroRapido("cliente não encontrado")
        nome = _nome(c) or nome
    cur = con.execute("""INSERT INTO counter_pending (code, item_id, client_id, pilot_id, pilot_name, service_date, by_user_id)
                         VALUES (?,?,?,?,?,?,?)""", (cod, item["id"] if item else None, client_id, pilot_id, nome, data, por))
    return _publica(con, um(con, "SELECT * FROM counter_pending WHERE id=?", (cur.lastrowid,)))


def desfazer(con, pid, por):
    """O "desfazer" da tela: só a leitura pendente, e só de quem leu."""
    p = um(con, "SELECT * FROM counter_pending WHERE id=?", (pid,))
    if not p:
        raise LookupError("leitura não existe")
    if p["status"] != "pendente":
        raise ErroRapido("esta leitura já foi revisada")
    if por is not None and p["by_user_id"] != por:
        raise ErroRapido("só quem leu desfaz por aqui")
    con.execute("DELETE FROM counter_pending WHERE id=? AND status='pendente'", (pid,))


def minhas(con, data, por, limite=5):
    return [_publica(con, p) for p in todos(con, """SELECT * FROM counter_pending WHERE service_date=? AND by_user_id IS ?
                                                     AND status='pendente' ORDER BY id DESC LIMIT ?""", (data, por, limite))]


# ------------------------------------------------------------------ a revisão (Command Center)
def revisao(con, limit=50, offset=0):
    total = um(con, "SELECT COUNT(*) AS n FROM counter_pending WHERE status='pendente'")["n"]
    itens = []
    for p in todos(con, """SELECT cp.*, u.name AS por FROM counter_pending cp LEFT JOIN users u ON u.id=cp.by_user_id
                            WHERE cp.status='pendente' ORDER BY cp.service_date, cp.id LIMIT ? OFFSET ?""", (limit, offset)):
        x = _publica(con, p)
        if p["item_id"]:
            it = estoque.item(con, p["item_id"])
            x["item"] = {"id": it["id"], "name": it["name"], "price": it["price"], "qbo_item_id": it["qbo_item_id"],
                         "do_cliente": estoque.saldo(con, it["id"], client_id=p["client_id"]) if p["client_id"] else 0}
        itens.append(x)
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


def confirmar(con, pid, modo, por, client_id=None, item_id=None, confirmado=False):
    """Vira uma leitura do balcão de verdade (estoque, cobrança, invoice do dia da leitura).
    Devolve a linha de `counter_scans`; quem chama grava e leva a invoice ao QuickBooks."""
    p = um(con, "SELECT * FROM counter_pending WHERE id=?", (pid,))
    if not p:
        raise LookupError("leitura não existe")
    if p["status"] != "pendente":
        raise ErroRapido(f"esta leitura já está {p['status']}")
    cid = client_id or p["client_id"]
    if not cid:
        raise ErroRapido("escolha o cliente desta peça")
    if p["pilot_id"] and p["client_id"] is None and client_id:
        pp = um(con, "SELECT client_id FROM portal_pilots WHERE id=?", (p["pilot_id"],))
        if pp and pp["client_id"] and int(pp["client_id"]) != int(client_id):
            raise ErroRapido("este piloto já é de outro card")
    iid = item_id or p["item_id"]
    if not iid:                                    # o código pode ter sido cadastrado depois da leitura
        achado = um(con, """SELECT i.id FROM stock_barcodes bc JOIN stock_items i ON i.id=bc.item_id
                             WHERE bc.code=? AND i.active=1""", (p["code"],))
        iid = achado["id"] if achado else None
    if not iid:
        raise ErroRapido("código novo: diga que peça é antes de confirmar")
    scan = b.lancar(con, cid, iid, modo, qty=p["qty"], por=por, codigo=p["code"], confirmado=confirmado,
                    data=p["service_date"])
    atualizar(con, "counter_pending", pid, status="confirmada", mode=modo, client_id=cid, item_id=iid, scan_id=scan["id"],
              reviewed_by=por, reviewed_at=agora())
    return scan


def descartar(con, pid, por, nota=None):
    p = um(con, "SELECT * FROM counter_pending WHERE id=?", (pid,))
    if not p:
        raise LookupError("leitura não existe")
    if p["status"] != "pendente":
        raise ErroRapido(f"esta leitura já está {p['status']}")
    atualizar(con, "counter_pending", pid, status="descartada", reviewed_by=por, reviewed_at=agora(),
              review_note=(nota or "")[:300] or None)
