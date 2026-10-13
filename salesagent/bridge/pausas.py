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
