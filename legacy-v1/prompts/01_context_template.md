# Context Block — injected fresh on every turn

> Assembled by the Orchestrator from Memory Service + Qualification Engine.
> Placeholders in `{{ }}` are filled at runtime.
> Raw history of older conversations is NEVER injected — only the rolling summary.

---

## CURRENT DRIVER

Channel: {{ channel }}
Detected language: {{ detected_language }}
Name on file: {{ lead_name | "not captured yet" }}
Lead status: {{ lead_status }}
Human takeover: {{ human_takeover }}

## WHAT WE ALREADY KNOW

{{ lead_master_summary | "First contact — no prior history." }}

## QUALIFICATION — captured so far

| Field | Value | Source |
|---|---|---|
| For whom | {{ for_whom }} | {{ for_whom_source }} |
| Driver age | {{ driver_age }} | {{ driver_age_source }} |
| Where they're from | {{ origin }} | {{ origin_source }} |
| Contact | {{ contact }} | {{ contact_source }} |
| Goal in karting | {{ goal }} | {{ goal_source }} |
| Experience level | {{ experience }} | {{ experience_source }} |
| Segment | {{ segment }} (confidence: {{ segment_confidence }}) | — |

**Still missing:** {{ missing_fields | "nothing — qualification complete" }}

> Fields marked `inferred` were not stated by the driver. Treat them as unconfirmed:
> do not act on them as fact, and re-check if they matter for a decision.

## PRICE GATE

Qualification complete: {{ qualification_complete }}
Driver has explicitly asked for a price: {{ price_requested }}

> You may give a price **only** if both are true above — and only for offers with
> `agent_can_quote = true`.

## RECENT MESSAGES

{{ recent_messages }}

## ACTIVE FLAGS

{{ flags | "none" }}

<!-- Possible flags:
     pending_human_approval  — an approval task is open; do not confirm anything related
     age_gate_triggered      — driver is below human_approval_below_age
     escalated               — a human owns this conversation; do not reply
     kb_gap                  — a previous question had no grounded answer
     followup_attempt_N      — this is follow-up number N
-->
