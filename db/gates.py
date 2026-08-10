"""
Os portões — antes funções SQL e um trigger, agora o único caminho de escrita.

No Postgres, três garantias eram estruturais:

    preço      agent_program() não devolvia o número
    idade      um trigger recusava a reserva, viesse de onde viesse
    escalação  agent_escalate travava o takeover e cancelava follow-ups

O Firestore não tem funções nem triggers síncronos, então as três moram aqui,
e a regra do projeto passa a ser esta, sem exceção:

    NENHUM outro módulo escreve em appointments, escalations ou lê preços
    de offers. Reserva nasce em create_appointment(). Escalação nasce em
    escalate(). Preço só sai de shape_offers(). O grep que prova isso é
    parte do test_gates.py.

O que se perde na troca, dito honestamente: no Postgres nem um humano com
psql conseguia inserir a reserva bloqueada — o trigger recusava. Aqui, quem
tiver a service account consegue escrever direto. O perímetro passou a ser a
credencial (só o serviço do agente escreve), não o schema. A transação abaixo
garante atomicidade e leitura consistente; não garante contra um insider com
a chave. Essa diferença está documentada em db/schema.md e no README.
"""

from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from . import schema
# Predicados puros em policy.py: este módulo importa o SDK; aquele, nada.
# O dry-run e o self-test dependem dessa separação para rodar sem o SDK.
from .policy import price_disclosure_allowed  # noqa: F401  (re-export)


class GateRefusal(Exception):
    """Uma escrita que o portão recusou. O chamador transforma em mensagem
    utilizável pelo modelo — nunca em meia frase para o driver."""


# =============================================================================
# 1. PREÇO — o número ausente do JSON, não escondido nele
# =============================================================================


def shape_offers(db, program_slug: str, agent_action: str,
                 qual: dict, price_requested: bool) -> list[dict]:
    """Lê as ofertas e devolve o JSON que o modelo pode ver.

    Quando o preço não pode ser dito, ele não está no retorno — nem nulo com
    o valor ao lado, nem sinalizado: ausente. Um modelo que nunca recebe um
    número não pode ser convencido a dizê-lo.
    """
    allowed, reason = price_disclosure_allowed(qual, price_requested)

    # Quem vai para o dono nunca recebe cotação, por mais completo que o
    # perfil esteja. Essa conversa pertence a uma pessoa.
    if agent_action in ("handoff_to_owner", "handoff_to_human"):
        allowed, reason = False, ("this program is not sold by you — "
                                  "route it to a person")

    docs = (db.collection("programs").document(program_slug)
            .collection("offers")
            .where(filter=FieldFilter("status", "==", "active"))
            .stream())

    out = []
    for snap in docs:
        r = snap.to_dict()
        offer = {
            "offer_id": r.get("offer_id", snap.id),
            "offer_name": r.get("offer_name"),
            "context": r.get("context"),
            "description": r.get("description"),
            "conditions_note": r.get("conditions_note"),
        }
        quotable = r.get("agent_can_quote", True)

        if not allowed:
            offer["price"] = None
            offer["price_withheld_because"] = reason
        elif not quotable:
            # A tarifa existe e só o operador da pista pode oferecê-la. O
            # agente mantém a linha para não ser contradito se o driver a
            # mencionar — e mesmo assim nunca diz o número.
            offer["price"] = None
            offer["price_withheld_because"] = (
                "this rate exists but only the track operator may offer it")
        else:
            offer["price"] = r.get("price_amount")
            offer["currency"] = r.get("price_currency", "USD")
            offer["unit"] = r.get("price_unit")
            offer["is_indicative"] = r.get("price_is_indicative", True)
            offer["variance_note"] = r.get("price_variance_note")
            offer["must_add"] = ("track fees are paid directly to Orlando "
                                 "Kart Center and are not included")
        out.append(offer)

    out.sort(key=lambda o: (o.get("price") is None, o.get("price") or 0))
    return out


# =============================================================================
# 2. IDADE — a transação que substitui o trigger
# =============================================================================

def latest_age_approval(db, lead_id: str, transaction=None):
    """A aprovação de idade mais recente do lead, ou None.

    Uma aprovação posterior supersede uma rejeição anterior — o ORDER BY
    do trigger, reproduzido aqui.
    """
    query = (db.collection("human_approvals")
             .where(filter=FieldFilter("lead_id", "==", lead_id))
             .where(filter=FieldFilter("reason", "==",
                                       "age_below_track_minimum"))
             .order_by("requested_at", direction=firestore.Query.DESCENDING)
             .limit(1))
    snaps = list(query.stream(transaction=transaction))
    return snaps[0].to_dict() if snaps else None


