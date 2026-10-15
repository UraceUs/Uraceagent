"""Webhook de conta do Kommo -> mensagens do lead e leads criados.

O Kommo manda form-urlencoded com colchetes (message[add][0][text],
leads[add][0][name]); a ponte já desdobra isso em dicionário
(_parse_hook_body). Aqui só se extrai o que interessa: mensagens que o lead
mandou (type=incoming) e leads novos (para marcar lixo do Inbox de e-mail
antes da REGRA 1 da equipe).
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


def leads_criados(payload):
    leads = (payload or {}).get("leads") or {}
    saida = []
    for lead in _itens(leads.get("add")):
        if not isinstance(lead, dict) or not str(lead.get("id") or "").isdigit():
            continue
        saida.append({"id": int(lead["id"]), "nome": lead.get("name") or ""})
    return saida


def mensagens_enviadas(payload):
    """Mensagens que SAÍRAM (type diferente de incoming) pelo webhook de conta. Só para observar: o
    Kommo manda aqui o que o robô, o Salesbot, uma automação e uma pessoa da equipe escrevem, e ainda
    não sabemos separar quem é quem pelo payload. A ponte registra o formato (sem o texto inteiro) até
    existir um sinal confiável de "uma pessoa escreveu"; por enquanto a pausa é do botão Pausar IA e
    da etapa ATENDIMENTO."""
    msg = (payload or {}).get("message") or {}
    saida = []
    for m in _itens(msg.get("add")):
        if not isinstance(m, dict) or not m.get("type") or m.get("type") == "incoming":
            continue
        autor = m.get("author") if isinstance(m.get("author"), dict) else {}
        lead_id = m.get("element_id") or m.get("entity_id")
        saida.append({
            "lead_id": int(lead_id) if lead_id and str(lead_id).isdigit() else None,
            "tipo": str(m.get("type")),
            "autor_tipo": str(autor.get("type") or m.get("author_type") or ""),
            "autor_id": str(autor.get("id") or m.get("created_by") or ""),
            "origem": str(m.get("origin") or ""),
            "inicio": (m.get("text") or "")[:40],
        })
    return saida
