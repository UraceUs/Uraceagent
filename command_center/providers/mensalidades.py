"""Mensalidade agendada: todos os meses criados de uma vez, e cada um enviado no dia 1 às 01:00 (#63).

Dono, 01/10: *"sempre que colocar criar invoice recorrente, já crie todos os meses, a situação
é só enviado ou a enviar e a data que vai ser enviada, e isso tem que ser feito... uma hora da
manhã, naquele dia já enviar essa invoice."*

- **O clique do gerente é a aprovação** dos meses que ele vê na tela (a tela pergunta antes,
  com a lista). Daí em diante o painel cria e envia cada invoice pelo QuickBooks no horário,
  sem pedir de novo — é o que o dono pediu.
- **Uma mensalidade por mês e por cliente**, nunca duas: antes de enviar, o painel confere se o
  mês já tem invoice de mensalidade (pelo memo "[October, 2026]", pelo item Academy da linha);
  se tem, a linha fica "enviada" com o número da que já existe.
- O mês que já começou sai no primeiro ciclo depois de criado (o laço roda a cada 15 min).
- Falha fica "falhou", com o motivo, e é tentada de novo até 3 vezes. Cancelar não apaga.
"""
import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from command_center.db import agora, atualizar, auditar, inserir, todos, um

FUSO = ZoneInfo("America/New_York")
HORA_ENVIO = "01:00"
MAX_TENTATIVAS = 3
MESES_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December")
ACADEMY = re.compile(r"academy|monthly|training program|mensal", re.I)


class ErroMensalidade(ValueError):
    pass


def agora_fl():
    return datetime.now(FUSO)


