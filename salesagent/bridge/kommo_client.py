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
    """Dispara um Salesbot num lead (POST /api/v4/bots/{id}/run) — usado pelo
    agendador para entregar follow-up espontâneo pelo mesmo circuito do chat.
    Status/corpo logados pelo chamador; devolve sucesso (2xx)."""
    with _client() as c:
        r = c.post(f"{BASE}/bots/{int(bot_id)}/run",
                   json={"entity_id": lead_id, "entity_type": "leads"})
        return r.status_code < 300
