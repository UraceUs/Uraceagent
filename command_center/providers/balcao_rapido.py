"""Balcão no celular, com uma mão (#180).

Dono, 09/10: *"o primeiro passo não vai ser ler o QR Code do cliente. O passo vai ser ler a
peça … escaneou a peça, identificou ali, isso o sistema faz sozinho … já abre um pop-up para
selecionar os pilotos que estão no dia … quando ele clicar no cliente, já registra aquela
peça"* e *"já sobe … no balcão, no Command Center, só que na seção de revisão para poder só
confirmar depois aquelas peças, mas eles não precisam ter acesso disso pelo celular"*.

**Mudou em 13/10 (#206).** Dono: *"quando você escaneia e joga para o cliente que está no dia, ele
já vai ali para aquele cliente ... Escaneou uma vez, já tem uma peça daquela ali na OS do cliente
... Escaneou, selecionou o cliente, já finaliza. Não tem essa de ter que confirmar depois."*

Agora a leitura com cliente vai **direto** para a OS do cliente naquele dia (`balcao.lancar` em modo
cobrar: estoque, invoice de peças do dia no QuickBooks). Só fica **pendente**, com o motivo dito na
tela, o que não pode ir direto — e nada se perde: código novo, piloto do site ainda sem card,
"decidir depois", peça sem preço ou sem item no QuickBooks, sem saldo na prateleira, card sem
cliente no QuickBooks, ou peça que o cliente tem guardada (usar a dele ou cobrar nova é o gerente).
O gerente resolve esses na Revisão do balcão.

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
    for x in todos(con, """SELECT s.client_id, COUNT(*) AS n FROM counter_scans s JOIN parts_invoices pi ON pi.id=s.parts_invoice_id
                            WHERE pi.service_date=? AND s.mode='cobrar' AND s.undone_at IS NULL GROUP BY s.client_id""", (data,)):
        pend[f"c:{x['client_id']}"] = pend.get(f"c:{x['client_id']}", 0) + x["n"]     # #206: as que já foram para a OS
    for p in out:
        p["pecas"] = pend.get(p["chave"], 0)
    return sorted(out, key=lambda p: p["nome"].lower())


def _publica(con, p):
    it = um(con, "SELECT id, name FROM stock_items WHERE id=?", (p["item_id"],)) if p["item_id"] else None
    return {**dict(p), "peca": it["name"] if it else None}


def registrar(con, codigo, data, client_id=None, pilot_id=None, por=None, local=None):
    """Um toque no piloto: com card e peça conhecida, vai direto para a OS do cliente no dia (#206).
    O que não pode ir direto fica pendente, com o motivo. Devolve a leitura com `direto` e `motivo`."""
    cod = b._codigo(codigo)                       # QR de cliente aqui é erro: o passo é a peça
    item = um(con, """SELECT i.id FROM stock_barcodes bc JOIN stock_items i ON i.id=bc.item_id
                       WHERE bc.code=? AND i.active=1""", (cod,))
    if not item:
        from command_center.providers import etiquetas
        iid = etiquetas.item_do_qr(con, cod, por)     # etiqueta de prateleira (#187)
        item = {"id": iid} if iid else None
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
    motivo = None
    if not item:
        motivo = "código novo: o gerente diz que peça é"
    elif not client_id:
        motivo = "piloto ainda sem card: o gerente escolhe o cliente" if pilot_id else "decidir depois: o gerente escolhe o cliente"
    else:
        con.execute("SAVEPOINT balcao_direto")
        try:
            s = b.lancar(con, client_id, item["id"], "cobrar", qty=1, local=local or estoque.SEDE, por=por, codigo=cod, data=data)
        except (b.ErroBalcao, estoque.ErroEstoque) as e:
            con.execute("ROLLBACK TO balcao_direto")
            con.execute("RELEASE balcao_direto")
            motivo = str(e)[:300]
        else:
            con.execute("RELEASE balcao_direto")
            it = um(con, "SELECT name FROM stock_items WHERE id=?", (item["id"],))
            return {"id": s["id"], "tipo": "lancada", "direto": True, "motivo": None, "code": cod, "item_id": item["id"],
                    "peca": it["name"], "client_id": client_id, "pilot_id": pilot_id, "pilot_name": nome,
                    "service_date": data, "parts_invoice_id": s["parts_invoice_id"]}
    cur = con.execute("""INSERT INTO counter_pending (code, item_id, client_id, pilot_id, pilot_name, service_date, by_user_id, motivo)
                         VALUES (?,?,?,?,?,?,?,?)""", (cod, item["id"] if item else None, client_id, pilot_id, nome, data, por, motivo))
    return {**_publica(con, um(con, "SELECT * FROM counter_pending WHERE id=?", (cur.lastrowid,))), "tipo": "pendente", "direto": False}


def desfazer_lancada(con, scan_id, por, gerente=False):
    """#206: o celular desfaz a peça que foi direto para a OS — a de quem leu (o gerente, qualquer uma),
    enquanto a invoice não foi enviada nem paga (as regras de `balcao.desfazer`)."""
    s = um(con, "SELECT * FROM counter_scans WHERE id=?", (scan_id,))
    if not s:
        raise LookupError("leitura não existe")
    if not gerente and s["by_user_id"] != por:
        raise ErroRapido("só quem leu desfaz por aqui")
    return b.desfazer(con, scan_id, por)


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


def minhas(con, data, por, limite=8):
    """As últimas leituras de quem está lendo, naquele dia: as que foram para a OS e as pendentes."""
    pend = [{**_publica(con, p), "tipo": "pendente"} for p in todos(con, """SELECT * FROM counter_pending WHERE service_date=?
                                    AND by_user_id IS ? AND status='pendente' ORDER BY id DESC LIMIT ?""", (data, por, limite))]
    lanc = [{"id": s["id"], "tipo": "lancada", "code": s["code"], "peca": s["peca"], "client_id": s["client_id"],
             "pilot_name": s["cliente"], "at": s["at"], "motivo": None}
            for s in todos(con, """SELECT s.id, s.code, s.client_id, s.at, i.name AS peca,
                                          COALESCE(c.pilot_name, c.name) AS cliente
                                     FROM counter_scans s JOIN parts_invoices pi ON pi.id=s.parts_invoice_id
                                     JOIN stock_items i ON i.id=s.item_id JOIN clients c ON c.id=s.client_id
                                    WHERE pi.service_date=? AND s.by_user_id IS ? AND s.mode='cobrar' AND s.undone_at IS NULL
                                      AND pi.status='aberta' AND pi.paid_at IS NULL
                                    ORDER BY s.id DESC LIMIT ?""", (data, por, limite))]
    return sorted(pend + lanc, key=lambda x: x.get("at") or "", reverse=True)[:limite]


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
                         "do_cliente": estoque.saldo(con, it["id"], client_id=p["client_id"]) if p["client_id"] else 0,
                         # #206: o que a URACE tem na prateleira — sem saldo, "Cobrar" é recusado
                         "nosso": estoque.saldo(con, it["id"], client_id=None)}
        itens.append(x)
    return {"itens": itens, "total": total, "limit": limit, "offset": offset}


def confirmar(con, pid, modo, por, client_id=None, item_id=None, confirmado=False, local=None):
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
    scan = b.lancar(con, cid, iid, modo, qty=p["qty"], local=local or estoque.SEDE, por=por, codigo=p["code"],
                    confirmado=confirmado, data=p["service_date"])   # #206: o gerente diz de onde a peça saiu
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


# ------------------------------------------------------------------ #189: qualquer dia, auditoria, cliente fora da lista
def buscar_clientes(con, q, limite=10):
    """Quem não está no calendário do dia: busca pelo nome, e só o nome volta (sem contato)."""
    t = " ".join((q or "").split())
    if len(t) < 2:
        return []
    padrao = f"%{t.lower()}%"
    out = []
    for c in todos(con, """SELECT id, name, pilot_name FROM clients
                            WHERE status!='INACTIVE' AND (lower(name) LIKE ? OR lower(COALESCE(pilot_name,'')) LIKE ?)
                            ORDER BY (lower(COALESCE(pilot_name, name)) LIKE ?) DESC, COALESCE(pilot_name, name) LIMIT ?""",
                   (padrao, padrao, f"{t.lower()}%", limite)):
        nome = _nome(c)
        resp = (c["name"] or "").strip()
        out.append({"client_id": c["id"], "nome": nome, "responsavel": resp if resp and resp != nome else None})
    return out


def _dia_fl(iso_utc):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except (AttributeError, ValueError):
        return None


def auditoria(con, data):
    """Tudo o que foi lançado para aquela data: no celular (pendente, confirmada, descartada) e no
    balcão do computador (lançada ou desfeita), com quem, quando, a peça e para quem."""
    from datetime import date, timedelta
    itens, do_celular = [], set()
    for p in todos(con, """SELECT cp.*, u.name AS por, r.name AS revisor, i.name AS peca, COALESCE(c.pilot_name, c.name) AS cliente
                             FROM counter_pending cp LEFT JOIN users u ON u.id=cp.by_user_id
                             LEFT JOIN users r ON r.id=cp.reviewed_by LEFT JOIN stock_items i ON i.id=cp.item_id
                             LEFT JOIN clients c ON c.id=cp.client_id
                            WHERE cp.service_date=?""", (data,)):
        if p["scan_id"]:
            do_celular.add(p["scan_id"])
        itens.append({"origem": "celular", "id": p["id"], "at": p["at"], "por": p["por"], "peca": p["peca"], "codigo": p["code"],
                      "para": p["cliente"] or p["pilot_name"], "qtd": p["qty"], "situacao": p["status"],
                      "revisado_por": p["revisor"], "revisado_em": p["reviewed_at"], "modo": p["mode"]})
    d = date.fromisoformat(data)
    de, ate = (d - timedelta(days=1)).isoformat(), (d + timedelta(days=2)).isoformat()
    for s in todos(con, """SELECT s.*, u.name AS por, x.name AS desfez, i.name AS peca, COALESCE(c.pilot_name, c.name) AS cliente,
                                  pi.service_date
                             FROM counter_scans s LEFT JOIN users u ON u.id=s.by_user_id LEFT JOIN users x ON x.id=s.undone_by
                             LEFT JOIN stock_items i ON i.id=s.item_id LEFT JOIN clients c ON c.id=s.client_id
                             LEFT JOIN parts_invoices pi ON pi.id=s.parts_invoice_id
                            WHERE pi.service_date=? OR (s.parts_invoice_id IS NULL AND s.at>=? AND s.at<?)""", (data, de, ate)):
        if not s["service_date"] and _dia_fl(s["at"]) != data:
            continue
        if s["id"] in do_celular:
            continue                                      # já está na linha do celular, como confirmada
        itens.append({"origem": "balcão", "id": s["id"], "at": s["at"], "por": s["por"], "peca": s["peca"], "codigo": s["code"],
                      "para": s["cliente"], "qtd": s["qty"], "situacao": "desfeita" if s["undone_at"] else "lançada",
                      "revisado_por": s["desfez"], "revisado_em": s["undone_at"], "modo": s["mode"]})
    itens.sort(key=lambda x: x["at"] or "")
    pessoas = sorted({x["por"] for x in itens if x["por"]})
    return {"data": data, "itens": itens, "total": len(itens), "pessoas": pessoas}
