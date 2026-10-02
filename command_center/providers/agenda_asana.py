"""Agendamento do site → tarefa no Asana (#67).

Dono, 01/10: *"todo agendamento independente se esta confirmado ou nao vira uma tarefa no
asana"*.

- O cliente marca no portal e a tarefa nasce no U-RACE (pendente ou confirmada), na coluna do
  dia da semana, **do modelo oficial** (#69, dono, 02/10: *"precisa vir com o corpo do template.
  Com todas as subtarefas... igual as outras tarefas que a gente tem de agendamento"*): o mesmo
  modelo, o mesmo bloco de descrição (`acoes.notas_servico`, com as medidas e a experiência do
  driver), o título da casa (`Piloto_Serviço [n/m]`) e o mesmo evento `task.created` que acorda
  a IA para as automações da tarefa feita à mão.
- Quando a situação muda (confirmada, recusada, cancelada), a tarefa ganha um comentário; a
  recusada e a cancelada também ficam marcadas no título, para ninguém ir à pista à toa.
- **Card do driver** (#65): a tarefa fica no card do driver do agendamento, carimbada
  (`client_by='human'`: o vínculo driver ↔ card foi uma pessoa que confirmou). A sincronia não
  a devolve ao primeiro card com o mesmo e-mail — que pode ser o do irmão.
- **Nada contado duas vezes:** o contrato e o histórico usam o agendamento; a tarefa dele
  não entra de novo (ver `GIDS_DE_AGENDAMENTO`).
- O Asana fora do ar não derruba o agendamento: o laço do servidor tenta de novo a cada 15 min.
"""
import json
import os
from datetime import date

from command_center.db import agora, atualizar, inserir, todos, um

PROJETO_URACE = "1205450093098920"
DIAS_EN = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
PERIODO_EN = {"manha": "morning", "tarde": "afternoon", "dia": "full day"}
SITUACAO_EN = {"pendente": "PENDING CONFIRMATION", "confirmada": "CONFIRMED", "recusada": "DECLINED", "cancelada": "CANCELLED"}
MARCA_TITULO = {"recusada": "DECLINED - ", "cancelada": "CANCELLED - "}
ATIVAS = ("pendente", "confirmada")

# subconsulta: ids de tarefa (tasks.id) que são de um agendamento do site
GIDS_DE_AGENDAMENTO = """SELECT l.entity_id FROM entity_links l JOIN bookings bk ON bk.asana_gid=l.external_id
                          WHERE l.entity_type='task' AND l.system='asana'"""


def _secao_do_dia(dia):
    from command_center.providers.sync import SECOES_DIAS
    nome = DIAS_EN[dia.weekday()]
    return next(((g, n) for g, n in SECOES_DIAS.items() if n == nome), (None, None))


def _dados(con, b):
    from command_center.providers import agenda_sessoes as ag
    from command_center.providers.contrato import CARD_DO_AGENDAMENTO
    x = um(con, f"""SELECT b.*, a.name AS resp, a.email, a.phone, a.phone_country, p.name AS driver, p.birth_date AS dob,
                           p.measures, p.notes AS experiencia, {CARD_DO_AGENDAMENTO} AS card
                      FROM bookings b JOIN portal_accounts a ON a.id=b.account_id LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                     WHERE b.id=?""", (b["id"],))
    dia = date.fromisoformat(x["date"])
    x["hora"] = ag._inicio(ag.config(con), dia, x["period"]).strftime("%H:%M")
    x["dia"] = dia
    x["medidas"] = json.loads(x["measures"]) if x["measures"] else {}
    # contrato do mês (#61): a sessão é a n-ésima das m do contrato; sem contrato, [1/1]
    from command_center.providers import contrato
    x["n"], x["m"] = 1, 1
    if x["card"] and contrato.tem_contrato(con, x["card"]):
        x["m"] = contrato.sessoes_por_mes(con, x["card"])
        x["n"] = max(1, contrato.usadas(con, x["card"], x["date"][:7])["total"])
    return x


def titulo(x):
    """O padrão do quadro: 'Piloto_Serviço [n/m]' (rotas.nome_tarefa)."""
    from command_center.api.rotas import nome_tarefa
    return nome_tarefa(x["driver"] or x["resp"], x["service_name"] or "Session", None, x["n"], x["m"])


def _medida(md, k, un):
    v = md.get(k)
    return f"{v:g} {un}" if isinstance(v, (int, float)) else (f"{v} {un}" if v else None)


