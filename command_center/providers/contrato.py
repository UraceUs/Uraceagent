"""Contrato mensal: quantas sessões o cliente já usou no mês (#61).

Dono, 01/10: *"se ele tivesse um contrato com a gente... as sessões são para ser usadas
naquele mês... ele fica com o contador de quantas sessões daquele mês do contrato já
utilizou. Passou o mês, zera"* — e *"não deixa o cliente ter essa informação... deixa
mostrando pra gente se ele deixou de usar alguma"*.

- Sessões por mês: o número do card (`clients.monthly_sessions`); sem número, o padrão da
  Academy (4), que é o que o card já usava.
- **Usadas no mês** são as sessões do Asana do card (as mesmas que o card já contava) **mais**
  os agendamentos do site da conta ligada ao card (não cancelados nem recusados). A conta é
  de cada mês: virou o mês, começa do zero, sem apagar nada.
- Nada disto vai para a área do cliente: é só para a equipe.
"""
from command_center.db import todos, um

PADRAO_SESSOES = 4


def sessoes_por_mes(con, cid):
    c = um(con, "SELECT monthly_sessions FROM clients WHERE id=?", (cid,))
    return (c and c["monthly_sessions"]) or PADRAO_SESSOES


def tem_contrato(con, cid):
    c = um(con, "SELECT plan_type, monthly_sessions, monthly_amount FROM clients WHERE id=?", (cid,)) if cid else None
    return bool(c and (c["plan_type"] == "monthly" or c["monthly_sessions"] or c["monthly_amount"]))


def sessoes_asana(con, cid, mes):
    """As tarefas de treino do mês no Asana (o mesmo critério que o card usava desde 09/09)."""
    return todos(con, """SELECT title, due_on, status FROM tasks WHERE client_id=? AND due_on LIKE ? AND project='U-RACE'
                           AND LOWER(COALESCE(section,'')) NOT IN ('races','finished services') OR (client_id=? AND due_on LIKE ? AND status='completed' AND LOWER(COALESCE(section,''))='finished services')""",
                 (cid, mes + "%", cid, mes + "%"))


def sessoes_site(con, cid, mes):
    """Agendamentos feitos na área do cliente pela conta ligada a este card."""
    return todos(con, """SELECT b.date AS due_on, COALESCE(b.service_name, 'Site booking') AS title, b.status
                           FROM bookings b JOIN portal_accounts a ON a.id=b.account_id
                          WHERE a.client_id=? AND b.date LIKE ? AND b.status IN ('pendente','confirmada') ORDER BY b.date""",
                 (cid, mes + "%"))


def usadas(con, cid, mes):
    a, s = sessoes_asana(con, cid, mes), sessoes_site(con, cid, mes)
    return {"asana": a, "site": s, "total": len(a) + len(s)}


def situacao_do_agendamento(con, cid, data_iso):
    """Para a lista da equipe: o agendamento cabe no contrato daquele mês? None sem contrato."""
    if not tem_contrato(con, cid):
        return None
    total = sessoes_por_mes(con, cid)
    n = usadas(con, cid, data_iso[:7])["total"]
    return {"usadas": n, "sessoes_por_mes": total, "acima": n > total}
