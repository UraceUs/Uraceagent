"""Webhook de conta do Kommo ("mensagem recebida") -> mensagens do lead.

O Kommo manda form-urlencoded com colchetes (message[add][0][text]); a ponte
já desdobra isso em dicionário (_parse_hook_body). Aqui só se extrai o que
interessa, e só mensagens que o lead mandou (type=incoming).
"""


def _itens(valor):
    if isinstance(valor, list):
        return valor
    if isinstance(valor, dict):
        return [valor[k] for k in sorted(valor, key=lambda k: str(k))]
    return []


def canal_por_origem(origem):
    o = str(origem or "").lower()
    if "whats" in o or "waba" in o or o.startswith("wa"):
        return "whatsapp"
    if "insta" in o:
        return "instagram"
    if "facebook" in o or "messenger" in o or o == "fb":
        return "messenger"
    if "telegram" in o:
        return "telegram"
    if "mail" in o:
        return "email"
    return "site"


def mensagens_recebidas(payload):
    msg = (payload or {}).get("message") or {}
    saida = []
    for m in _itens(msg.get("add")):
        if not isinstance(m, dict):
            continue
        if m.get("type") and m.get("type") != "incoming":
            continue
        tipo_entidade = str(m.get("element_type") or m.get("entity_type") or "")
        lead_id = m.get("element_id") or m.get("entity_id") if tipo_entidade in ("2", "lead", "leads") else None
        anexo = m.get("attachment")
        saida.append({
            "id": m.get("id"),
            "texto": m.get("text") or "",
            "lead_id": int(lead_id) if lead_id and str(lead_id).isdigit() else None,
            "canal": canal_por_origem(m.get("origin")),
            "midia": (anexo.get("type") if isinstance(anexo, dict) else None) or ("anexo" if anexo else None),
        })
    return saida
