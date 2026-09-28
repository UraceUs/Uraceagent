"""Ponte ↔ SDR: liga o pacote salesagent/sdr ao Kommo real, ao estado e à
auditoria da sales-bridge.

Os funis são os da equipe: Urace (página 1, recebe tudo) e Comercial
(página 2, só lead). Quem sobe o card novo de uma página para a outra são
as REGRAS 1 e 2 da própria equipe em Urace > First Contact. O SDR
complementa (salesagent/docs/sdr.md, "Quem move o quê"):
  - lead criado em First Contact com nome de lixo: nao_e_lead antes dos
    5 min da REGRA 1;
  - mensagem em First Contact: só tags; quem sobe é a REGRA 2;
  - Cold Leads / Follow Up 1 ou fechado, com sinal comercial: sobe para
    Comercial > ENTRADA;
  - card de outro funil (Contact list, Pós Venda...) com sinal comercial:
    tarefa + nota, uma vez por dia, sem mover;
  - Comercial: handoff, opt-out e perdido, sempre para frente.

Tudo que escreve no Kommo passa por aqui e respeita SDR_MODO (config.py):
em "observar" nada é escrito — a decisão vai só para o log de auditoria
(kind "sdr"), que é como se confere o SDR antes de ligar. Ver
salesagent/docs/sdr.md.

Nenhuma chamada ao Kommo daqui roda no caminho da resposta ao lead: a
triagem do card corre em thread própria. A janela do Salesbot (~58s) é do
lead, não da organização do funil.
"""
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # salesagent/

import sdr  # noqa: E402
from sdr import estilo, evento, executor, funil, regras, roteador, triagem  # noqa: E402

import kommo_client as kommo  # noqa: E402
import state  # noqa: E402
from config import KOMMO_RESPONSAVEL_ID, KOMMO_TOKEN, SDR_MODO  # noqa: E402

_MAPA_TTL = 600
_cache = {"mapa": None, "em": 0.0}
_vistas: dict[str, float] = {}
_avisados: dict[int, float] = {}
_INTERVALO_AVISO = 24 * 3600
_MOTIVOS_NAO_LEAD = ("MENSAGEM_AUTOMATICA", "SPAM_OU_OFERTA")


def modo() -> str:
    return SDR_MODO


def kommo_disponivel() -> bool:
    """Sem token não há Kommo (testes offline, VPS sem kommo.env)."""
    return bool(KOMMO_TOKEN) or _forcar_kommo


_forcar_kommo = False  # testes ligam com um Kommo falso


def mapa(forcar: bool = False) -> funil.Mapa:
    agora = time.time()
    if forcar or _cache["mapa"] is None or agora - _cache["em"] > _MAPA_TTL:
        _cache["mapa"] = funil.Mapa(kommo.list_pipelines())
        _cache["em"] = agora
    return _cache["mapa"]


class _Api:
    """O que o executor precisa. Resolve `kommo` na hora da chamada (os
    testes trocam o módulo por um falso)."""

    @staticmethod
    def move(lead_id, pipeline_id, status_id):
        kommo.move_lead(lead_id, pipeline_id, status_id)

    @staticmethod
    def add_tags(lead_id, tags):
        kommo.add_tags(lead_id, tags)

    @staticmethod
    def add_note(lead_id, texto):
        kommo.add_note(lead_id, texto)

    @staticmethod
    def add_task(lead_id, texto, prazo_ts, responsavel=None):
        kommo.add_task(lead_id, texto, prazo_ts, responsavel)


def _card(lead: dict, m: funil.Mapa) -> tuple[dict, dict]:
    local = m.localizar(lead.get("pipeline_id"), lead.get("status_id"))
    fechado_em = lead.get("closed_at")
    card = {
        "existe": True,
        # Funil que não é do SDR conta como fora do Comercial: com sinal
        # comercial a triagem diz "subir", e a ponte transforma em aviso.
        "zona": local["zona"] or regras.ENTRADA,
        "fechado": local["fechado"],
        "fechado_em": datetime.fromtimestamp(int(fechado_em), timezone.utc) if fechado_em else None,
        "etapa": local["etapa"],
    }
    return card, local


def _decidir(texto: str, card: dict, canal: str, midia: str | None, rota: dict | None):
    resultado = sdr.avaliar(texto or "", card=card, evento_extra={"canal": canal})
    decisao = resultado["triagem"]
    if not texto and midia:
        decisao = triagem.triar({"tipo": "mensagem"}, resultado["analise"], card)
    rota = rota or resultado["roteamento"]
    if rota["acao"] == roteador.ESCALAR:
        decisao = triagem.para_atendimento_humano(decisao, card)
    return decisao, rota


