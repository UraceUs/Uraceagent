"""Contrato mensal: quantas sessões o cliente já usou no mês (#61) e quanto custa a sessão a mais (#314).

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

Dono, 16/10 (#314): *"Quando for cliente do Kart School … pagam pelo QuickBooks. O invoice deles é
recorrente … quando ele for para a área do cliente para ele poder agendar a sessão dele, ele não precisa
efetuar o pagamento, a não ser que as sessões daquele pacote dele … Se ele já tiver usado as sessões
daquele pacote dele mensal, aí ele paga uma sessão adicional. Aí a sessão é dividida pelo valor do
mensal dele … ou então usa aqueles valores que eu te passei."* (Academy e Kart School são a mesma coisa.)

- **Vigente** (`vigente`): o card tem contrato, o plano comprado no site já teve a 1ª mensalidade paga
  e a recorrência (quando existe) não acabou. Pro Racing Driver sem mensal no card não é recorrente.
- **Vaga do pacote** (`usadas_do_pacote`): conta a sessão do plano; a extra e a paga no Stripe não
  ocupam vaga. Cancelada devolve a vaga do mês. O pacote é por mês (zera no dia 1), também nos
  contratos de 6 e 12 meses.
- **Preço da extra** (`preco_extra`): o valor configurado no card > o do plano > mensal do card ÷
  sessões do mês, em centavos com arredondamento comercial (2.756,90 ÷ 4 = 689,23).
- **Item da extra** (`item_extra`): o do card > o do plano > o item "Extra session" do QuickBooks.
- **Alocar** (`alocar`): por mês e em ordem de data, os dias pedidos ocupam as vagas livres do
  pacote; o resto é extra.
"""
from decimal import ROUND_HALF_UP, Decimal

from command_center.db import todos, um

PADRAO_SESSOES = 4
CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


# O card de um agendamento do site (#65): o do driver; sem driver marcado, o da conta.
# Driver ainda sem card não cai no card do irmão — fica sem card até a equipe vincular.
CARD_DO_AGENDAMENTO = "(CASE WHEN b.pilot_id IS NULL THEN a.client_id ELSE p.client_id END)"
# #314: a sessão que ocupa a vaga do pacote. A de antes (sem `coverage`) conta se não foi cobrada à parte.
DO_PACOTE = "(b.coverage='plano' OR (b.coverage IS NULL AND COALESCE(b.charge_kind,'') IN ('','contrato')))"


def sessoes_por_mes(con, cid):
    c = um(con, "SELECT monthly_sessions FROM clients WHERE id=?", (cid,))
    return (c and c["monthly_sessions"]) or PADRAO_SESSOES


def tem_contrato(con, cid):
    c = um(con, "SELECT plan_type, monthly_sessions, monthly_amount FROM clients WHERE id=?", (cid,)) if cid else None
    return bool(c and (c["plan_type"] == "monthly" or c["monthly_sessions"] or c["monthly_amount"]))


def _mes_de_hoje():
    from command_center.providers.agenda_sessoes import _agora_fl
    return _agora_fl().date().isoformat()[:7]


def plano_do_site(con, cid):
    """O último plano comprado no site para este card (#169), ou None."""
    return um(con, "SELECT * FROM plan_orders WHERE client_id=? AND status<>'cancelada' ORDER BY id DESC LIMIT 1",
              (cid,)) if cid else None


def plano_pago(con, o):
    """A 1ª mensalidade do plano do site está paga (conferida direto ou pelo espelho do QuickBooks)?"""
    if o["status"] == "ativa" or o["paid_at"]:
        return True
    from command_center.providers.cobranca_agenda import invoice_paga
    return invoice_paga(con, o)


def plano_encerrado(con, cid, mes):
    """A recorrência do card acabou antes deste mês. Sem recorrência no painel, o card manda (o de sempre)."""
    recs = todos(con, "SELECT status, end_on FROM monthly_recurring WHERE client_id=? AND status IN ('active','ended')", (cid,))
    return bool(recs) and not any(r["status"] == "active" and r["end_on"] >= f"{mes}-01" for r in recs)


