"""SDR da URACE — o Chase reorganizado pelas diretivas de 25/09/2026.

Pacote puro (sem rede, sem banco): classifica a mensagem, decide onde o card
fica — Urace (página 1) ou Comercial (página 2) — (triagem), decide
responder/calar/escalar antes do modelo
(roteador), limpa o que sai para o lead (estilo) e aplica no Kommo conforme o
nível (executor). A ponte (bridge/sdr_ponte.py) liga isto ao mundo real.

Documento: salesagent/docs/sdr.md · Parâmetros: sdr/regras.py
"""
from . import classificador, estilo, evento, executor, funil, regras, roteador, triagem  # noqa: F401


def avaliar(texto, card=None, evento_extra=None, remetente_email=None):
    """Atalho: classifica, faz a triagem e o roteamento de uma mensagem."""
    analise = classificador.classificar(texto, remetente_email=remetente_email)
    ev = {"tipo": "mensagem"}
    ev.update(evento_extra or {})
    decisao = triagem.triar(ev, analise, card or {})
    rota = roteador.rotear(analise, decisao, canal=ev.get("canal"))
    if rota["acao"] == roteador.ESCALAR:
        decisao = triagem.para_atendimento_humano(decisao, card or {})
    return {"analise": analise, "triagem": decisao, "roteamento": rota}
