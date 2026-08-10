"""
Catalog mapping — the single definition of how the sheet maps to the database.

Four times today the same defect appeared: one vocabulary written by hand in two
files, drifting in silence. Tool lists, judge verdicts, the close_lead enum, the
approval sequence. The sheet-to-column mapping is the fifth opportunity, so it
gets one definition and a checker (validate_mapping.py) instead of living
half in the parser and half in the INSERT statement.

Nothing here knows about Google Sheets or about Firestore. It is a spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# =============================================================================
# COERCION
#
# The sheet gives everything as text. Empty string is the interesting case:
# it must become None, and None means "do not evaluate this criterion" —
# never "assume something reasonable". That rule is enforced downstream in the
# recommendation engine; here we only have to be sure the empty cell survives
# as NULL instead of being helpfully filled in.
# =============================================================================

class CoercionError(ValueError):
    """Raised with a human-readable reason. Rejects one row, never the run."""


def _blank(raw: str | None) -> bool:
    return raw is None or str(raw).strip() == ""


def as_text(raw):
    return None if _blank(raw) else str(raw).strip()


def as_int(raw):
    if _blank(raw):
        return None
    try:
        return int(float(str(raw).strip()))
    except ValueError:
        raise CoercionError(f"expected a whole number, got {raw!r}")


def as_numeric(raw):
    if _blank(raw):
        return None
    cleaned = str(raw).strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        raise CoercionError(f"expected a number, got {raw!r}")


def as_bool(raw):
    if _blank(raw):
        return None
    v = str(raw).strip().lower()
    if v in ("true", "yes", "sim", "1", "y"):
        return True
    if v in ("false", "no", "nao", "não", "0", "n"):
        return False
    raise CoercionError(f"expected TRUE or FALSE, got {raw!r}")


def as_list(raw):
    """Semicolon-separated. Empty stays None, not an empty array — an empty
    keyword list and an unfilled keyword cell mean the same thing to the agent,
    and NULL is the honest representation of 'nobody filled this in'."""
    if _blank(raw):
        return None
    parts = [p.strip() for p in str(raw).split(";") if p.strip()]
    return parts or None


def one_of(*allowed: str) -> Callable:
    def check(raw):
        value = as_text(raw)
        if value is None:
            return None
        if value not in allowed:
            raise CoercionError(
                f"expected one of {', '.join(allowed)}, got {value!r}")
        return value
    return check


def slug(raw):
    value = as_text(raw)
    if value is None:
        return None
    if value != value.lower() or " " in value:
        raise CoercionError(f"must be lowercase with no spaces, got {value!r}")
    return value


# =============================================================================
# COLUMN SPEC
# =============================================================================

@dataclass(frozen=True)
class Column:
    sheet: str                  # header text in the sheet, matched exactly
    db: str                     # column name in Postgres
    coerce: Callable = as_text
    required: bool = False      # a blank here rejects the row


@dataclass(frozen=True)
class TabSpec:
    tab: str                    # sheet tab name
    table: str                  # target table
    key: str                    # stable identity column — see README on renames
    columns: list[Column]
    row_checks: list = field(default_factory=list)


# --- row-level checks --------------------------------------------------------

def age_range_sane(row: dict):
    lo, hi = row.get("age_min"), row.get("age_max")
    if lo is not None and hi is not None and lo > hi:
        raise CoercionError(f"age_min ({lo}) is greater than age_max ({hi})")


def approval_age_sane(row: dict):
    gate, lo = row.get("human_approval_below_age"), row.get("age_min")
    if gate is not None and lo is not None and gate < lo:
        raise CoercionError(
            f"human_approval_below_age ({gate}) is below age_min ({lo}), which "
            f"means the gate can never fire")


def price_needs_unit(row: dict):
    if row.get("price_amount") is not None and row.get("price_unit") is None:
        raise CoercionError("price_amount is set but price_unit is empty — the "
                            "agent cannot quote a number without its unit")


# =============================================================================
# THE MAPPING
# =============================================================================

SEGMENTS = TabSpec(
    tab="_segments", table="segments", key="slug",
    columns=[
        Column("segment_slug", "slug", slug, required=True),
        Column("segment_name", "name", as_text, required=True),
        Column("description", "description"),
        Column("required_fields", "required_fields", as_list),
        Column("optional_fields", "optional_fields", as_list),
        Column("default_agent_action", "default_agent_action",
               one_of("recommend", "handoff_to_owner", "handoff_to_human",
                      "faq_only")),
        Column("status", "status", one_of("active", "inactive")),
    ],
)

PROGRAMS = TabSpec(
    tab="_programs", table="programs", key="slug",
    columns=[
        Column("program_slug", "slug", slug, required=True),
        Column("program_name", "name", as_text, required=True),
        Column("segment_slug", "segment_id", slug),        # slug É o doc ID no Firestore
        Column("agent_action", "agent_action",
               one_of("recommend", "handoff_to_owner", "handoff_to_human",
                      "faq_only"), required=True),
        Column("category", "category", as_text, required=True),
        Column("status", "status", one_of("active", "inactive"), required=True),
        Column("description", "description"),
        Column("target_audience", "target_audience"),
        Column("age_min", "age_min", as_int),
        Column("age_max", "age_max", as_int),
        Column("human_approval_below_age", "human_approval_below_age", as_int),
        Column("recommended_level", "recommended_level"),
        Column("prerequisites", "prerequisites"),
        Column("benefits", "benefits"),
        Column("differentiators", "differentiators"),
        Column("keywords", "keywords", as_list),
        Column("cross_sell", "cross_sell"),
        Column("upsell", "upsell"),
        Column("recommendation_priority", "recommendation_priority", as_int),
        Column("display_order", "display_order", as_int),
    ],
    row_checks=[age_range_sane, approval_age_sane],
)

OFFERS = TabSpec(
    tab="_offers", table="program_offers", key="offer_id",
    columns=[
        Column("offer_id", "offer_id", slug, required=True),
        Column("program_slug", "program_id", slug, required=True),  # resolved on apply
        Column("offer_name", "offer_name", as_text, required=True),
        Column("context", "context"),
        Column("description", "description"),
        Column("price_amount", "price_amount", as_numeric),
        Column("price_currency", "price_currency"),
        Column("price_unit", "price_unit", one_of(
            "day", "event", "session", "month", "package", "contract",
            "person", "service", "3_days", "4_days", "5_days")),
        Column("price_is_indicative", "price_is_indicative", as_bool),
        Column("price_variance_note", "price_variance_note"),
        Column("conditions_note", "conditions_note"),
        Column("agent_can_quote", "agent_can_quote", as_bool),
        Column("status", "status", one_of("active", "inactive"), required=True),
        Column("source_tab", "source_sheet_tab"),
    ],
    row_checks=[price_needs_unit],
)

SPECS = [SEGMENTS, PROGRAMS, OFFERS]


# =============================================================================
# PARSING
# =============================================================================

def parse_row(spec: TabSpec, raw: dict, row_number: int) -> tuple[dict | None, str | None]:
    """Coerce one sheet row. Returns (row, None) or (None, reason).

    A bad row is rejected on its own. One malformed cell never takes the
    catalog down — that is the whole point of returning a reason instead of
    raising.
    """
    out: dict = {}
    for col in spec.columns:
        raw_value = raw.get(col.sheet)
        try:
            value = col.coerce(raw_value)
        except CoercionError as exc:
            return None, f"column '{col.sheet}': {exc}"
        if col.required and value is None:
            return None, f"column '{col.sheet}' is required and is empty"
        out[col.db] = value

    for check in spec.row_checks:
        try:
            check(out)
        except CoercionError as exc:
            return None, str(exc)

    out["source_sheet_row"] = row_number
    out["source_sheet_tab"] = spec.tab
    return out, None