def _avisar_contato_antigo(lead: dict, decisao: dict, m: funil.Mapa, rota: dict) -> dict:
    """Card de funil que não é do SDR recebeu mensagem com sinal comercial:
    tarefa + nota para o responsável, uma vez por dia. O card fica onde está
    (o caso do relatório: lead parado em Contact list recebeu DM e nada
    disparou)."""
    lead_id = int(lead["id"])
    agora = time.time()
    if agora - _avisados.get(lead_id, 0) < _INTERVALO_AVISO:
        return _registrar(lead_id, {"ignorado": "AVISO_JA_ENVIADO"})
    _avisados[lead_id] = agora
    funil_nome = m.nome_funil(lead.get("pipeline_id"))
    feito = {"modo": modo(), "lead_id": lead_id, "acao": "avisar_contato_antigo",
             "motivo": decisao["motivo"], "funil": funil_nome, "moveu": None, "nota": True,
             "tarefa": {"prazo_min": regras.SLA_MINUTOS["media"]}}
    if executor.escreve(modo()):
        nota = (f"[SDR] contato antigo voltou a falar com sinal comercial ({decisao['motivo']}).\n"
                f"O card está em {funil_nome}; o SDR não move cards deste funil.")
        if rota.get("acao") == roteador.ESCALAR:
            nota += f"\nHANDOFF {rota['prioridade'].upper()}: {rota['descricao']}"
        kommo.add_note(lead_id, nota)
        kommo.add_task(lead_id, f"SDR: contato antigo voltou com sinal comercial ({decisao['motivo']})",
                       int(agora) + regras.SLA_MINUTOS["media"] * 60,
                       KOMMO_RESPONSAVEL_ID or lead.get("responsible_user_id"))
    return _registrar(lead_id, feito)


def triar_lead(lead_id: int, texto: str, canal: str = "", midia: str | None = None,
               rota: dict | None = None) -> dict:
    """Lê o card, decide e aplica (ou só registra, em observar). Síncrono;
    quem chama do caminho do lead usa triar_em_segundo_plano."""
    lead = kommo.get_lead(lead_id)
    m = mapa()
    card, local = _card(lead, m)

    if local["incoming"]:
        return _registrar(lead_id, {"ignorado": "INCOMING_LEADS"})

    if not local["do_sdr"]:
        decisao, rota = _decidir(texto, card, canal, midia, rota)
        if not decisao["entra_no_comercial"]:
            return _registrar(lead_id, {"ignorado": "FUNIL_FORA_DO_SDR", "pipeline_id": lead.get("pipeline_id")})
        return _avisar_contato_antigo(lead, decisao, m, rota)

    na_pagina1 = local["zona"] == regras.ENTRADA
    if na_pagina1 and not local["fechado"] and not local["gerenciada"] and not local["resgate"]:
        # Hot Leads, Closing the sale...: a equipe está trabalhando o card.
        return _registrar(lead_id, {"ignorado": "ETAPA_DA_EQUIPE", "etapa": local["etapa"]})

    decisao, rota = _decidir(texto, card, canal, midia, rota)

    # Card enterrado (resgate) ou fechado na página 1 só volta a andar se for
    # para subir ao Comercial.
    if na_pagina1 and (local["fechado"] or local["resgate"]) and not decisao["entra_no_comercial"]:
        return _registrar(lead_id, {"ignorado": "FECHADO_SEM_SINAL" if local["fechado"] else "RESGATE_SEM_SINAL",
                                    "motivo": decisao["motivo"]})

    feito = executor.aplicar(_Api, lead, decisao, m, modo(), roteamento=rota,
                             responsavel_id=KOMMO_RESPONSAVEL_ID or lead.get("responsible_user_id"),
                             segurar_na_entrada=na_pagina1 and local["gerenciada"])
    return _registrar(lead_id, feito)


def triar_lead_criado(lead_id: int, nome: str = "") -> dict:
    """Lead novo em First Contact com nome de lixo (assunto de e-mail de
    sistema, notificação): nao_e_lead antes da REGRA 1 carimbar DM. Qualquer
    outro lead novo é da equipe: nada a fazer."""
    lead = kommo.get_lead(lead_id)
    m = mapa()
    local = m.localizar(lead.get("pipeline_id"), lead.get("status_id"))
    if local["zona"] != regras.ENTRADA or not local["gerenciada"] or local["fechado"]:
        return _registrar(lead_id, {"ignorado": "FORA_DE_FIRST_CONTACT"})
    texto = str(lead.get("name") or nome or "").strip()
    if not texto:
        return _registrar(lead_id, {"ignorado": "SEM_NOME"})
    decisao = sdr.avaliar(texto, card={"existe": True, "zona": regras.ENTRADA},
                          evento_extra={"canal": "email"})["triagem"]
    if decisao["motivo"] not in _MOTIVOS_NAO_LEAD:
        return _registrar(lead_id, {"ignorado": "LEAD_DA_EQUIPE"})
    existentes = {t.get("name") for t in (lead.get("_embedded") or {}).get("tags", [])}
    novas = [t for t in dict.fromkeys(decisao["tags"]) if t not in existentes]
    if novas and executor.escreve(modo()):
        kommo.add_tags(lead_id, novas)
    return _registrar(lead_id, {"modo": modo(), "lead_id": lead_id, "acao": "marcar_nao_e_lead",
                                "motivo": decisao["motivo"], "tags": novas, "moveu": None})