def notas(x):
    """O mesmo bloco das tarefas feitas no painel e pela IA (acoes.notas_servico), com o que o
    site sabe a mais: Client ID, período e hora, situação e a nota do cliente."""
    from command_center.api.acoes import notas_servico
    tel = f"{x['phone_country']} {x['phone']}" if x["phone"] and x["phone_country"] and x["phone_country"] != "+1" else x["phone"]
    md = x["medidas"]
    extra = [f"Client ID: {x['card'] or 'not linked yet'}",
             f"Site booking #{x['id']}: {PERIODO_EN.get(x['period'], x['period'])} (starts {x['hora']} Florida)",
             f"Status: {SITUACAO_EN.get(x['status'], x['status'])}"]
    if x["notes"]:
        extra.append(f"Client note: {x['notes']}")
    return notas_servico(x["driver"] or x["resp"], x["resp"], x["email"], tel, x["dob"], x["date"], x["service_name"] or "Session",
                         None, x["price"], _medida(md, "height_in", "in"), _medida(md, "weight_lb", "lb"),
                         _medida(md, "waist_in", "in"), x["experiencia"], "\n".join(extra), por="área do cliente (site)")


def _chamar_padrao(ferramenta, **kw):
    """Escrita no Asana aprovada pelo dono para este fluxo (01/10): APLICAR ligado só nesta chamada."""
    from command_center import providers
    anterior = os.environ.get("APLICAR")
    os.environ["APLICAR"] = "1"
    try:
        return providers.chamar("asana", ferramenta, **kw)
    finally:
        if anterior is None:
            os.environ.pop("APLICAR", None)
        else:
            os.environ["APLICAR"] = anterior


def _espelhar_local(con, x, gid, secao_gid, secao, nome, link=None):
    """A tarefa aparece no card na hora (sem esperar a sincronia), ligada ao card do driver, e
    acorda a IA como a tarefa criada à mão (`task.created`)."""
    from command_center.providers.sync import ASANA_LINK, _liga
    campos = dict(client_id=x["card"], title=nome, project="U-RACE", section=secao, section_gid=secao_gid,
                  status="open", due_on=x["date"], resp_name=x["resp"], resp_email=(x["email"] or "").lower() or None,
                  resp_phone=x["phone"], client_by="human" if x["card"] else None, synced_at=agora())
    tid = um(con, "SELECT entity_id FROM entity_links WHERE system='asana' AND external_id=? AND entity_type='task'", (gid,))
    if tid:
        atualizar(con, "tasks", tid["entity_id"], **campos)
        return tid["entity_id"]
    nid = inserir(con, "tasks", **campos)
    _liga(con, "task", nid, "asana", gid, link or ASANA_LINK.format(proj=PROJETO_URACE, gid=gid))
    if x["card"]:
        from command_center.api import motor
        motor.registrar_evento(con, "task.created", "task", nid, x["card"],
                               f"{nome} em {secao or 'U-RACE'} ({x['date']}) — agendamento do site #{x['id']}")
    return nid


def criar(con, bid, chamar=None):
    """Cria a tarefa do agendamento `bid` (se ainda não tem). Devolve o gid, ou None."""
    chamar = chamar or _chamar_padrao
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or b["asana_gid"]:
        return b and b["asana_gid"]
    from command_center.api.acoes import MODELO_SESSAO, RACE_PADRAO
    x = _dados(con, b)
    secao_gid, secao = _secao_do_dia(x["dia"])
    nome = titulo(x)
    try:
        res = chamar("asana_criar_do_modelo", modelo_gid=MODELO_SESSAO, nome=nome, notas=notas(x), vence_em=x["date"],
                     campos={"Race": RACE_PADRAO}, **({"secao_gid": secao_gid} if secao_gid else {}))
        gid = (res or {}).get("gid")
        if not gid:
            raise RuntimeError("o Asana não criou a tarefa (simulação ou sem resposta)")
    except Exception as e:                                         # noqa: BLE001 - registra e tenta no próximo ciclo
        atualizar(con, "bookings", bid, asana_error=f"{type(e).__name__}: {str(e)[:300]}",
                  asana_attempts=(b["asana_attempts"] or 0) + 1)
        return None
    atualizar(con, "bookings", bid, asana_gid=str(gid), asana_status=b["status"], asana_error=None,
              asana_attempts=(b["asana_attempts"] or 0) + 1)
    _espelhar_local(con, x, str(gid), secao_gid, secao, (res or {}).get("nome") or nome, (res or {}).get("link"))
    return str(gid)