def vigente(con, cid, mes=None):
    """O card é de aluno recorrente neste mês (#314): marca na área dele, a sessão do pacote sai sem custo
    e a extra vai pela invoice do QuickBooks. Decisões de 16/10: o plano comprado no site só libera as sessões
    depois da 1ª mensalidade paga; o plano encerrado não libera mais."""
    if not cid or not tem_contrato(con, cid):
        return False
    o = plano_do_site(con, cid)
    if o and o["status"] == "pendente" and not plano_pago(con, o):
        return False
    return not plano_encerrado(con, cid, mes or _mes_de_hoje())


def sessoes_asana(con, cid, mes):
    """As tarefas de treino do mês no Asana (o mesmo critério que o card usava desde 09/09)."""
    from command_center.providers.agenda_asana import GIDS_DE_AGENDAMENTO   # #67: a do site já conta pelo agendamento
    return todos(con, f"""SELECT title, due_on, status FROM tasks WHERE id NOT IN ({GIDS_DE_AGENDAMENTO}) AND (
                           client_id=? AND due_on LIKE ? AND project='U-RACE'
                           AND LOWER(COALESCE(section,'')) NOT IN ('races','finished services') OR (client_id=? AND due_on LIKE ? AND status='completed' AND LOWER(COALESCE(section,''))='finished services'))""",
                 (cid, mes + "%", cid, mes + "%"))


def sessoes_site(con, cid, mes, so_do_pacote=False, sem=()):
    """Agendamentos feitos na área do cliente para o driver deste card (#65: cada driver tem o
    seu card; a sessão do irmão não conta aqui). Agendamento sem driver conta no card da conta.
    `so_do_pacote` (#314): só as que ocupam vaga do pacote; `sem`: ids que não entram na conta."""
    filtro = f" AND {DO_PACOTE}" if so_do_pacote else ""
    if sem:
        filtro += f" AND b.id NOT IN ({','.join('?' * len(sem))})"
    return todos(con, f"""SELECT b.id, b.date AS due_on, COALESCE(b.service_name, 'Site booking') AS title, b.status, b.coverage
                           FROM bookings b JOIN portal_accounts a ON a.id=b.account_id LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                          WHERE {CARD_DO_AGENDAMENTO}=? AND b.date LIKE ? AND b.status IN ('pendente','confirmada'){filtro}
                          ORDER BY b.date""",
                 (cid, mes + "%", *sem))


def usadas(con, cid, mes):
    a, s = sessoes_asana(con, cid, mes), sessoes_site(con, cid, mes)
    return {"asana": a, "site": s, "total": len(a) + len(s)}


def usadas_do_pacote(con, cid, mes, sem=()):
    """As vagas do pacote do mês já ocupadas: o Asana e as sessões do plano. A extra e a do Stripe não contam."""
    return len(sessoes_asana(con, cid, mes)) + len(sessoes_site(con, cid, mes, so_do_pacote=True, sem=sem))


