"""Diagnóstico (17/09): o lead CRU como a API do Kommo devolve, para achar onde mora o perfil
do Instagram/Facebook que o Kommo mostra em "Open profile". Só leitura; imprime JSON.

Uso (no VPS):  python3 adminai/kommo_cru.py <lead_id>
Lê ~/.urace/kommo.env. Corta valores longos; nunca imprime o token."""
import json
import sys
import urllib.parse

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from adminai.mcp import kommo_mcp as k  # noqa: E402


def _corta(o, n=300):
    if isinstance(o, dict):
        return {a: _corta(b, n) for a, b in o.items() if a != "_links"}
    if isinstance(o, list):
        return [_corta(x, n) for x in o[:12]]
    if isinstance(o, str) and len(o) > n:
        return o[:n] + "…"
    return o


def _tenta(rotulo, caminho, params=None):
    try:
        r = k._req(caminho, params=params)
        print(f"\n### {rotulo}  GET {caminho}{'?' + urllib.parse.urlencode(params, doseq=True) if params else ''}")
        print(json.dumps(_corta(r), ensure_ascii=False, indent=1))
        return r or {}
    except Exception as e:  # noqa: BLE001
        print(f"\n### {rotulo}  GET {caminho} → {str(e)[:200]}")
        return {}


def main(lead_id):
    k._carregar_env()
    lead = _tenta("LEAD", f"/leads/{int(lead_id)}", {"with": "contacts,source_id,loss_reason"})
    ids = [c.get("id") for c in ((lead.get("_embedded") or {}).get("contacts") or []) if c.get("id")]
    for cid in ids[:2]:
        _tenta("CONTATO", f"/contacts/{cid}", {"with": "leads,catalog_elements"})
        _tenta("CHATS DO CONTATO", "/contacts/chats", {"contact_id": cid})
    evs = _tenta("EVENTOS (últimos 6)", "/events", {"filter[entity][]": "lead", "filter[entity_id][]": int(lead_id), "limit": 6})
    talks = set()
    for ev in ((evs.get("_embedded") or {}).get("events") or []):
        va = ev.get("value_after") or []
        a0 = va[0] if isinstance(va, list) and va and isinstance(va[0], dict) else {}
        m = a0.get("message") or {}
        if isinstance(m, dict) and m.get("talk_id"):
            talks.add(m["talk_id"])
        if ev.get("entity_type") == "talk":
            talks.add(ev.get("entity_id"))
    for t in list(talks)[:2]:
        _tenta("TALK", f"/talks/{int(t)}")
    _tenta("CAMPOS DO CONTATO (definições)", "/contacts/custom_fields", {"limit": 50})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("uso: python3 adminai/kommo_cru.py <lead_id>")
    main(sys.argv[1])
