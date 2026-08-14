"""Portões — as regras que vivem abaixo do modelo (rules-to-code.md).

Um modelo que nunca recebe o número não pode ser convencido a dizê-lo.
"""
import re

from config import RATECARD
from state import get_conversation, log

# ---------------------------------------------------------------- G1: preço
def price_gate_open(lead_id: int) -> bool:
    conv = get_conversation(lead_id)
    return bool(conv["q_experience"]) and bool(conv["q_origin"])


def get_price(lead_id: int, product: str, category: str) -> dict:
    """Única porta de saída de preço. Fecha por qualificação e por idade."""
    if not price_gate_open(lead_id):
        log("gate", lead_id, f"G1 fechado: preço negado ({product}/{category})")
        return {"status": "gate_closed",
                "message": "Qualifique primeiro: experiência do driver e origem (local/traveler)."}
    conv = get_conversation(lead_id)
    age = conv["driver_age"]
    if age is not None and not age_eligible(age, category):
        log("gate", lead_id, f"G5 idade {age} inelegível para {category}")
        return {"status": "age_ineligible",
                "message": f"Idade {age} não é elegível para a categoria {category}."}
    table = {
        "one_day": RATECARD.get("academy_daily", {}),
        "monthly": RATECARD.get("academy_monthly_no_contract", {}),
        "camp": RATECARD.get("summer_camp", {}),
        "lead_and_follow": RATECARD.get("lead_and_follow", {}),
        "corporate": RATECARD.get("corporate_event", {}),
    }.get(product)
    if not table or category not in table:
        log("gate", lead_id, f"G8 sem preço na base: {product}/{category}")
        return {"status": "unknown",
                "message": "Preço não disponível na base — diga que vai confirmar e escale."}
    entry = table[category]
    log("gate", lead_id, f"preço liberado: {product}/{category}")
    return {"status": "ok", "product": product, "category": category, "price": entry,
            "notes": ["Driver pass e pit pass são pagos direto à pista — nunca inclusos.",
                      "Security deposit de $400, reembolsável sem dano."]}


# ---------------------------------------------------------------- G5: idade
def age_eligible(age: int, category: str) -> bool:
    """Decisão C7: faixas universais. baby_kart 4–7; demais 7+; shifter 14+; <4 inelegível."""
    if age < 4:
        return False
    cat = category.lower()
    if "baby" in cat:
        return 4 <= age <= 7
    if "shifter" in cat:
        return age >= 14
    if "own" in cat:
        return age >= 4
    return age >= 7


# ---------------------------------------------------------------- G2: roteamento
def routing(experience: str) -> str:
    """competes → Italo (escala). Recreativo/primeira vez → agente."""
    return "escalate_to_owner" if experience == "competes" else "agent"


# ---------------------------------------------------------------- B4: gatilhos de escalação
ESCALATION_PATTERNS = [
    (r"\b(discount|desconto|cheaper|price match|coupon)\b", "pedido de desconto"),
    (r"\b(refund|reembolso|money back|chargeback)\b", "pedido de refund/chargeback"),
    (r"\b(lawyer|legal|sue|advogado|processo)\b", "ameaça legal"),
    (r"\b(injur|hurt|accident|lesão|machuc)\b", "menção a lesão/incidente"),
    (r"\b(sponsor|patroc[íi]nio|partnership|parceria)\b", "patrocínio/parceria"),
    (r"\b(racing team|race team|corrida profissional)\b", "interesse em Racing Team"),
    (r"\b(custody|guarda|ex[- ]?(wife|husband|marido|esposa))\b", "questão de custódia"),
    (r"\b(own kart|meu kart|kart pr[óo]prio)\b", "kart próprio (inspeção/gestão)"),
]


def escalation_triggers(text: str) -> list[str]:
    found = []
    low = text.lower()
    for pattern, reason in ESCALATION_PATTERNS:
        if re.search(pattern, low):
            found.append(reason)
    return found
