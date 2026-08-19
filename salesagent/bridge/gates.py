"""Portões — as regras que vivem abaixo do modelo (rules-to-code.md).

Um modelo que nunca recebe o número não pode ser convencido a dizê-lo.
"""
import re

from config import PROGRAM_LINKS, RATECARD
from state import get_conversation, log

# ---------------------------------------------------------------- G1: preço
# Refinado em 17/08 (documento Chase, decisão C1): o agente NUNCA fala um
# número em chat, para nenhum lead, em nenhum momento. get_price() não
# devolve mais valor monetário para uso conversacional — devolve o link
# da página do programa. O valor bruto continua em ratecard-2026.json para
# uso interno/CRM (nunca exposto por este endpoint).
_LINK_FIELD = {
    "one_day": "one_day_program_link",
    "monthly": "academy_link",
    "camp": "training_camp_link",
    "lead_and_follow": "program_link_generic",
    "corporate": "program_link_generic",
}


def get_price(lead_id: int, product: str, category: str) -> dict:
    """Única porta de saída de "preço" para o chat: devolve o LINK da
    página, nunca um número. Ainda bloqueia por idade quando aplicável."""
    conv = get_conversation(lead_id)
    age = conv["driver_age"]
    if age is not None and not age_eligible(age, category):
        log("gate", lead_id, f"G5 idade {age} inelegível para {category}")
        return {"status": "age_ineligible",
                "message": f"Idade {age} não é elegível para a categoria {category}."}
    link = PROGRAM_LINKS.get(_LINK_FIELD.get(product, ""))
    if not link:
        log("gate", lead_id, f"G1: link não configurado ({product}/{category})")
        return {"status": "unknown",
                "message": "Link do programa ainda não configurado — diga que vai confirmar e escale."}
    log("gate", lead_id, f"G1: link liberado ({product}/{category})")
    return {"status": "ok", "product": product, "category": category, "link": link,
            "notes": ["Nunca fale um preço em número no chat — use o link.",
                      "Driver pass e pit pass são pagos direto à pista — nunca inclusos.",
                      "Security deposit reembolsável sem dano ao kart."]}


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
    (r"\b(complaint|complain|reclama[çc][ãa]o|reclamar)\b", "reclamação"),
    (r"\b(media|press|imprensa|journalist|jornalista)\b", "mídia/imprensa"),
    (r"\b(talk to a human|speak to a person|falar com (um )?humano|falar com algu[ée]m da equipe)\b",
     "pediu para falar com humano"),
]


def escalation_triggers(text: str) -> list[str]:
    found = []
    low = text.lower()
    for pattern, reason in ESCALATION_PATTERNS:
        if re.search(pattern, low):
            found.append(reason)
    return found
