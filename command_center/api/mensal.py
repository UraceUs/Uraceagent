"""Mensalidade do cliente: o valor combinado e a recorrência no QuickBooks.

Dono, 29/09, no card do Enzo Kurian: *"eu preciso que o valor seja um campo alterável…
pode ser às vezes um deal diferente… e conseguir enviar a invoice, a invoice fica ali salva
para poder enviar todo dia primeiro. E seria interessante se o Command Center já deixasse
como invoice recorrente no QuickBooks. Padrão seis meses, podendo ser personalizado, 12
meses e 6 meses."*

Duas coisas, e a ordem importa:

1. **O combinado** — valor mensal e item do catálogo, gravados no cliente. É o que a invoice
   do dia 1 usa (a IA recebe esse valor e ele manda sobre a Rate Card).
2. **A recorrência no QuickBooks** — criada a partir do combinado, por 6, 12 ou N meses.
   Enquanto ela estiver ativa, o dia 1 do painel **não** monta outra invoice: seria cobrar
   o cliente duas vezes.

Tudo aqui é **gerente**: é dinheiro, e o mecânico nem vê o valor da mensalidade hoje.
"""
import json
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from command_center.api import auth
from command_center.db import agora, auditar, get_db, inserir, todos, um

r = APIRouter(prefix="/ops/api/clients", tags=["mensalidade"])

OPCOES_MESES = (6, 12)          # os dois botões; "personalizado" é qualquer outro de 1 a 36
PADRAO_MESES = 6


def proximo_dia_1(hoje=None):
    hoje = hoje or date.today()
    return date(hoje.year + (hoje.month == 12), hoje.month % 12 + 1, 1)


def recorrencia_ativa(con, client_id, mes):
    """A recorrência que cobre o mês `AAAA-MM` (ou None). É o que impede cobrar duas vezes."""
    dia = f"{mes}-01"
    return um(con, """SELECT * FROM monthly_recurring WHERE client_id=? AND status='active'
                       AND start_on <= ? AND end_on >= ? ORDER BY id DESC LIMIT 1""", (client_id, dia, dia))


def _cliente(con, cid):
    c = um(con, "SELECT * FROM clients WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Client not found.")
    return c


def _cliente_qbo(con, c):
    """Id do cliente no QuickBooks: o da última invoice dele; senão, busca pelo e-mail."""
    inv = um(con, "SELECT customer_ref FROM invoices WHERE client_id=? AND customer_ref IS NOT NULL "
                  "ORDER BY issued_on DESC LIMIT 1", (c["id"],))
    if inv:
        return inv["customer_ref"], "última invoice"
    from command_center import providers
    for email in (c["email"], c.get("email_alt")):
        if not email:
            continue
        try:
            achados = providers.chamar("quickbooks", "qbo_clientes_buscar", texto=email)
        except providers.NaoConectado:
            raise HTTPException(503, "QuickBooks não está conectado.")
        exatos = [x for x in achados if (x.get("email") or "") == email.lower()]
        if len(exatos) == 1:
            return exatos[0]["id"], f"e-mail {email}"
    return None, None


@r.get("/{cid}/mensal")
def ver(cid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    c = _cliente(con, cid)
    item = um(con, "SELECT id, name, price FROM qbo_items WHERE id=?", (c["monthly_item_id"],)) if c["monthly_item_id"] else None
    itens = todos(con, """SELECT id, name, full_name, price FROM qbo_items WHERE active=1
                           AND (LOWER(COALESCE(full_name,name)) LIKE '%academy%' OR LOWER(name) LIKE '%monthly%'
                                OR LOWER(name) LIKE '%mensal%' OR LOWER(name) LIKE '%training%')
                           ORDER BY name LIMIT 60""")
    return {"monthly_plan": c["monthly_plan"], "monthly_note": c["monthly_note"],
            "monthly_amount": c["monthly_amount"], "monthly_item_id": c["monthly_item_id"], "item": item,
            "itens": itens, "email": c["email"],
            "opcoes_meses": list(OPCOES_MESES), "padrao_meses": PADRAO_MESES,
            "proximo_inicio": proximo_dia_1().isoformat(),
            "recorrencias": todos(con, """SELECT m.*, us.name AS criado_por FROM monthly_recurring m
                                           LEFT JOIN users us ON us.id=m.created_by
                                          WHERE m.client_id=? ORDER BY m.id DESC""", (cid,))}


class CombinadoIn(BaseModel):
    model_config = {"extra": "forbid"}
    monthly_amount: float | None = None
    monthly_item_id: str | None = None


@r.patch("/{cid}/mensal")
def combinar(cid: int, dados: CombinadoIn, request: Request, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("MANAGER"))):
    """O valor que ESTE cliente paga por mês, e o item do QuickBooks que vai na invoice."""
    c = _cliente(con, cid)
    campos = dados.model_dump(exclude_unset=True)
    if "monthly_amount" in campos and campos["monthly_amount"] is not None:
        if not 0 < campos["monthly_amount"] <= 100000:
            raise HTTPException(400, "Valor mensal fora da faixa.")
        campos["monthly_amount"] = round(campos["monthly_amount"], 2)
    if campos.get("monthly_item_id"):
        if not um(con, "SELECT 1 AS x FROM qbo_items WHERE id=? AND active=1", (campos["monthly_item_id"],)):
            raise HTTPException(400, "Esse item não está ativo no catálogo do QuickBooks.")
    if not campos:
        return {"ok": True}
    antes = {k: c[k] for k in campos}
    con.execute(f"UPDATE clients SET {', '.join(f'{k}=?' for k in campos)}, updated_at=? WHERE id=?",
                (*campos.values(), agora(), cid))
    auditar(con, "client.monthly.deal", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=cid,
            detail={"antes": antes, "depois": campos}, ip=auth._ip(request))
    con.commit()
    return {"ok": True, **campos}


