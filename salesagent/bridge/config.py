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

# Chave que autentica o agente OpenClaw (e o Salesbot) na ponte
AGENT_API_KEY = _bridge.get("AGENT_API_KEY", "")
# Número autorizado a aprovar escalações (WhatsApp interno)
HUMAN_WHATSAPP = _bridge.get("HUMAN_WHATSAPP", "+14074878143")
# Horário comercial para alarmes de escalação (decisão C2)
BUSINESS_TZ = "America/New_York"
BUSINESS_HOURS = (9, 18)
ESCALATION_REALERT_MIN = int(_bridge.get("ESCALATION_REALERT_MIN", "15"))  # 10–30

DB_PATH = URACE_DIR / "salesbridge.db"

RATECARD = json.loads((REPO_DIR / "config" / "ratecard-2026.json").read_text())
PIPELINE = json.loads((REPO_DIR / "config" / "kommo-pipeline.json").read_text())
CHECKIN_TEMPLATE = (REPO_DIR / "config" / "checkin-template.md").read_text()

STAGES = {k: v["id"] for k, v in PIPELINE["stages"].items()}
PIPELINE_ID = PIPELINE["pipeline_id"]
