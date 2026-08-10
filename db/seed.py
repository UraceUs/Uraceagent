#!/usr/bin/env python3
"""
Seed de configuração — cada decisão da URace, como dado.

Port do 002_seed_config.sql. Mudar qualquer valor destes é um write no
Firestore, nunca um deploy. Estrutura: um documento por categoria em
`configurations/{category}`, campos = keys.

Uso:
    python db/seed.py --dry-run      # mostra o que escreveria
    python db/seed.py                # aplica (idempotente: merge)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CONFIGURATIONS: dict[str, dict] = {
    # -------------------------------------------------------------------------
    # BUSINESS HOURS (Orlando — America/New_York)
    # -------------------------------------------------------------------------
    "business_hours": {
        "timezone": "America/New_York",
        "support_hours": {
            "monday":    {"open": "09:00", "close": "18:00"},
            "tuesday":   {"open": "09:00", "close": "18:00"},
            "wednesday": {"open": "09:00", "close": "18:00"},
            "thursday":  {"open": "09:00", "close": "18:00"},
            "friday":    {"open": "09:00", "close": "18:00"},
            "saturday":  {"open": "08:00", "close": "12:00"},
            "sunday":    {"open": "08:00", "close": "12:00"},
        },
        # Fim de semana tem equipe, mas ligação é oferecida em dia útil.
        "preferred_booking_days": ["monday", "tuesday", "wednesday",
                                   "thursday", "friday"],
        "out_of_hours_policy": {
            "auto_confirm": False,
            "action": "create_human_approval",
            "message_intent": "tell the driver the team will confirm availability",
        },
    },
    # -------------------------------------------------------------------------
    # LEAD SCORING (pesos somam 100)
    # -------------------------------------------------------------------------
    "scoring_rules": {
        "weights": {
            "urgency": 25, "budget_fit": 20, "program_defined": 15,
            "driver_profile_fit": 15, "engagement": 15,
            "scheduling_readiness": 10,
        },
        "thresholds": {"hot": 70, "warm": 40},
        # Sinais de capacidade observados NA CONVERSA. Deliberadamente não
        # inferidos de perfil social: o erro caro é o falso negativo — o pai
        # quieto que gasta milhares por mês.
        "budget_signals": {
            "asks_about_monthly_or_contract": "high",
            "travels_from_out_of_state": "high",
            "owns_a_kart": "high",
            "asks_about_championship_season": "high",
            "no_reaction_to_price": "high",
            "asks_only_cheapest_option": "low",
            "raises_price_objection_twice": "low",
        },
        "config_version": "2026-07-28.1",
    },
    # -------------------------------------------------------------------------
    # PRICE DISCLOSURE
    # -------------------------------------------------------------------------
    "price_policy": {
        "disclosure_gate": {
            "proactive_quoting": False,
            "requires_explicit_request": True,
            "requires_qualification_complete": True,
            "requires_lead_score_minimum": None,
            "one_price_at_a_time": True,
            "value_framing_before_number": True,
        },
        "qualification_required_fields": [
            "for_whom", "driver_age", "origin", "goal", "experience_level"],
        "mandatory_disclaimer": {
            "track_fees": "driver pass and pit pass are paid directly to "
                          "Orlando Kart Center",
            "never_say": ["all-inclusive", "everything included"],
        },
        # O agente informa que add-ons existem; nunca computa um total.
        "agent_computes_totals": False,
    },
    # -------------------------------------------------------------------------
    # CLOSING PATH
    # -------------------------------------------------------------------------
    "closing": {
        "routing": {
            "call_with_owner": {
                "conditions": ["origin = local",
                               "wants_recurring_commitment = true"],
                "action": "schedule call and hand off to owner",
            },
            "chat_close": {
                "conditions": ["single day or low commitment"],
                "action": "close in chat, then create human task to "
                          "finalise payment",
            },
        },
        "required_before_scheduling": [
            "responsible_name", "driver_name", "driver_age", "origin",
            "contact_phone", "availability_window"],
        "agent_takes_payment": False,
    },
    # -------------------------------------------------------------------------
    # FOLLOW-UP
    # -------------------------------------------------------------------------
    "follow_up": {
        "intervals_hours": [24, 72, 168],
        "max_attempts": 3,
        "close_reason_after_max": "no_response",
        "hard_stops": [
            "lead_escalated",
            "lead_asked_not_to_be_contacted",
            "personal_hardship_disclosed",
            "channel_messaging_window_closed",
        ],
    },
    # -------------------------------------------------------------------------
    # ESCALATION
    # -------------------------------------------------------------------------
    "escalation": {
        "keywords_en": ["discount", "refund", "cancel", "complaint",
                        "manager", "lawyer", "chargeback",
                        "speak to a human", "real person"],
        "keywords_pt": ["desconto", "reembolso", "cancelar", "reclamação",
                        "gerente", "advogado", "falar com humano",
                        "pessoa de verdade"],
        "keywords_es": ["descuento", "reembolso", "cancelar", "queja",
                        "gerente", "abogado", "hablar con una persona"],
        "always_escalate": ["payment", "discount_request", "complaint",
                            "personal_hardship"],
        "rag_confidence_threshold": 0.72,
        # Escalado fica em silêncio até um humano devolver.
        "agent_resumes_automatically": False,
    },
    # -------------------------------------------------------------------------
    # CATALOG SYNC
    # -------------------------------------------------------------------------
    "catalog_sync": {
        "sheet_tabs": {"segments": "_segments", "programs": "_programs",
                       "offers": "_offers"},
        "interval_minutes": 15,
        "on_row_error": "reject_row_and_report",
        "on_missing_row": "set_inactive",
        "on_sheet_unavailable": "keep_last_good_and_alert",
    },
    # -------------------------------------------------------------------------
    # SAFETY
    # -------------------------------------------------------------------------
    "safety": {
        "age_gate": {
            "below_program_threshold": "create_human_approval",
            "agent_may_confirm": False,
            "agent_may_refuse": False,
            "must_collect": ["driver_age", "driver_experience"],
            "rationale_to_driver": "clearance depends on the child's size "
                                   "and is checked by the team",
        },
        # Campo vazio no catálogo = "não avalie", nunca "assuma algo sensato".
        "empty_field_policy": {
            "age_min": "do_not_filter_by_age",
            "segment_id": "exclude_from_automatic_recommendation",
            "recommended_level": "do_not_filter_by_level",
            "description": "do_not_describe_program_escalate_instead",
            "price_amount": "never_estimate_escalate_instead",
        },
        "profile_enrichment": {
            "default_result": "not_possible",
            "may_raise_priority": True,
            "may_lower_service_level": False,
            "allowed_signals": ["public_company_data", "role", "city"],
            "forbidden_signals": ["photo", "appearance", "surname",
                                  "neighbourhood", "follower_count"],
        },
    },
    # -------------------------------------------------------------------------
    # KOMMO FIELD MAPPING — preencher com IDs reais da conta
    # -------------------------------------------------------------------------
    "pipeline_mapping": {
        "custom_fields": {
            "interest": {"field_id": None},
            "program": {"field_id": None, "type": "text",
                        "note": "free text, not a select — avoids syncing "
                                "option lists with the catalog"},
            "experience": {"field_id": None},
            "driver_age": {"field_id": None},
            "budget": {"field_id": None},
            "urgency": {"field_id": None},
            "lead_score": {"field_id": None},
            "score_reason": {"field_id": None},
        },
        "stages": {
            "new": {"status_id": None},
            "qualifying": {"status_id": None},
            "qualified": {"status_id": None},
            "scheduled": {"status_id": None},
            "with_owner": {"status_id": None},
            "closed_lost": {"status_id": None},
        },
    },
}

SEGMENTS = [
    {"slug": "corporate", "name": "Corporate / Group",
     "description": "Company, family or group booking a private event "
                    "(minimum 3 drivers)",
     "required_fields": ["headcount", "preferred_date"],
     "optional_fields": ["company", "total_budget", "city"],
     "default_agent_action": "recommend", "display_order": 1,
     "status": "active"},
    {"slug": "youth", "name": "Youth / Family",
     "description": "Parent or guardian looking for an activity for a child "
                    "or teenager",
     "required_fields": ["driver_age", "experience_level", "origin"],
     "optional_fields": ["goal", "preferred_period"],
     "default_agent_action": "recommend", "display_order": 2,
     "status": "active"},
    {"slug": "learner", "name": "Beginner / Recreational",
     "description": "Beginner, or someone who has only driven recreationally "
                    "(indoor, rental, arcade)",
     "required_fields": ["experience_level", "origin"],
     "optional_fields": ["driver_age", "goal", "availability_window"],
     "default_agent_action": "recommend", "display_order": 3,
     "status": "active"},
    {"slug": "competitor", "name": "Active racer",
     "description": "Actually competes: runs a series, has a class, cites "
                    "lap times",
     "required_fields": ["experience_level", "contact_phone"],
     "optional_fields": ["category", "target_event", "dates"],
     "default_agent_action": "handoff_to_owner", "display_order": 4,
     "status": "active"},
    {"slug": "owner_operator", "name": "Kart or team owner",
     "description": "Already owns a kart or runs a team; wants maintenance, "
                    "parts or support",
     "required_fields": ["need_type"],
     "optional_fields": ["owns_kart", "category"],
     "default_agent_action": "handoff_to_owner", "display_order": 5,
     "status": "active"},
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed configurations + segments.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        print(f"configurations: {len(CONFIGURATIONS)} categorias")
        for cat, keys in CONFIGURATIONS.items():
            print(f"  {cat}: {', '.join(keys)}")
        print(f"segments: {', '.join(s['slug'] for s in SEGMENTS)}")
        print("\ndry run — nada escrito")
        return 0

    from db.client import get_db
    from db import schema

    db = get_db()

    # merge=True: rodar de novo atualiza sem apagar chaves acrescentadas
    # à mão depois (ex.: field IDs do Kommo preenchidos no console).
    for category, values in CONFIGURATIONS.items():
        db.collection("configurations").document(category).set(
            dict(values, updated_by="seed"), merge=True)
        print(f"  configurations/{category} ok")

    for seg in SEGMENTS:
        schema.validate("segments", seg)
        db.collection("segments").document(seg["slug"]).set(seg, merge=True)
        print(f"  segments/{seg['slug']} ok")

    print("\nseed aplicado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
