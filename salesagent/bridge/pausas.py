"""Conversas com a IA pausada (dono, 13/10: "ter a possibilidade de desativar pelo command
center ... respostas da IA em uma conversa específica").

Quem pausa é a equipe, no Command Center (página Robô SDR ou o chat do Kommo). O painel grava
~/.urace/sdr_pausas.json com escrita atômica, uma chave por lead do Kommo:

    {"31764961": {"por": "Lucas", "em": "2026-10-13T11:02:00-04:00", "motivo": "..."}}

A ponte lê o arquivo a cada mensagem (é pequeno). Conversa pausada não recebe resposta, nem
follow-up, nem resgate; o card continua sendo organizado. Arquivo ausente ou ilegível = nenhuma
pausa: a ponte segue respondendo, e a falha de leitura fica no log.
"""
import json

import state
from config import URACE_DIR

ARQUIVO = "sdr_pausas.json"


def pausadas() -> dict:
    f = URACE_DIR / ARQUIVO
    try:
        dados = json.loads(f.read_text(encoding="utf-8") or "{}")
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        state.log("error", None, f"sdr_pausas: {exc}")
        return {}
    return dados if isinstance(dados, dict) else {}


def ia_pausada(lead_id) -> bool:
    if not lead_id:
        return False
    return str(int(lead_id)) in pausadas()


# 14/10 (atendimento humano): a IA só fala em conversa que é dela. Pausa (manual ou caso aberto no
# Command Center) e estado escalado da ponte travam, cada um sozinho: se o painel cair antes de
# escrever a pausa, o estado local já trava; se o estado local se perder, a pausa trava.
ESTADOS_DA_IA = ("AI_ACTIVE", "RESUMED")


def ia_pode_enviar(lead_id) -> tuple[bool, str]:
    """A última pergunta antes de QUALQUER mensagem automática sair (resposta, follow-up,
    resgate, entrega pendente). Mensagem humana não passa por aqui."""
    if not lead_id:
        return False, "sem lead"
    if ia_pausada(lead_id):
        entrada = pausadas().get(str(int(lead_id))) or {}
        caso = entrada.get("handoff") if isinstance(entrada, dict) else None
        return False, (f"atendimento humano aberto (caso #{caso})" if caso
                       else "IA pausada nesta conversa (Command Center)")
    atual = state.get_conversation(int(lead_id))["state"]
    if atual not in ESTADOS_DA_IA:
        return False, f"conversa em {atual}: quem responde é uma pessoa"
    return True, ""
