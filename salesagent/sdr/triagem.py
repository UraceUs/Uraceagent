"""Triagem — decide a zona do card: fica na Entrada ou passa para venda.

Regra central: toda mensagem continua chegando pelo canal de origem. O que se
decide aqui é só onde o card mora no Novo funil e, se não é lead, em que
etapa da Entrada ele fica.

Entrada:
    evento  {tipo, canal, interno, grupo, qualificacao{...}}
    analise saída de classificador.classificar
    card    {existe, zona ('Entrada'|'Comercial'|None), fechado (bool),
             fechado_em (datetime|None)}
Saída: dict com acao, motivo, descricao, destino {zona, etapa, mover}, tags,
score, intencoes.
"""
from datetime import datetime, timezone

from . import regras

E = regras.ETAPAS_ENTRADA
C = regras.ETAPAS_COMERCIAL

_ETAPA_ENTRADA_POR_MOTIVO = {
    "CONTATO_INTERNO": E["RUIDO"],
    "GRUPO_OU_TRANSMISSAO": E["RUIDO"],
    "SPAM_OU_OFERTA": E["RUIDO"],
    "MENSAGEM_AUTOMATICA": E["AUTOMATICO"],
    "OPT_OUT": E["NAO_CONTATAR"],
    "SAUDACAO_ISOLADA": E["AGUARDANDO_CONTEXTO"],
    "MIDIA_SEM_CONTEXTO": E["AGUARDANDO_CONTEXTO"],
    "AGRADECIMENTO_OU_ENCERRAMENTO": E["SEM_SINAL"],
    "SEM_SINAL_COMERCIAL": E["SEM_SINAL"],
}


def _resultado(acao, motivo, analise, etapa=None, tags=None):
    descricao = regras.MOTIVOS_ENTRADA.get(motivo) or regras.MOTIVOS_NAO_ENTRADA.get(motivo) or motivo
    return {
        "acao": acao,
        "motivo": motivo,
        "descricao": descricao,
        "etapa_sugerida": etapa,
        "tags": list(tags or []) + regras.TAGS_POR_MOTIVO.get(motivo, []),
        "score": analise["score"],
        "intencoes": analise["intencoes"],
        "entra_no_comercial": acao in regras.ACOES_NO_COMERCIAL,
    }


def _dias_desde(quando, agora):
    if not quando:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return (agora - quando).total_seconds() / 86400


def _qualificacao_suficiente(q):
    q = q or {}
    return bool(q.get("servico") and (q.get("data") or q.get("periodo"))
                and (q.get("contato") or q.get("nome")))


def _decidir(evento, analise, card, agora):
    no_comercial = card.get("existe") and card.get("zona") == regras.COMERCIAL

    # 1. Ruído estrutural: nunca é lead, nunca recebe resposta.
    if evento.get("interno"):
        return _resultado(regras.IGNORAR, "CONTATO_INTERNO", analise)
    if evento.get("grupo"):
        return _resultado(regras.IGNORAR, "GRUPO_OU_TRANSMISSAO", analise)
    if analise["automatico"]:
        return _resultado(regras.FICA, "MENSAGEM_AUTOMATICA", analise, tags=["sdr:automatico"])
    if analise["spam"]:
        return _resultado(regras.FICA, "SPAM_OU_OFERTA", analise, tags=["sdr:spam"])
    if analise["opt_out"]:
        return _resultado(regras.FICA, "OPT_OUT", analise, tags=["sdr:opt-out"])

    # 2. Eventos do funil de reserva sempre entram (ou atualizam).
    tipo = evento.get("tipo") or "mensagem"
    por_evento = {
        "reserva_etapa2": ("RESERVA_ETAPA2", C["CONFIRMADA"]),
        "reserva_etapa1": ("RESERVA_ETAPA1", C["ETAPA1"]),
        "reserva_etapa1_parada": ("RESERVA_PARADA", C["ETAPA1"]),
        "formulario": ("FORMULARIO_SITE", C["NOVO"]),
        "chamada_perdida": ("CHAMADA_PERDIDA", C["NOVO"]),
    }
    if tipo in por_evento:
        motivo, etapa = por_evento[tipo]
        return _resultado(regras.ANEXAR if no_comercial else regras.CRIAR, motivo, analise, etapa,
                          ["sdr:reserva" if motivo.startswith("RESERVA") else "sdr:site"])

    # 3. Já está em venda e aberto: registra, nunca duplica, não muda etapa.
    if no_comercial and not card.get("fechado"):
        return _resultado(regras.ANEXAR, "CARD_ABERTO_EXISTENTE", analise)

    gatilho = (any(i in regras.GATILHOS_DIRETOS for i in analise["intencoes"])
               or analise["compete"] or analise["conversao"])
    sinal = gatilho or analise["sensivel"] or bool(analise["sinais"]["pit_id"]) or analise["score"] >= regras.LIMIAR

    # 4. Fechado em venda há pouco, voltou com sinal: reabre.
    if no_comercial and card.get("fechado"):
        if not sinal:
            return _resultado(regras.FICA, "SEM_SINAL_COMERCIAL", analise)
        dias = _dias_desde(card.get("fechado_em"), agora)
        if dias is not None and dias <= regras.JANELA_REABERTURA_DIAS:
            return _resultado(regras.REABRIR, "INTENCAO_COMERCIAL", analise, C["QUALIFICANDO"], ["sdr:reaberto"])

    # 5. Sem texto útil: espera contexto.
    if not analise["tem_texto"]:
        return _resultado(regras.FICA, "MIDIA_SEM_CONTEXTO", analise)

    # 6. Dados de qualificação já coletados.
    if _qualificacao_suficiente(evento.get("qualificacao")):
        return _resultado(regras.CRIAR, "DADOS_QUALIFICACAO", analise, C["QUALIFICANDO"], ["sdr:qualificacao"])

    # 7. Conversa social.
    if analise["saudacao_isolada"]:
        return _resultado(regras.FICA, "SAUDACAO_ISOLADA", analise)
    if analise["encerramento"]:
        return _resultado(regras.FICA, "AGRADECIMENTO_OU_ENCERRAMENTO", analise)

    # 8. Sinais que levam para venda.
    if analise["sensivel"]:
        return _resultado(regras.CRIAR, "TEMA_SENSIVEL", analise, C["HUMANO"], ["sdr:sensivel"])
    if analise["pede_humano"]:
        return _resultado(regras.CRIAR, "PEDIDO_HUMANO", analise, C["HUMANO"], ["sdr:pedido-humano"])
    if "corporativo" in analise["intencoes"] or analise["grupo_grande"]:
        return _resultado(regras.CRIAR, "DEMANDA_CORPORATIVA", analise, C["HUMANO"], ["sdr:corporativo"])
    if analise["sinais"]["pit_id"]:
        return _resultado(regras.CRIAR, "PIT_ID_INFORMADO", analise, C["ETAPA1"], ["sdr:pit-id"])
    if gatilho:
        return _resultado(regras.CRIAR, "INTENCAO_COMERCIAL", analise, C["QUALIFICANDO"], ["sdr:intencao-comercial"])
    if analise["score"] >= regras.LIMIAR:
        return _resultado(regras.CRIAR, "SCORE_QUALIFICACAO", analise, C["QUALIFICANDO"], ["sdr:score"])

    return _resultado(regras.FICA, "SEM_SINAL_COMERCIAL", analise)


