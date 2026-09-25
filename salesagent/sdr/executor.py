"""Executor — aplica a decisão da triagem no card do Kommo.

Níveis (SDR_MODO no bridge.env):
  observar   decide e registra; não escreve nada no Kommo (padrão);
  organizar  move etapa, põe tag, escreve nota e cria tarefa; não responde;
  atender    como organizar, e a ponte também responde ao lead.

Escrever no Kommo (etapa, tag, tarefa) é ato do dono pela D-09-17: subir de
"observar" exige a palavra dele. Por isso o padrão é observar.
"""
import time

from . import regras

OBSERVAR = "observar"
ORGANIZAR = "organizar"
ATENDER = "atender"
MODOS = (OBSERVAR, ORGANIZAR, ATENDER)


def modo_valido(valor):
    valor = (valor or "").strip().lower()
    return valor if valor in MODOS else OBSERVAR


def escreve(modo):
    return modo in (ORGANIZAR, ATENDER)


def texto_da_nota(decisao, roteamento=None):
    linhas = [f"[SDR] {decisao['acao']} ({decisao['motivo']}): {decisao['descricao']}"]
    d = decisao.get("destino") or {}
    if d.get("mover"):
        linhas.append(f"Etapa: {d['etapa']}")
    if decisao.get("intencoes"):
        linhas.append("Sinais: " + ", ".join(decisao["intencoes"]) + f" · score {decisao['score']}")
    if roteamento and roteamento.get("acao") == "escalar":
        linhas.append(f"HANDOFF {roteamento['prioridade'].upper()}: {roteamento['descricao']}")
    return "\n".join(linhas)


def aplicar(api, lead, decisao, mapa, modo, roteamento=None, responsavel_id=None, agora=None):
    """Aplica a decisão num lead. `api` precisa de move/add_tags/add_note/add_task.

    Devolve o que foi (ou seria, em observar) feito — vai para o log de
    auditoria nos dois casos, que é o que permite conferir antes de ligar.
    """
    agora = agora or time.time()
    gravar = escreve(modo)
    feito = {"modo": modo, "lead_id": lead["id"], "acao": decisao["acao"],
             "motivo": decisao["motivo"], "moveu": None, "tags": [], "nota": False,
             "tarefa": None, "aviso": None}

    destino = decisao.get("destino") or {}
    if destino.get("mover") and destino.get("etapa"):
        status = mapa.status_id(destino["etapa"])
        if not status:
            feito["aviso"] = f"etapa não encontrada no Novo funil: {destino['etapa']}"
        elif int(lead.get("status_id") or 0) != status:
            feito["moveu"] = destino["etapa"]
            if gravar:
                api.move(lead["id"], mapa.pipeline_id, status)

    existentes = {t.get("name") for t in (lead.get("_embedded") or {}).get("tags", [])}
    novas = [t for t in dict.fromkeys(decisao.get("tags") or []) if t not in existentes]
    if roteamento and roteamento.get("acao") == "escalar":
        novas += [t for t in ("sdr:handoff", f"handoff:{roteamento['motivo'].lower()}") if t not in existentes]
    if novas:
        feito["tags"] = novas
        if gravar:
            api.add_tags(lead["id"], novas)

    # Nota só quando o card entra em venda ou vai para uma pessoa: o que fica
    # na triagem não polui o histórico.
    entrou = decisao["acao"] in (regras.CRIAR, regras.PROMOVER, regras.REABRIR)
    escalou = bool(roteamento and roteamento.get("acao") == "escalar")
    if entrou or escalou:
        feito["nota"] = True
        if gravar:
            api.add_note(lead["id"], texto_da_nota(decisao, roteamento))

    # Handoff sem a ponte respondendo (nível organizar): vira tarefa com o SLA
    # da prioridade para o responsável único. No nível atender, quem cuida é
    # o escalate() da ponte.
    if escalou and modo != ATENDER:
        minutos = regras.SLA_MINUTOS.get(roteamento["prioridade"], 15)
        feito["tarefa"] = {"prioridade": roteamento["prioridade"], "prazo_min": minutos}
        if gravar:
            api.add_task(lead["id"], f"SDR: {roteamento['descricao']}",
                         int(agora) + minutos * 60, responsavel_id)
    return feito