class RecorrenciaIn(BaseModel):
    meses: int = PADRAO_MESES
    inicio: str | None = None          # AAAA-MM-01; padrão: o próximo dia 1
    email: str | None = None
    memo: str | None = None


@r.post("/{cid}/mensal/recorrencia")
def criar_recorrencia(cid: int, dados: RecorrenciaIn, request: Request, con: sqlite3.Connection = Depends(get_db),
                      u=Depends(auth.exige("MANAGER"))):
    """Cria a invoice recorrente no QuickBooks a partir do combinado. O clique do gerente é
    a aprovação (a tela pergunta antes). O resultado — inclusive falha — fica registrado."""
    from command_center import providers
    c = _cliente(con, cid)
    if not c["monthly_amount"] or not c["monthly_item_id"]:
        raise HTTPException(400, "Salve antes o valor mensal e o item do QuickBooks.")
    if not 1 <= dados.meses <= 36:
        raise HTTPException(400, "A recorrência vai de 1 a 36 meses.")
    try:
        inicio = date.fromisoformat((dados.inicio or proximo_dia_1().isoformat())[:10])
    except ValueError:
        raise HTTPException(400, "Início inválido.")
    if inicio.day != 1 or inicio < date.today().replace(day=1):
        raise HTTPException(400, "A mensalidade começa num dia 1, deste mês em diante.")
    fim_m = inicio.month - 1 + dados.meses - 1
    fim = date(inicio.year + fim_m // 12, fim_m % 12 + 1, 1)
    ja = um(con, """SELECT * FROM monthly_recurring WHERE client_id=? AND status='active'
                     AND start_on <= ? AND end_on >= ?""", (cid, fim.isoformat(), inicio.isoformat()))
    if ja:
        raise HTTPException(409, f"Já existe recorrência ativa de {ja['start_on'][:7]} a {ja['end_on'][:7]}: "
                                 "cobrar duas vezes, não.")
    qbo_id, origem = _cliente_qbo(con, c)
    if not qbo_id:
        raise HTTPException(400, "Não achei este cliente no QuickBooks (nem por invoice, nem pelo e-mail). "
                                 "Crie o cliente lá ou mande uma invoice antes.")
    item = um(con, "SELECT id, name FROM qbo_items WHERE id=?", (c["monthly_item_id"],))
    piloto = c["pilot_name"] or c["name"]
    memo = dados.memo or f"{item['name'] if item else 'Academy'} | {piloto} | mensalidade"
    email = (dados.email or c["email"] or "").strip() or None
    args = dict(cliente_id=qbo_id, meses=dados.meses, inicio=inicio.isoformat(), email=email, memo=memo,
                nome=f"Mensalidade {piloto} {inicio:%Y-%m}",
                linhas=[{"item_id": c["monthly_item_id"], "quantidade": 1, "unitario": float(c["monthly_amount"]),
                         "descricao": f"{c['monthly_plan'] or 'Academy'} — {piloto}"}])
    try:
        res = providers.chamar("quickbooks", "qbo_criar_recorrencia", **args)
        status = "active" if res.get("aplicado") else "simulated"
    except providers.NaoConectado:
        raise HTTPException(503, "QuickBooks não está conectado.")
    except Exception as e:                                        # noqa: BLE001 - registra e mostra
        res, status = {"erro": f"{type(e).__name__}: {str(e)[:400]}"}, "failed"
    rid = inserir(con, "monthly_recurring", client_id=cid, qbo_id=res.get("id"), name=args["nome"],
                  amount=float(c["monthly_amount"]), item_id=c["monthly_item_id"], months=dados.meses,
                  start_on=inicio.isoformat(), end_on=fim.isoformat(), email=email, status=status,
                  result=json.dumps(res, ensure_ascii=False)[:4000], created_by=u["id"])
    auditar(con, "client.monthly.recurring", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=cid,
            detail={"id": rid, "status": status, "cliente_qbo": qbo_id, "origem_cliente": origem,
                    "meses": dados.meses, "inicio": inicio.isoformat(), "valor": c["monthly_amount"]},
            ip=auth._ip(request))
    con.commit()
    if status == "failed":
        raise HTTPException(502, f"O QuickBooks recusou: {res['erro']}")
    return {"id": rid, "status": status, "inicio": inicio.isoformat(), "fim": fim.isoformat(), "meses": dados.meses,
            "qbo_id": res.get("id"), "aviso": res.get("teria_feito") if status == "simulated" else None}