def soma_mes(d, n):
    t = d.year * 12 + d.month - 1 + n
    return date(t // 12, t % 12 + 1, 1)


def memo_do_mes(mes):
    a, m = [int(x) for x in mes.split("-")]
    return f"Urace Academy Training Program [{MESES_EN[m - 1]}, {a}]"


def invoice_do_mes(con, client_id, mes):
    """Invoice de mensalidade que já existe para o cliente naquele mês (espelho do QuickBooks):
    pelo memo "[Month, AAAA]", ou emitida no mês com item/descrição de Academy."""
    nome_mes = MESES_EN[int(mes[5:7]) - 1]
    for i in todos(con, "SELECT * FROM invoices WHERE client_id=? ORDER BY issued_on DESC", (client_id,)):
        memo = i.get("memo") or ""
        if re.search(rf"\[\s*{nome_mes}[,\s]+{mes[:4]}\s*\]", memo, re.I):
            return i
        if (i.get("issued_on") or "")[:7] == mes:
            linhas = todos(con, "SELECT item_name, description FROM invoice_lines WHERE invoice_id=?", (i["id"],))
            if ACADEMY.search(memo) or any(ACADEMY.search(f"{x['item_name'] or ''} {x['description'] or ''}") for x in linhas):
                return i
    return None


def agendar(con, por, client_id, recurring_id, inicio, meses, amount, item_id, descricao, email):
    """Cria as linhas dos meses. Mês que já tem invoice nasce "enviada" (com o número dela)."""
    saida = []
    for k in range(meses):
        d = soma_mes(inicio, k)
        mes = d.strftime("%Y-%m")
        if um(con, "SELECT 1 AS x FROM monthly_invoices WHERE client_id=? AND month=? AND status<>'cancelada'", (client_id, mes)):
            raise ErroMensalidade(f"{mes} já está agendado para este cliente: cobrar duas vezes, não.")
        ja = invoice_do_mes(con, client_id, mes)
        mid = inserir(con, "monthly_invoices", recurring_id=recurring_id, client_id=client_id, month=mes, amount=amount,
                      item_id=item_id, description=descricao, email=email, send_at=f"{d.isoformat()} {HORA_ENVIO}",
                      status="enviada" if ja else "a_enviar", doc_number=ja["doc_number"] if ja else None,
                      note="já existia no QuickBooks" if ja else None, created_by=por)
        saida.append(mid)
    return saida


def do_cliente(con, client_id):
    return [dict(x) for x in todos(con, "SELECT * FROM monthly_invoices WHERE client_id=? ORDER BY month, id", (client_id,))]


def cancelar(con, por, mid, client_id):
    m = um(con, "SELECT * FROM monthly_invoices WHERE id=? AND client_id=?", (mid, client_id))
    if not m:
        raise ErroMensalidade("mês não encontrado")
    if m["status"] not in ("a_enviar", "falhou"):
        raise ErroMensalidade(f"esse mês já está {m['status']}")
    atualizar(con, "monthly_invoices", mid, status="cancelada", cancelled_by=por, updated_at=agora())


def _cliente_qbo(con, client_id):
    from command_center.api.mensal import _cliente_qbo as achar
    c = um(con, "SELECT * FROM clients WHERE id=?", (client_id,))
    return achar(con, c)[0] if c else None


def _aplicando(fn, **kw):
    """Envio aprovado pelo gerente ao agendar: APLICAR ligado só nesta chamada."""
    anterior = os.environ.get("APLICAR")
    os.environ["APLICAR"] = "1"
    try:
        return fn(**kw)
    finally:
        if anterior is None:
            os.environ.pop("APLICAR", None)
        else:
            os.environ["APLICAR"] = anterior


def devidas(con, agora_local=None):
    agora_local = agora_local or agora_fl()
    chave = agora_local.strftime("%Y-%m-%d %H:%M")
    return todos(con, """SELECT * FROM monthly_invoices WHERE send_at<=? AND
                           (status='a_enviar' OR (status='falhou' AND attempts<?)) ORDER BY send_at, id""",
                 (chave, MAX_TENTATIVAS))


def enviar_devidas(con, agora_local=None, enviar=None):
    """Chamado pelo laço do autosync. Cria e envia, pelo QuickBooks, cada mensalidade cujo horário
    chegou. `enviar` é a função de envio (o teste troca); o padrão é a do QuickBooks."""
    from command_center import providers
    if enviar is None:
        def enviar(**kw):
            return _aplicando(providers.modulo("quickbooks").qbo_criar_e_enviar_invoice, **kw)
    feitas = []
    for m in devidas(con, agora_local):
        ja = invoice_do_mes(con, m["client_id"], m["month"])
        if ja:
            atualizar(con, "monthly_invoices", m["id"], status="enviada", doc_number=ja["doc_number"],
                      note="já existia no QuickBooks", updated_at=agora())
            feitas.append((m["id"], "já existia"))
            continue
        qbo = _cliente_qbo(con, m["client_id"])
        try:
            if not qbo:
                raise ErroMensalidade("cliente não encontrado no QuickBooks")
            dia = m["send_at"][:10]
            res = enviar(cliente_id=qbo, linhas=[{"item_id": m["item_id"], "quantidade": 1, "unitario": float(m["amount"]),
                                                  "descricao": m["description"] or "Academy"}],
                         vence_em=dia, memo=memo_do_mes(m["month"]), email=m["email"])
            if not res or res.get("aplicado") is False:
                raise ErroMensalidade("o QuickBooks não criou a invoice (simulação)")
            atualizar(con, "monthly_invoices", m["id"], status="enviada", qbo_id=str(res.get("id") or ""),
                      doc_number=res.get("numero"), sent_at=agora(), error=None, attempts=m["attempts"] + 1,
                      note=None if res.get("enviado", True) else (res.get("aviso") or "criada, sem envio"), updated_at=agora())
            auditar(con, "client.monthly.sent", "system", entity_type="client", entity_id=m["client_id"],
                    detail={"mes": m["month"], "invoice": res.get("numero"), "valor": m["amount"]})
            feitas.append((m["id"], "enviada"))
        except Exception as e:                                # noqa: BLE001 - registra e tenta de novo
            atualizar(con, "monthly_invoices", m["id"], status="falhou", error=f"{type(e).__name__}: {str(e)[:300]}",
                      attempts=m["attempts"] + 1, updated_at=agora())
            feitas.append((m["id"], "falhou"))
    return feitas