def avisar(con, bid, chamar=None):
    """Leva ao Asana a situação nova do agendamento (comentário; marca no título se saiu)."""
    chamar = chamar or _chamar_padrao
    b = um(con, "SELECT * FROM bookings WHERE id=?", (bid,))
    if not b or not b["asana_gid"] or b["asana_status"] == b["status"]:
        return False
    x = _dados(con, b)
    quem = {"cliente": "by the client", "equipe": "by the URACE team"}.get(b["cancelled_by"] or "", "")
    texto = f"Site booking #{bid}: {SITUACAO_EN.get(b['status'], b['status'])}{(' ' + quem) if b['status'] == 'cancelada' and quem else ''}."
    if b["decision_note"]:
        texto += f" Note: {b['decision_note']}"
    local = um(con, """SELECT title FROM tasks WHERE id IN (SELECT entity_id FROM entity_links WHERE system='asana'
                        AND entity_type='task' AND external_id=?)""", (b["asana_gid"],))
    atual = (local or {}).get("title") or titulo(x)
    novo_titulo = atual if any(atual.startswith(m) for m in MARCA_TITULO.values()) else MARCA_TITULO.get(b["status"], "") + atual
    try:
        chamar("asana_comentar", gid=b["asana_gid"], texto=texto)
        if b["status"] in MARCA_TITULO and novo_titulo != atual:
            chamar("asana_renomear", gid=b["asana_gid"], nome=novo_titulo)
    except Exception as e:                                         # noqa: BLE001
        atualizar(con, "bookings", bid, asana_error=f"{type(e).__name__}: {str(e)[:300]}")
        return False
    atualizar(con, "bookings", bid, asana_status=b["status"], asana_error=None)
    con.execute("""UPDATE tasks SET title=? WHERE id IN (SELECT entity_id FROM entity_links WHERE system='asana'
                    AND entity_type='task' AND external_id=?)""", (novo_titulo, b["asana_gid"]))
    return True


def ligar_ao_card(con):
    """Driver que ganhou card depois do agendamento: a tarefa passa para o card dele."""
    from command_center.providers.contrato import CARD_DO_AGENDAMENTO
    n = 0
    for r in todos(con, f"""SELECT t.id, {CARD_DO_AGENDAMENTO} AS card FROM bookings b
                             JOIN portal_accounts a ON a.id=b.account_id LEFT JOIN portal_pilots p ON p.id=b.pilot_id
                             JOIN entity_links l ON l.external_id=b.asana_gid AND l.entity_type='task' AND l.system='asana'
                             JOIN tasks t ON t.id=l.entity_id WHERE b.asana_gid IS NOT NULL"""):
        if r["card"] and not um(con, "SELECT 1 AS x FROM tasks WHERE id=? AND client_id=?", (r["id"], r["card"])):
            atualizar(con, "tasks", r["id"], client_id=r["card"], client_by="human")
            n += 1
    return n


def rodar(con, chamar=None, hoje=None):
    """Laço do servidor: cria o que falta (agendamento ativo, de hoje em diante) e leva as
    mudanças de situação. Devolve {"criadas", "avisadas", "falhas"}."""
    from command_center.providers.agenda_sessoes import _agora_fl
    hoje = hoje or _agora_fl().date().isoformat()
    criadas = avisadas = falhas = 0
    for b in todos(con, f"""SELECT id FROM bookings WHERE asana_gid IS NULL AND status IN {ATIVAS} AND date>=?
                             AND COALESCE(asana_attempts,0) < 20 ORDER BY id""", (hoje,)):
        if criar(con, b["id"], chamar):
            criadas += 1
        else:
            falhas += 1
    for b in todos(con, "SELECT id FROM bookings WHERE asana_gid IS NOT NULL AND COALESCE(asana_status,'')<>status ORDER BY id"):
        if avisar(con, b["id"], chamar):
            avisadas += 1
        else:
            falhas += 1
    ligar_ao_card(con)
    return {"criadas": criadas, "avisadas": avisadas, "falhas": falhas}


def levar(bid):
    """Depois da resposta ao cliente (BackgroundTasks): cria ou atualiza a tarefa deste
    agendamento, numa conexão própria. Falha fica no agendamento e o laço tenta de novo."""
    from command_center.db import conectar
    con = conectar()
    try:
        b = um(con, "SELECT asana_gid FROM bookings WHERE id=?", (bid,))
        if b and b["asana_gid"]:
            avisar(con, bid)
        elif b:
            criar(con, bid)
        con.commit()
    except Exception:                                              # noqa: BLE001 - o laço de 15 min tenta de novo
        pass
    finally:
        con.close()


def agendamento_da_tarefa(con, gid):
    """Para a sincronia: o agendamento dono desta tarefa do Asana, com o card do driver."""
    from command_center.providers.contrato import CARD_DO_AGENDAMENTO
    return um(con, f"""SELECT b.id, {CARD_DO_AGENDAMENTO} AS card FROM bookings b JOIN portal_accounts a ON a.id=b.account_id
                        LEFT JOIN portal_pilots p ON p.id=b.pilot_id WHERE b.asana_gid=?""", (gid,))
