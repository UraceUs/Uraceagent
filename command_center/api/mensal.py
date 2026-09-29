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

**Uma recorrência só** (dono, 29/09): antes de criar, o painel lê as recorrências que já
existem no QuickBooks para o cliente. Se houver uma ativa que o painel não conhece, criar é
recusado e a tela oferece **vincular** aquela ao card — a cobrança passa a ser a do
QuickBooks, e o valor do card passa a ser o dela. Nunca duas cobranças do mesmo mês.

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


SEM_FIM = "2099-12-01"


def _fim(inicio, meses):
    fim_m = inicio.month - 1 + meses - 1
    return date(inicio.year + fim_m // 12, fim_m % 12 + 1, 1)


def _recorrencias_qbo(con, c):
    """(id do cliente no QBO, recorrências dele no QBO marcadas com o vínculo no painel).
    Sem QuickBooks conectado, levanta 503: sem conferir, não se cria cobrança."""
    from command_center import providers
    qbo_id, _ = _cliente_qbo(con, c)
    if not qbo_id:
        return None, []
    try:
        lista = providers.chamar("quickbooks", "qbo_recorrencias", cliente_id=qbo_id)
    except providers.NaoConectado:
        raise HTTPException(503, "QuickBooks não está conectado: não dá para conferir se já existe recorrência.")
    ligadas = {x["qbo_id"]: x for x in todos(con, "SELECT id, client_id, qbo_id FROM monthly_recurring "
                                                   "WHERE qbo_id IS NOT NULL AND status='active'")}
    for x in lista:
        v = ligadas.get(str(x.get("id")))
        x["vinculada_id"] = v["id"] if v and v["client_id"] == c["id"] else None
        x["de_outro_cliente"] = bool(v and v["client_id"] != c["id"])
    return qbo_id, lista


def _soltas(lista):
    """Recorrências ativas no QuickBooks que o painel ainda não conhece — o risco de cobrar duas vezes."""
    return [x for x in lista if x.get("ativa") and not x.get("vinculada_id") and not x.get("de_outro_cliente")]


@r.get("/{cid}/mensal/qbo")
def ver_no_quickbooks(cid: int, con: sqlite3.Connection = Depends(get_db), u=Depends(auth.exige("MANAGER"))):
    """O que o QuickBooks já cobra deste cliente todo mês. A tela chama ao abrir a aba."""
    c = _cliente(con, cid)
    try:
        qbo_id, lista = _recorrencias_qbo(con, c)
    except HTTPException as e:
        return {"conectado": False, "erro": e.detail, "recorrencias": [], "soltas": 0}
    return {"conectado": True, "cliente_qbo": qbo_id, "recorrencias": lista, "soltas": len(_soltas(lista))}


class VincularIn(BaseModel):
    qbo_id: str


@r.post("/{cid}/mensal/vincular")
def vincular(cid: int, dados: VincularIn, request: Request, con: sqlite3.Connection = Depends(get_db),
             u=Depends(auth.exige("MANAGER"))):
    """Liga ao card a recorrência que já existe no QuickBooks, em vez de criar outra. A
    cobrança é a do QuickBooks; o valor e o item do card passam a ser os dela."""
    c = _cliente(con, cid)
    qbo_cliente, lista = _recorrencias_qbo(con, c)
    x = next((y for y in lista if str(y.get("id")) == str(dados.qbo_id)), None)
    if not x:
        raise HTTPException(404, "Essa recorrência não é deste cliente no QuickBooks.")
    if x["de_outro_cliente"]:
        raise HTTPException(409, "Essa recorrência já está vinculada ao card de outro cliente.")
    if x["vinculada_id"]:
        return {"ok": True, "id": x["vinculada_id"], "ja_estava": True}
    ativa_no_painel = um(con, "SELECT * FROM monthly_recurring WHERE client_id=? AND status='active'", (cid,))
    if ativa_no_painel:
        raise HTTPException(409, f"O card já tem uma recorrência ativa ({ativa_no_painel['start_on'][:7]} a "
                                 f"{ativa_no_painel['end_on'][:7]}). Uma só: confira qual das duas vale no QuickBooks.")
    try:
        inicio = date.fromisoformat((x.get("inicio") or "")[:10])
    except ValueError:
        inicio = date.today().replace(day=1)
    meses = int(x.get("ocorrencias") or 0)
    if x.get("fim"):
        fim = x["fim"][:10]
    elif meses:
        fim = _fim(inicio, meses).isoformat()
    else:
        fim = SEM_FIM
    linha = (x.get("linhas") or [{}])[0]
    valor = float(x.get("total") or linha.get("unitario") or 0)
    rid = inserir(con, "monthly_recurring", client_id=cid, qbo_id=str(x["id"]), name=x.get("nome"), amount=valor,
                  item_id=linha.get("item_id") or "", months=meses, start_on=inicio.isoformat(), end_on=fim,
                  email=x.get("email"), status="active", source="qbo",
                  result=json.dumps(x, ensure_ascii=False)[:4000], created_by=u["id"])
    antes = {"monthly_amount": c["monthly_amount"], "monthly_item_id": c["monthly_item_id"]}
    con.execute("UPDATE clients SET monthly_amount=?, monthly_item_id=COALESCE(?, monthly_item_id), updated_at=? WHERE id=?",
                (valor or c["monthly_amount"], linha.get("item_id"), agora(), cid))
    auditar(con, "client.monthly.link", f"user:{u['id']}", user_id=u["id"], entity_type="client", entity_id=cid,
            detail={"id": rid, "qbo_id": x["id"], "cliente_qbo": qbo_cliente, "valor": valor, "antes": antes},
            ip=auth._ip(request))
    con.commit()
    return {"ok": True, "id": rid, "valor": valor, "inicio": inicio.isoformat(), "fim": fim}


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
    fim = _fim(inicio, dados.meses)
    ja = um(con, """SELECT * FROM monthly_recurring WHERE client_id=? AND status='active'
                     AND start_on <= ? AND end_on >= ?""", (cid, fim.isoformat(), inicio.isoformat()))
    if ja:
        raise HTTPException(409, f"Já existe recorrência ativa de {ja['start_on'][:7]} a {ja['end_on'][:7]}: "
                                 "cobrar duas vezes, não.")
    qbo_id, origem = _cliente_qbo(con, c)
    if not qbo_id:
        raise HTTPException(400, "Não achei este cliente no QuickBooks (nem por invoice, nem pelo e-mail). "
                                 "Crie o cliente lá ou mande uma invoice antes.")
    # uma recorrência só: a que já existe no QuickBooks é vinculada, nunca duplicada
    _, no_qbo = _recorrencias_qbo(con, c)
    soltas = _soltas(no_qbo)
    if soltas:
        x = soltas[0]
        raise HTTPException(409, f"Este cliente JÁ tem cobrança recorrente no QuickBooks: “{x.get('nome') or x['id']}”, "
                                 f"${float(x.get('total') or 0):,.2f} desde {x.get('inicio') or '?'}. "
                                 "Vincule essa ao card em vez de criar outra.")
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
