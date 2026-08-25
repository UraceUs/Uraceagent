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

    Duas rotas, tentadas nesta ordem, porque a conta real contradiz o que
    estava aqui até 25/08:

    1. POST /api/v4/salesbot/run  — corpo em LISTA, com bot_id dentro e
       entity_type NUMÉRICO (2 = leads). É a rota que casa com as duas
       evidências que temos da conta: o return_url que o widget manda vive
       em `/api/v4/salesbot/{bot}/continue/{id}`, e o JWT descartável do
       widget_request traz `"entity_type":"2"`.
    2. POST /api/v4/bots/{id}/run — o que este código chamava sozinho antes.
       Nunca foi exercitado de verdade (FOLLOWUP_BOT_ID sempre esteve vazio
       em produção), então nunca soubemos se responde nesta conta.

    Devolve True no primeiro 2xx. `probe_salesbot_run.py` resolve a dúvida
    empiricamente e diz qual das duas a conta aceita.
    """
    tentativas = [
        ("salesbot/run", f"{BASE}/salesbot/run",
         [{"bot_id": int(bot_id), "entity_id": lead_id, "entity_type": 2}]),
        ("bots/{id}/run", f"{BASE}/bots/{int(bot_id)}/run",
         {"entity_id": lead_id, "entity_type": "leads"}),
    ]
    ultimo = ""
    with _client() as c:
        for nome, url, body in tentativas:
            try:
                r = c.post(url, json=body)
            except Exception as exc:
                ultimo = f"{nome}: {exc}"
                continue
            if r.status_code < 300:
                _log_run_bot(f"rota {nome} OK (rc={r.status_code})")
                return True
            ultimo = f"{nome}: rc={r.status_code} {r.text[:160]}"
    _log_run_bot(f"nenhuma rota aceitou o disparo — último erro: {ultimo}")
    return False


def _log_run_bot(detalhe: str) -> None:
    """Registra qual rota funcionou. Import tardio de state para manter este
    módulo sem dependência de ciclo."""
    try:
        import state
        state.log("salesbot_run", None, detalhe)
    except Exception:
        pass
