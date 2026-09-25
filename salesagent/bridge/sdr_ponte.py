"""Ponte ↔ SDR: liga o pacote salesagent/sdr ao Kommo real, ao estado e à
auditoria da sales-bridge.

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
        "zona": local["zona"],
        "fechado": local["fechado"],
        "fechado_em": datetime.fromtimestamp(int(fechado_em), timezone.utc) if fechado_em else None,
        "etapa": local["etapa"],
    }
    return card, local


def triar_lead(lead_id: int, texto: str, canal: str = "", midia: str | None = None,
               rota: dict | None = None) -> dict:
    """Lê o card, decide e aplica (ou só registra, em observar). Síncrono;
    quem chama do caminho do lead usa triar_em_segundo_plano."""
    lead = kommo.get_lead(lead_id)
    m = mapa()
    card, local = _card(lead, m)

    if not local["do_sdr"]:
        return _registrar(lead_id, {"ignorado": "FORA_DO_NOVO_FUNIL", "pipeline_id": lead.get("pipeline_id")})
    if local["incoming"]:
        return _registrar(lead_id, {"ignorado": "INCOMING_LEADS"})
    if local["zona"] is None:
        # Etapa criada à mão no Novo funil: é da equipe, não do robô.
        return _registrar(lead_id, {"ignorado": "ETAPA_DA_EQUIPE", "status_id": lead.get("status_id")})

    resultado = sdr.avaliar(texto or "", card=card, evento_extra={"canal": canal})
    decisao = resultado["triagem"]
    if not texto and midia:
        decisao = triagem.triar({"tipo": "mensagem"}, resultado["analise"], card)
    rota = rota or resultado["roteamento"]
    if rota["acao"] == roteador.ESCALAR:
        decisao = triagem.para_atendimento_humano(decisao, card)

    # Perdido na triagem só volta se for para venda.
    if local["zona"] == regras.ENTRADA and local["fechado"] and not decisao["entra_no_comercial"]:
        return _registrar(lead_id, {"ignorado": "FECHADO_SEM_SINAL", "motivo": decisao["motivo"]})

    feito = executor.aplicar(_Api, lead, decisao, m, modo(), roteamento=rota,
                             responsavel_id=KOMMO_RESPONSAVEL_ID or lead.get("responsible_user_id"))
    return _registrar(lead_id, feito)


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
    """Move o card para uma etapa do Novo funil (escalação, fechamento),
    em segundo plano e só nos níveis que escrevem."""
    if not kommo_disponivel():
        return

    def _rodar():
        try:
            m = mapa()
            lead = kommo.get_lead(lead_id)
            local = m.localizar(lead.get("pipeline_id"), lead.get("status_id"))
            dados = {"modo": modo(), "etapa": etapa, "motivo": motivo}
            status = m.status_id(etapa)
            if not local["do_sdr"] or local["zona"] is None or not status:
                dados["ignorado"] = "FORA_DO_NOVO_FUNIL" if not local["do_sdr"] else "SEM_ETAPA"
            elif int(lead.get("status_id") or 0) != status and executor.escreve(modo()):
                kommo.move_lead(lead_id, m.pipeline_id, status)
                dados["moveu"] = etapa
            _registrar(lead_id, dados)
        except Exception as exc:
            state.log("error", lead_id, f"sdr: mover para {etapa} falhou: {exc}")

    threading.Thread(target=_rodar, daemon=True).start()


def ao_fechar(lead_id: int) -> None:
    """Trilha de follow-up esgotada (scheduler): card vai para Perdido."""
    mover_para(lead_id, regras.ETAPAS_COMERCIAL["PERDIDO"], "trilha de follow-up esgotada")


def limpar(lead_id: int, texto: str) -> str:
    """Guarda de estilo no que sai para o lead (nível atender)."""
    limpo, violacoes = estilo.aplicar(texto)
    if violacoes:
        state.log("gate", lead_id, "SDR estilo: " + ", ".join(violacoes))
    return limpo


def processar_eventos(payload: dict) -> list[dict]:
    """Webhook de conta do Kommo (mensagem recebida). Nos níveis observar e
    organizar é por aqui que o SDR enxerga as conversas — sem Salesbot, sem
    responder ninguém."""
    saida = []
    for msg in evento.mensagens_recebidas(payload):
        chave = str(msg["id"] or "")
        if chave and chave in _vistas:
            continue
        if chave:
            _vistas[chave] = time.time()
            if len(_vistas) > 2000:
                for velha in sorted(_vistas, key=_vistas.get)[:500]:
                    _vistas.pop(velha, None)
        if not msg["lead_id"]:
            saida.append(_registrar(None, {"ignorado": "SEM_LEAD", "mensagem": chave}))
            continue
        try:
            saida.append(triar_lead(msg["lead_id"], msg["texto"], msg["canal"], msg["midia"]))
        except Exception as exc:
            state.log("error", msg["lead_id"], f"sdr: evento falhou: {exc}")
            saida.append({"erro": str(exc), "lead_id": msg["lead_id"]})
    return saida