def destino(decisao, card):
    """Onde o card deve ficar: {zona, etapa, mover}. mover=False = não mexer."""
    acao = decisao["acao"]
    if acao in regras.ACOES_NO_COMERCIAL:
        etapa = decisao["etapa_sugerida"] or (None if acao == regras.ANEXAR else C["NOVO"])
        return {"zona": regras.COMERCIAL, "etapa": etapa, "mover": etapa is not None}

    # Lead que já está em venda não volta para a Entrada. Opt-out lá dentro
    # fecha como perdido; o resto não mexe no card.
    if card.get("existe") and card.get("zona") == regras.COMERCIAL:
        if decisao["motivo"] == "OPT_OUT":
            return {"zona": regras.COMERCIAL, "etapa": C["PERDIDO"], "mover": True}
        return {"zona": regras.COMERCIAL, "etapa": None, "mover": False}

    etapa = _ETAPA_ENTRADA_POR_MOTIVO.get(decisao["motivo"], E["TRIAGEM"])
    return {"zona": regras.ENTRADA, "etapa": etapa, "mover": True}


def triar(evento, analise, card=None, agora=None):
    card = card or {}
    agora = agora or datetime.now(timezone.utc)
    decisao = _decidir(evento, analise, card, agora)

    # Card que já existe na Entrada passa para venda: o mesmo card, não outro.
    if decisao["acao"] == regras.CRIAR and card.get("existe") and card.get("zona") == regras.ENTRADA:
        decisao["acao"] = regras.PROMOVER

    decisao["destino"] = destino(decisao, card)
    return decisao


def para_atendimento_humano(decisao, card=None):
    """Quando o roteador chama uma pessoa, o card vai para "Atendimento
    humano" — venha de onde vier. Lead no meio da reserva (Etapa 1/2) não
    volta de etapa: só recebe a marca de handoff."""
    card = card or {}
    etapa_humano = C["HUMANO"]
    no_comercial = card.get("existe") and card.get("zona") == regras.COMERCIAL
    em_reserva = no_comercial and card.get("etapa") in (
        # nomes normalizados vindos do funil.Mapa.localizar
        _norm(C["ETAPA1"]), _norm(C["ETAPA2"]))
    if em_reserva:
        return decisao
    if decisao["acao"] in (regras.FICA, regras.CRIAR):
        decisao["acao"] = regras.PROMOVER if card.get("existe") and card.get("zona") == regras.ENTRADA else (
            regras.ANEXAR if no_comercial else regras.CRIAR)
    decisao["etapa_sugerida"] = etapa_humano
    decisao["entra_no_comercial"] = True
    decisao["destino"] = {"zona": regras.COMERCIAL, "etapa": etapa_humano, "mover": True}
    return decisao


def _norm(nome):
    from .classificador import normalizar
    return normalizar(nome)