# ------------------------------------------------------------------ a sessão extra (#314)
def centavos(v):
    """Decimal com 2 casas, arredondamento comercial (689,225 → 689,23). Nada de float na conta."""
    return Decimal(str(v)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def servico_do_plano(con, cid):
    """O plano (booking_services kind='plan') do card: o do último plano comprado no site, ou o de mesmo nome
    do plano escrito no card. None quando não há."""
    o = plano_do_site(con, cid)
    if o:
        s = um(con, "SELECT * FROM booking_services WHERE id=?", (o["service_id"],))
        if s:
            return s
    c = um(con, "SELECT monthly_plan FROM clients WHERE id=?", (cid,))
    if c and c["monthly_plan"]:
        achados = todos(con, "SELECT * FROM booking_services WHERE kind='plan' AND LOWER(name)=LOWER(?)", (c["monthly_plan"],))
        if len(achados) == 1:
            return achados[0]
    return None


def extra(con, cid):
    """{preco: Decimal | None, origem: 'card' | 'plano' | 'mensal' | None, conta: '2,756.90 ÷ 4'}. A ordem é a
    do dono (16/10): o valor configurado no card, depois o do plano, depois o mensal ÷ sessões do mês."""
    c = um(con, "SELECT extra_session_price, monthly_amount FROM clients WHERE id=?", (cid,)) if cid else None
    if not c:
        return {"preco": None, "origem": None, "conta": None}
    if c["extra_session_price"]:
        return {"preco": centavos(c["extra_session_price"]), "origem": "card", "conta": None}
    s = servico_do_plano(con, cid)
    if s and s["extra_price"]:
        return {"preco": centavos(s["extra_price"]), "origem": "plano", "conta": None}
    if c["monthly_amount"]:
        n = sessoes_por_mes(con, cid)
        return {"preco": (Decimal(str(c["monthly_amount"])) / n).quantize(CENTAVO, rounding=ROUND_HALF_UP), "origem": "mensal",
                "conta": f"{c['monthly_amount']:,.2f} ÷ {n}"}
    return {"preco": None, "origem": None, "conta": None}


def preco_extra(con, cid):
    return extra(con, cid)["preco"]


def item_extra(con, cid):
    """O item do QuickBooks da sessão extra: o do card, o do plano, ou o item "Extra session" do espelho
    (no QuickBooks da URACE: "Academy | Extra session (beyond monthly 4)"). None quando não há nenhum."""
    c = um(con, "SELECT extra_item_id FROM clients WHERE id=?", (cid,)) if cid else None
    if c and c["extra_item_id"]:
        return c["extra_item_id"]
    s = servico_do_plano(con, cid) if cid else None
    if s and s["extra_item_id"]:
        return s["extra_item_id"]
    i = um(con, """SELECT id FROM qbo_items WHERE active=1 AND (LOWER(name) LIKE '%extra session%'
                    OR LOWER(COALESCE(full_name,'')) LIKE '%extra session%')
                  ORDER BY (LOWER(COALESCE(full_name, name)) LIKE '%academy%') DESC, name LIMIT 1""")
    return i["id"] if i else None


def alocar(con, cid, datas, sem=()):
    """Os dias pedidos (AAAA-MM-DD, na ordem do pedido) → [{coverage, price}] na mesma ordem. Por mês, em
    ordem de data: as vagas livres do pacote viram `plano` (sem custo); o resto, `extra` (preço da extra).
    O mês em que o card não é vigente (plano acabou) fica `None`: é sessão avulsa. `sem`: os ids dos
    agendamentos que estão sendo alocados (não contam como já usados)."""
    total = sessoes_por_mes(con, cid)
    preco = preco_extra(con, cid)
    livres, ok, saida = {}, {}, [None] * len(datas)
    for i in sorted(range(len(datas)), key=lambda k: (datas[k], k)):
        mes = datas[i][:7]
        if mes not in ok:
            ok[mes] = vigente(con, cid, mes)
            livres[mes] = max(0, total - usadas_do_pacote(con, cid, mes, sem)) if ok[mes] else 0
        if not ok[mes]:
            saida[i] = {"coverage": None, "price": None}
        elif livres[mes] > 0:
            livres[mes] -= 1
            saida[i] = {"coverage": "plano", "price": ZERO}
        else:
            saida[i] = {"coverage": "extra", "price": preco}
    return saida


def situacao_do_agendamento(con, cid, data_iso, b=None):
    """Para a lista da equipe: o agendamento cabe no contrato daquele mês? None sem contrato.
    #314: a vaga é a do pacote (extra e Stripe não ocupam); com `b`, vale o que foi alocado."""
    if not tem_contrato(con, cid):
        return None
    total = sessoes_por_mes(con, cid)
    n = usadas_do_pacote(con, cid, data_iso[:7])
    cob = (b or {}).get("coverage")
    return {"usadas": n, "sessoes_por_mes": total, "acima": cob == "extra" if cob else n > total}

