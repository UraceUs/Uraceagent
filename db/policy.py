"""
Predicados puros dos portões — zero dependências, importável em qualquer modo.

Separado de gates.py por uma razão operacional: o dry-run do orchestrator e o
self-test do indexador provam a lógica SEM banco e sem SDK instalado. gates.py
importa o SDK do Firestore; este módulo não importa nada.

Uma definição, dois consumidores (gates.py e agent/tools_impl.py). A lista de
campos obrigatórios espelha configurations/price_policy e closing — mudou lá,
muda aqui, e o test_gates.py confere os dois lados.
"""

from __future__ import annotations

REQUIRED_FOR_PRICE = [
    "for_whom", "driver_age", "origin", "goal", "experience_level",
]

REQUIRED_FOR_SCHEDULING = [
    "driver_name", "driver_age", "origin", "contact_phone",
    "availability_window",
]


def missing_fields(qual: dict, required: list[str]) -> list[str]:
    return [f for f in required if not qual.get(f)]


def price_disclosure_allowed(qual: dict, price_requested: bool) -> tuple[bool, str]:
    """As duas condições, avaliadas em código. Nenhuma é juízo do modelo."""
    if not price_requested:
        return False, "the driver has not asked for a price"
    gaps = missing_fields(qual, REQUIRED_FOR_PRICE)
    if gaps:
        return False, f"qualification incomplete: missing {', '.join(gaps)}"
    return True, "qualification complete and the driver asked"