def create_appointment(db, lead_id: str, closing_path: str,
                       scheduled_at, phone_collected: str | None = None,
                       status: str = "scheduled",
                       approval_id: str | None = None,
                       timezone: str = "America/New_York") -> str:
    """O único lugar onde uma reserva nasce.

    Dentro de uma transação: a leitura da aprovação e a criação do documento
    são atômicas, então uma aprovação que muda no meio não passa pela fresta.
    Levanta GateRefusal — nunca cria e marca depois.
    """
    data = {
        "lead_id": lead_id,
        "closing_path": closing_path,
        "scheduled_at": scheduled_at,
        "status": status,
        "phone_collected": phone_collected,
        "approval_id": approval_id,
        "timezone": timezone,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    schema.validate("appointments", data)

    # CONSTRAINT scheduled_has_time: reserva confirmada tem horário.
    if status != "pending_human_approval" and scheduled_at is None:
        raise GateRefusal("a scheduled/confirmed booking must have a time")
    # CONSTRAINT pending_requires_approval.
    if status == "pending_human_approval" and not approval_id:
        raise GateRefusal("a pending booking must reference its approval")

    transaction = db.transaction()
    ref = db.collection("appointments").document()

    @firestore.transactional
    def _txn(txn):
        if status in ("scheduled", "confirmed"):
            approval = latest_age_approval(db, lead_id, transaction=txn)
            # Nunca precisou de aprovação: nada a checar. Precisou: só
            # 'approved' libera — 'pending' e 'rejected' recusam.
            if approval is not None and approval.get("status") != "approved":
                raise GateRefusal(
                    f"Booking blocked: driver age clearance for lead "
                    f"{lead_id} is {approval.get('status')}, not approved. "
                    f"A human must clear the age gate first.")
        txn.create(ref, data)

    _txn(transaction)
    return ref.id


def request_approval(db, lead_id: str, reason: str, context: str,
                     driver_age: int | None = None,
                     driver_experience: str | None = None,
                     requested_slot=None) -> str:
    data = {
        "lead_id": lead_id,
        "reason": reason,
        "driver_age": driver_age,
        "driver_experience": driver_experience,
        "requested_slot": requested_slot,
        "context": context,
        "status": "pending",
        "requested_at": firestore.SERVER_TIMESTAMP,
    }
    schema.validate("human_approvals", data)
    ref = db.collection("human_approvals").document()
    ref.create(data)
    return ref.id


# =============================================================================
# 3. ESCALAÇÃO — irreversível, e silencia follow-ups na mesma transação
# =============================================================================

def escalate(db, lead_id: str, reason: str, triggered_by: str = "ai",
             priority: str = "normal", briefing: str | None = None,
             verbatim_quote: str | None = None) -> None:
    """Takeover + registro + cancelamento de follow-ups, atomicamente.

    Nenhuma mensagem automática pode alcançar quem foi escalado — muito menos
    quem acabou de relatar uma dificuldade pessoal. Se o cancelamento dos
    follow-ups falhasse depois do takeover, essa janela existiria; a transação
    é o que a fecha.
    """
    esc_data = {
        "lead_id": lead_id,
        "reason": reason,
        "triggered_by": triggered_by,
        "priority": priority,
        "briefing": briefing,
        "verbatim_quote": verbatim_quote,
        "escalated_at": firestore.SERVER_TIMESTAMP,
    }
    schema.validate("escalations", esc_data)

    transaction = db.transaction()
    lead_ref = db.collection("leads").document(lead_id)
    esc_ref = db.collection("escalations").document()

    @firestore.transactional
    def _txn(txn):
        pending = list(
            db.collection("follow_ups")
            .where(filter=FieldFilter("lead_id", "==", lead_id))
            .where(filter=FieldFilter("status", "==", "pending"))
            .stream(transaction=txn))

        txn.update(lead_ref, {"human_takeover": True, "status": "escalated",
                              "updated_at": firestore.SERVER_TIMESTAMP})
        txn.create(esc_ref, esc_data)
        for snap in pending:
            txn.update(snap.reference, {
                "status": "cancelled",
                "skip_reason": f"escalated: {reason}",
            })

    _txn(transaction)
