"""Configuração da sales-bridge. Lê segredos de ~/.urace/, nunca do repositório."""
import json
import os
from pathlib import Path

URACE_DIR = Path(os.environ.get("URACE_DIR", Path.home() / ".urace"))
REPO_DIR = Path(__file__).resolve().parent.parent  # salesagent/


def _load_env_file(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_kommo = _load_env_file(URACE_DIR / "kommo.env")
_bridge = _load_env_file(URACE_DIR / "bridge.env")

KOMMO_TOKEN = _kommo.get("KOMMO_TOKEN", "")
KOMMO_DOMAIN = _kommo.get("KOMMO_DOMAIN", "urace.kommo.com").rstrip("/")
# Client secret da integração privada (aba "Keys and scopes" no Kommo).
# Opcional: quando presente, a ponte valida a assinatura HS512 do JWT
# descartável que o widget_request envia (defesa em profundidade além do
# ?key= na URL). Vazio = validação desligada.
KOMMO_BOT_SECRET = _kommo.get("KOMMO_BOT_SECRET", "")

# Chave que autentica o agente OpenClaw (e o Salesbot) na ponte
AGENT_API_KEY = _bridge.get("AGENT_API_KEY", "")
# Números autorizados a aprovar escalações (WhatsApp interno). Aceita LISTA
# separada por vírgula — até 25/08 era um número só (o do Italo), e por isso
# o Eduardo, que o brief lista como autoridade, nunca recebia escalação
# nenhuma. HUMAN_WHATSAPP segue existindo como o primeiro da lista para não
# quebrar chamador antigo.
HUMAN_WHATSAPP_LIST = [n.strip() for n in
                       _bridge.get("HUMAN_WHATSAPP", "+14074878143").split(",")
                       if n.strip()]
HUMAN_WHATSAPP = HUMAN_WHATSAPP_LIST[0] if HUMAN_WHATSAPP_LIST else ""
# Horário comercial para alarmes de escalação (decisão C2)
BUSINESS_TZ = "America/New_York"
BUSINESS_HOURS = (9, 18)
ESCALATION_REALERT_MIN = int(_bridge.get("ESCALATION_REALERT_MIN", "15"))  # 10–30
# Id do Salesbot (chase-bridge) para ENTREGA de follow-up espontâneo: o
# agendador dispara o bot via POST /api/v4/bots/{id}/run e a ponte devolve o
# texto pendente pelo return_url. Vazio = fallback nota+tarefa no Kommo.
FOLLOWUP_BOT_ID = _bridge.get("FOLLOWUP_BOT_ID", "")
# Sales Brain (retrieval de conhecimento do vault brain/):
#   "off" (default) — ponte funciona exatamente como antes, zero mudança
#   "on"            — injeta memória do lead + conhecimento relevante como
#                     contexto [SYSTEM] em cada turno, e habilita a diretiva
#                     [[kb query="..."]]. Rollback = remover a linha do env.
BRAIN_RETRIEVAL = _bridge.get("BRAIN_RETRIEVAL", "off").lower()
BRAIN_TOP_DOCS = int(_bridge.get("BRAIN_TOP_DOCS", "3"))

# Como a resposta chega no chat do lead:
#   "balloons"   — sequência de handlers `show` de <=80 chars (funciona com o
#                  widget v1; limite de 80 validado ao vivo em 24/08)
#   "json_reply" — a resposta inteira vai no campo data.reply e o PRÓPRIO BOT
#                  a exibe via {{json.reply}} (exige widget v2 + bot re-salvo;
#                  uma mensagem única, sem limite de 80)
SALESBOT_DISPLAY = _bridge.get("SALESBOT_DISPLAY", "balloons")

DB_PATH = URACE_DIR / "salesbridge.db"

# Autoridade humana (§3): identidade e escopo vêm do repo, contato vem do env.
_operators_path = REPO_DIR / "config" / "human-operators.json"
HUMAN_OPERATORS = (json.loads(_operators_path.read_text())
                   if _operators_path.exists() else {"operators": [], "rules": {}})
OPERATOR_RULES = HUMAN_OPERATORS.get("rules", {})

RATECARD = json.loads((REPO_DIR / "config" / "ratecard-2026.json").read_text())
PROGRAM_LINKS = json.loads((REPO_DIR / "config" / "program-links.json").read_text())
CHECKIN_TEMPLATE = (REPO_DIR / "config" / "checkin-template.md").read_text()

# Pipeline ativo: prefere o pipeline dedicado do Chase (criado via
# create_chase_pipeline.py) se existir; senão cai no "Sales funnel" original.
_chase_pipeline_path = REPO_DIR / "config" / "kommo-pipeline-chase.json"
_pipeline_path = (_chase_pipeline_path if _chase_pipeline_path.exists()
                  else REPO_DIR / "config" / "kommo-pipeline.json")
PIPELINE = json.loads(_pipeline_path.read_text())
PIPELINE_SOURCE = _pipeline_path.name

STAGES = {k: v["id"] for k, v in PIPELINE["stages"].items()}
PIPELINE_ID = PIPELINE["pipeline_id"]
