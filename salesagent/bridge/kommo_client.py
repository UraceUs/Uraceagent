"""Cliente mínimo da API v4 do Kommo. O Kommo é o single source of truth comercial."""
import httpx

from config import KOMMO_DOMAIN, KOMMO_TOKEN, PIPELINE_ID

BASE = f"https://{KOMMO_DOMAIN}/api/v4"
HEADERS = {"Authorization": f"Bearer {KOMMO_TOKEN}"}


def _client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=15)


def get_lead(lead_id: int) -> dict:
    with _client() as c:
        r = c.get(f"{BASE}/leads/{lead_id}", params={"with": "contacts"})
        r.raise_for_status()
        return r.json()


def update_lead(lead_id: int, fields: dict) -> dict:
    with _client() as c:
        r = c.patch(f"{BASE}/leads/{lead_id}", json=fields)
        r.raise_for_status()
        return r.json()


def set_stage(lead_id: int, status_id: int) -> dict:
    return update_lead(lead_id, {"pipeline_id": PIPELINE_ID, "status_id": status_id})


def add_note(lead_id: int, text: str) -> None:
    with _client() as c:
        r = c.post(
            f"{BASE}/leads/{lead_id}/notes",
            json=[{"note_type": "common", "params": {"text": text[:20000]}}],
        )
        r.raise_for_status()


def add_task(lead_id: int, text: str, complete_till_ts: int) -> None:
    """Cria a próxima tarefa do lead (regra B2: nenhum lead sem próxima ação)."""
    with _client() as c:
        r = c.post(
            f"{BASE}/tasks",
            json=[{
                "entity_id": lead_id,
                "entity_type": "leads",
                "text": text[:500],
                "complete_till": complete_till_ts,
            }],
        )
        r.raise_for_status()


def add_tags(lead_id: int, tags: list[str]) -> None:
    with _client() as c:
        r = c.patch(
            f"{BASE}/leads/{lead_id}",
            json={"_embedded": {"tags": [{"name": t} for t in tags]}},
        )
        r.raise_for_status()


def run_bot(bot_id: str | int, lead_id: int) -> bool:
    """Dispara um Salesbot num lead — usado pelo agendador para entregar
    follow-up (e resposta de humano) pelo mesmo circuito do chat.

    A rota foi CONFIRMADA contra a conta real em 25/08
    (`tools/probe_salesbot_run.py --bot 162247`), depois de ter ficado dois
    meses como suposição não exercitada (FOLLOWUP_BOT_ID sempre vazio em
    produção, então o agendador caía direto no fallback de nota e ninguém
    nunca soube se respondia). O probe testou as quatro combinações:

        POST /api/v4/bots/{id}/run  {"entity_type": "leads"}  -> 202  ✅
        POST /api/v4/bots/{id}/run  {"entity_type": 2}        -> 400 (InvalidType)
        POST /api/v4/salesbot/run   (lista)                   -> 404 (rota não existe)
        POST /api/v4/salesbot/run   (objeto)                  -> 404

    Ou seja: `entity_type` é STRING aqui, mesmo o JWT do widget_request
    trazendo `"2"` e o return_url vivendo em `/api/v4/salesbot/...`. As duas
    pistas apontavam para a rota errada — por isso o probe existe, e por isso
    ele continua no repo: se a conta mudar, ele responde de novo em 10s.
    """
    with _client() as c:
        r = c.post(f"{BASE}/bots/{int(bot_id)}/run",
                   json={"entity_id": lead_id, "entity_type": "leads"})
        ok = r.status_code < 300
        if not ok:
            _log_run_bot(f"disparo do bot {bot_id} no lead {lead_id} recusado: "
                         f"rc={r.status_code} {r.text[:200]}")
        return ok


def _log_run_bot(detalhe: str) -> None:
    """Registra falha de disparo. Import tardio de state para manter este
    módulo sem dependência de ciclo."""
    try:
        import state
        state.log("salesbot_run", None, detalhe)
    except Exception:
        pass