def _registrar(lead_id: int, dados: dict) -> dict:
    state.log("sdr", lead_id, json.dumps(dados, ensure_ascii=False, default=str)[:1500])
    return dados


def triar_em_segundo_plano(lead_id: int, texto: str, rota: dict | None = None) -> None:
    if not kommo_disponivel():
        return

    def _rodar():
        try:
            triar_lead(lead_id, texto, rota=rota)
        except Exception as exc:  # o lead nunca paga por falha de organização
            state.log("error", lead_id, f"sdr: triagem do card falhou: {exc}")

    threading.Thread(target=_rodar, daemon=True).start()


def rotear(texto: str) -> dict:
    """Decisão antes do modelo (nível atender). Sem rede: só o texto."""
    return sdr.avaliar(texto or "")["roteamento"]


def confirmacao_opt_out(texto: str) -> str:
    return roteador.MENSAGEM_OPT_OUT[roteador.idioma(sdr.classificador.normalizar(texto))]


def mover_para(lead_id: int, etapa: str, motivo: str) -> None:
    """Move o card para uma etapa do Comercial (escalação, fechamento), em
    segundo plano e só nos níveis que escrevem. Card fora do Comercial não
    se move por aqui (na página 1 quem sobe é a REGRA 2 da equipe), e dentro
    dele o SDR só anda para frente."""
    if not kommo_disponivel():
        return

    def _rodar():
        try:
            m = mapa()
            lead = kommo.get_lead(lead_id)
            local = m.localizar(lead.get("pipeline_id"), lead.get("status_id"))
            dados = {"modo": modo(), "etapa": etapa, "motivo": motivo}
            pipeline, status = m.status_id(etapa, regras.COMERCIAL)
            atual = int(lead.get("status_id") or 0)
            ordem_atual, ordem_destino = m.ordem(pipeline, atual), m.ordem(pipeline, status)
            if local["zona"] != regras.COMERCIAL or not status:
                dados["ignorado"] = "FORA_DO_COMERCIAL" if local["zona"] != regras.COMERCIAL else "SEM_ETAPA"
            elif ordem_atual is not None and ordem_destino is not None and ordem_destino < ordem_atual:
                dados["ignorado"] = "NAO_VOLTA_ETAPA"
            elif atual != status and executor.escreve(modo()):
                kommo.move_lead(lead_id, pipeline, status)
                dados["moveu"] = etapa
            _registrar(lead_id, dados)
        except Exception as exc:
            state.log("error", lead_id, f"sdr: mover para {etapa} falhou: {exc}")

    threading.Thread(target=_rodar, daemon=True).start()


def ao_fechar(lead_id: int) -> None:
    """Trilha de follow-up esgotada (scheduler): card vai para
    PERDIDO / NÃO QUALIFICADO no Comercial."""
    mover_para(lead_id, regras.ETAPAS_COMERCIAL["PERDIDO"], "trilha de follow-up esgotada")


def limpar(lead_id: int, texto: str) -> str:
    """Guarda de estilo no que sai para o lead (nível atender)."""
    limpo, violacoes = estilo.aplicar(texto)
    if violacoes:
        state.log("gate", lead_id, "SDR estilo: " + ", ".join(violacoes))
    return limpo


def _primeira_vez(chave: str) -> bool:
    if not chave:
        return True
    if chave in _vistas:
        return False
    _vistas[chave] = time.time()
    if len(_vistas) > 2000:
        for velha in sorted(_vistas, key=_vistas.get)[:500]:
            _vistas.pop(velha, None)
    return True


def processar_eventos(payload: dict) -> list[dict]:
    """Webhook de conta do Kommo (mensagem recebida e lead criado). Nos
    níveis observar e organizar é por aqui que o SDR enxerga as conversas —
    sem Salesbot, sem responder ninguém."""
    saida = []
    for msg in evento.mensagens_recebidas(payload):
        chave = str(msg["id"] or "")
        if not _primeira_vez(chave):
            continue
        if not msg["lead_id"]:
            saida.append(_registrar(None, {"ignorado": "SEM_LEAD", "mensagem": chave}))
            continue
        try:
            saida.append(triar_lead(msg["lead_id"], msg["texto"], msg["canal"], msg["midia"]))
        except Exception as exc:
            state.log("error", msg["lead_id"], f"sdr: evento falhou: {exc}")
            saida.append({"erro": str(exc), "lead_id": msg["lead_id"]})
    for novo in evento.leads_criados(payload):
        if not _primeira_vez(f"lead-{novo['id']}"):
            continue
        try:
            saida.append(triar_lead_criado(novo["id"], novo["nome"]))
        except Exception as exc:
            state.log("error", novo["id"], f"sdr: lead criado falhou: {exc}")
            saida.append({"erro": str(exc), "lead_id": novo["id"]})
    return saida
