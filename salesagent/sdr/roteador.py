"""Roteador — antes do modelo: responder, calar ou chamar uma pessoa.

Só vale no nível "atender" (a ponte responde ao lead). Complementa o B4 de
gates.py: o B4 cobre desconto, reembolso, jurídico, reclamação e pedido de
humano; aqui entram os sinais do SDR que o B4 não tinha — sinal de
conversão, piloto que compete, demanda corporativa ou grupo grande — e o
que NÃO é lead (automático, spam, interno, grupo), que não recebe resposta.

"Toda mensagem de lead recebe resposta" continua valendo: o que se cala
aqui não é lead. Opt-out recebe UMA confirmação e silêncio depois.
"""
from . import regras

RESPONDER = "responder"
SILENCIAR = "silenciar"
CONFIRMAR_OPT_OUT = "confirmar_opt_out"
ESCALAR = "escalar"

MENSAGEM_OPT_OUT = {
    "pt": "Tudo certo, não vamos mais te mandar mensagens por aqui. Se precisar, é só chamar.",
    "en": "Got it, we won't message you here anymore. If you ever need us, just reach out.",
    "es": "Entendido, no te enviaremos más mensajes por aquí. Si nos necesitas, escríbenos.",
}


def _escalar(motivo):
    return {
        "acao": ESCALAR,
        "motivo": motivo,
        "descricao": regras.MOTIVOS_ESCALONAMENTO[motivo],
        "prioridade": regras.PRIORIDADE_ESCALONAMENTO[motivo],
    }


def rotear(analise, triagem):
    """Decisão antes do modelo. A ordem importa: o que não é lead sai
    primeiro; entre as escalações, a mais grave vence."""
    if triagem["acao"] == regras.IGNORAR:
        return {"acao": SILENCIAR, "motivo": triagem["motivo"]}
    if analise["automatico"]:
        return {"acao": SILENCIAR, "motivo": "MENSAGEM_AUTOMATICA"}
    if analise["spam"]:
        return {"acao": SILENCIAR, "motivo": "SPAM_OU_OFERTA"}
    if analise["opt_out"]:
        return {"acao": CONFIRMAR_OPT_OUT, "motivo": "OPT_OUT"}

    if analise["sensivel"]:
        return _escalar("TEMA_SENSIVEL")
    if analise["pede_humano"]:
        return _escalar("PEDIDO_HUMANO")
    if analise["insatisfacao"]:
        return _escalar("LEAD_INSATISFEITO")
    if analise["conversao"]:
        return _escalar("SINAL_CONVERSAO")
    if analise["compete"]:
        return _escalar("PILOTO_COMPETIDOR")
    if analise["desconto"]:
        return _escalar("NEGOCIACAO")
    if "corporativo" in analise["intencoes"] or analise["grupo_grande"]:
        return _escalar("CORPORATIVO")

    return {"acao": RESPONDER, "motivo": None}


def idioma(texto_normalizado):
    """Idioma para a confirmação de opt-out (o resto é o modelo que escolhe)."""
    t = f" {texto_normalizado} "
    if any(p in t for p in (" stop ", " unsubscribe ", " remove me ", " please ", " don't ", " do not ")):
        return "en"
    if any(p in t for p in (" no quiero ", " por favor ", " gracias ", " mensajes ")):
        return "es"
    return "pt"
