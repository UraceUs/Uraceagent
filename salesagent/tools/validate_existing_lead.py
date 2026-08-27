#!/usr/bin/env python3
"""TESTE DE CONTINUIDADE com lead EXISTENTE — lead real, histórico real.

Diferente de validate_production.py (que assume lead limpo), este harness
existe para provar a régua mais dura: o cliente que sumiu e voltou, com
escalação antiga, follow-up já rodado e decisões humanas no meio. O
histórico É o teste — por isso a regra número um:

    NADA é resetado, apagado, recriado ou corrigido em silêncio.
    Estado inconsistente é DOCUMENTADO, nunca consertado pelo harness.

Uso (no VPS):
    python3 salesagent/tools/validate_existing_lead.py --lead 31764961 --snapshot
        # só o retrato do estado atual (read-only, não muda NADA)
    python3 salesagent/tools/validate_existing_lead.py --lead 31764961
        # snapshot + teste guiado + tabela EXISTING LEAD TEST

Relatório com evidências: ~/.urace/existing-lead-<id>-<data>.md
"""
import argparse
import datetime
import sys
import time
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent / "bridge"
sys.path.insert(0, str(BRIDGE))

import state  # noqa: E402
from config import KOMMO_DOMAIN, KOMMO_TOKEN, STAGES, URACE_DIR  # noqa: E402

REL: list[str] = []
R: dict[str, str] = {}


def out(txt: str = "") -> None:
    REL.append(txt)
    print(txt)


def marca(teste: str, ok: bool, motivo: str = "") -> None:
    R[teste] = "PASS" if ok else "FAIL"
    out(f"  ==> {teste}: {R[teste]}" + (f" — {motivo}" if motivo else ""))


def sim(pergunta: str) -> bool:
    while True:
        r = input(f"  >> {pergunta} [s/n] ").strip().lower()
        if r in ("s", "sim", "y", "yes"):
            return True
        if r in ("n", "nao", "não", "no"):
            return False


def acao(instrucao: str) -> None:
    input(f"\n  AÇÃO SUA: {instrucao}\n  (Enter quando feito) ")


def eventos(lead: int, desde: int) -> list[dict]:
    with state.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT ts, kind, detail FROM audit WHERE ts>=? AND "
            "(lead_id=? OR lead_id IS NULL) ORDER BY id", (desde, lead))]


def mostra(evs: list[dict], kinds: tuple[str, ...]) -> None:
    for e in evs:
        if e["kind"] in kinds:
            ts = datetime.datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")
            out(f"    [{ts}] {e['kind']}: {e['detail'][:150]}")


# ------------------------------------------------------------- §2 snapshot
def snapshot(lead: int) -> dict:
    out(f"\n===== SNAPSHOT (read-only) — lead {lead} =====")
    conv = state.get_conversation(lead)
    confirmadas = state.get_confirmations(lead, limit=10)
    agora = int(time.time())

    def idade(ts):
        return f"{(agora - ts) // 3600}h atrás" if ts else "-"

    out(f"  nome:              {conv.get('contact_name') or '?'}")
    out(f"  estado:            {conv['state']}")
    out(f"  qualificação:      experience={conv.get('q_experience') or '?'} "
        f"origin={conv.get('q_origin') or '?'} idade={conv.get('driver_age') or '?'}")
    out(f"  escalação:         motivo='{conv.get('escalation_reason') or '-'}' "
        f"({idade(conv.get('escalated_at'))})")
    out(f"  pergunta pendente: {conv.get('pending_question') or '-'}")
    out(f"  última msg lead:   '{(conv.get('last_inbound_text') or '')[:60]}' "
        f"({idade(conv.get('last_inbound_at'))})")
    out(f"  última msg nossa:  {idade(conv.get('last_outbound_at'))}")
    out(f"  follow-up:         trilha={conv.get('followup_track') or '-'} "
        f"tentativas={conv.get('followup_attempts')}")
    out(f"  contadores:        holding={conv.get('holding_count') or 0} "
        f"realerts={conv.get('realert_count') or 0}")
    out(f"  confirmações humanas: {len(confirmadas)}")
    for c in confirmadas:
        out(f"    - [{c['author']}] '{(c.get('question') or '')[:50]}' -> "
            f"'{c['answer'][:70]}'")

    # histórico recente da conversa (auditoria da ponte)
    out("  últimos eventos da conversa:")
    with state.db() as conn:
        hist = [dict(r) for r in conn.execute(
            "SELECT ts, kind, detail FROM audit WHERE lead_id=? AND kind IN "
            "('inbound','outbound','escalation','human_reply','rescue') "
            "ORDER BY id DESC LIMIT 12", (lead,))]
    for e in reversed(hist):
        ts = datetime.datetime.fromtimestamp(e["ts"]).strftime("%d/%m %H:%M")
        out(f"    [{ts}] {e['kind']}: {e['detail'][:110]}")

    # sessão do Chase no OpenClaw (histórico da conversa no modelo)
    sess = Path.home() / ".openclaw/agents/urace-sales/sessions/sessions.json"
    tem_sessao = sess.exists() and f"kommo-{lead}" in sess.read_text(errors="replace")
    out(f"  sessão OpenClaw kommo-{lead}: {'EXISTE' if tem_sessao else 'não encontrada'}")

    # Kommo (leitura pura — nada é escrito)
    try:
        import httpx
        r = httpx.get(f"https://{KOMMO_DOMAIN}/api/v4/leads/{lead}",
                      params={"with": "contacts"},
                      headers={"Authorization": f"Bearer {KOMMO_TOKEN}"}, timeout=15)
        r.raise_for_status()
        info = r.json()
        estagio = next((k for k, v in STAGES.items()
                        if v == info.get("status_id")), info.get("status_id"))
        tags = [t["name"] for t in info.get("_embedded", {}).get("tags", [])]
        out(f"  Kommo: estágio={estagio} tags={tags}")
        n = httpx.get(f"https://{KOMMO_DOMAIN}/api/v4/leads/{lead}/notes",
                      params={"limit": 5, "order[id]": "desc"},
                      headers={"Authorization": f"Bearer {KOMMO_TOKEN}"}, timeout=15)
        notas = n.json().get("_embedded", {}).get("notes", []) if n.status_code == 200 else []
        out(f"  Kommo: {len(notas)} nota(s) recentes no card")
    except Exception as exc:
        out(f"  Kommo: leitura falhou ({exc}) — confira o card manualmente")

    # memória que o Chase receberia AGORA
    import app
    out("  memória injetada no próximo turno:")
    for ln in app._memory_context(lead, conv).splitlines():
        out(f"    | {ln}")

    # ---------------- §12: inconsistências DOCUMENTADAS, não corrigidas
    out("\n  INCONSISTÊNCIAS DOCUMENTADAS (nada foi corrigido):")
    achou = False
    pq = conv.get("pending_question") or ""
    er = conv.get("escalation_reason") or ""
    if pq and er and not any(w in pq.lower() for w in er.lower().split()[:1]):
        out(f"    - motivo da escalação ('{er}') difere da pergunta pendente "
            f"('{pq[:50]}'): a pendência foi atualizada por pergunta "
            f"posterior (comportamento de 27/08 — a última pergunta vence).")
        achou = True
    if (conv.get("holding_count") or 0) >= 3:
        out(f"    - holding_count={conv['holding_count']}: as 3 frases de "
            f"espera foram esgotadas; o resgate autônomo está SILENCIADO "
            f"para este lead até um humano responder (por desenho).")
        achou = True
    if conv["state"] in ("WAITING_HUMAN", "HUMAN_HANDOFF") and conv.get("escalated_at"):
        horas = (agora - conv["escalated_at"]) // 3600
        if horas > 24:
            out(f"    - escalado há {horas}h sem resposta humana.")
            achou = True
    if conv.get("last_inbound_at") and not conv.get("q_experience"):
        out("    - lead TEM histórico mas q_experience está vazio: a "
            "classificação nunca foi gravada via [[qualify]]. No 31764961 a "
            "causa conhecida é o truncamento do manual (o lead respondeu 'A' "
            "em 24/08, na época em que o protocolo de diretivas era cortado "
            "do AGENTS.md).")
        achou = True
    if not achou:
        out("    (nenhuma)")
    return conv


# ------------------------------------------------------------------ testes
def rodar(lead: int) -> None:
    conv = snapshot(lead)

    ctx_tem_historico = bool(conv.get("last_inbound_text") or conv.get("contact_name"))
    marca("Historical context recovered", ctx_tem_historico,
          "snapshot acima é a evidência")

    # §6: a ordem depende do estado REAL
    if conv["state"] in ("WAITING_HUMAN", "HUMAN_HANDOFF"):
        out("\n===== ESCALAÇÃO PENDENTE DETECTADA — resolvê-la é o 1º passo (§6) =====")
        out(f"  pendente: '{conv.get('pending_question') or conv.get('escalation_reason')}'")
        t0 = int(time.time())
        acao("no WhatsApp interno, RESPONDA a escalação pendente (reply na "
             "mensagem da escalação): 'Yes, he can bring his own kart. We "
             "need to inspect it before use.'")
        time.sleep(5)
        evs = eventos(lead, t0)
        mostra(evs, ("human_reply", "outbound", "followup", "gate", "error", "knowledge"))
        conv = state.get_conversation(lead)
        confs = state.get_confirmations(lead)
        ingeriu = conv["state"] == "RESUMED" and bool(confs)
        entregou = sim("a resposta APARECEU no chat do lead?")
        marca("Human response ingestion", ingeriu and entregou,
              f"estado={conv['state']}, confirmações={len(confs)}")
    else:
        out("\n  (sem escalação pendente — seguindo direto para memória)")

    # §4: memória — mensagem simples, sem repetir nada
    t0 = int(time.time())
    acao("como o LEAD, mande: 'Hey, I'm back. What was the next step we "
         "discussed?'")
    time.sleep(5)
    evs = eventos(lead, t0)
    mostra(evs, ("inbound", "outbound", "gate", "escalation"))
    respondeu = any(e["kind"] == "outbound" for e in evs)
    usou_ctx = sim("a resposta usou o contexto (citou/assumiu o que já foi "
                   "falado, SEM mandar menu A/B/C/D de novo)?")
    marca("Customer memory recovered", respondeu and usou_ctx)
    marca("Conversation continuation", respondeu and usou_ctx)

    # §5: informação já confirmada não re-escala
    t0 = int(time.time())
    acao("como o LEAD, pergunte DE NOVO a questão já respondida: "
         "'So can I bring my own kart or not?'")
    time.sleep(5)
    evs = eventos(lead, t0)
    mostra(evs, ("inbound", "outbound", "escalation", "notify_human"))
    re_escalou = any(e["kind"] == "escalation" for e in evs)
    afirmou = sim("o Chase AFIRMOU a resposta confirmada (kart pode, com "
                  "inspeção) sem escalar de novo e sem pedir confirmação?")
    marca("Human confirmation recovered", afirmou and not re_escalou)
    marca("No repeated questions", afirmou and not re_escalou)

    # §7/§8: pergunta NOVA que exige humano → escalação imediata e completa
    t0 = int(time.time())
    acao("como o LEAD, mande uma pergunta NOVA que exija decisão humana, "
         "ex.: 'Can I get a discount if I bring a friend?'")
    time.sleep(5)
    evs = eventos(lead, t0)
    mostra(evs, ("inbound", "escalation", "notify_human", "outbound", "gate"))
    t_in = next((e["ts"] for e in evs if e["kind"] == "inbound"), None)
    notif = [e for e in evs if e["kind"] == "notify_human"]
    if not notif:
        out("  aguardando repasse assíncrono (até 90s)...")
        time.sleep(75)
        notif = [e for e in eventos(lead, t0) if e["kind"] == "notify_human"]
        mostra(notif, ("notify_human",))
    lat = (notif[0]["ts"] - t_in) if (notif and t_in) else 9999
    conteudo_ok = bool(notif) and str(lead) in notif[0]["detail"]
    out(f"  latência inbound→notify: {lat}s")
    chegou = sim("chegou no WhatsApp com nome, id, pergunta e contexto?")
    espera_ok = sim("e o lead recebeu espera citando a pergunta nova?")
    marca("Immediate escalation", conteudo_ok and chegou and espera_ok and lat < 120)

    # §9: resposta humana da nova pergunta
    t0 = int(time.time())
    acao("responda ESSA nova escalação no WhatsApp (reply), ex.: 'No "
         "discounts, but group sessions have special conditions - tell him "
         "we can talk about it'")
    time.sleep(5)
    conv = state.get_conversation(lead)
    confs = state.get_confirmations(lead)
    evs = eventos(lead, t0)
    mostra(evs, ("human_reply", "outbound", "gate", "error"))
    entregou2 = sim("a resposta apareceu no chat do lead?")
    marca("Resume after human response",
          conv["state"] == "RESUMED" and entregou2, f"estado={conv['state']}")
    marca("Memory updated", len(confs) >= 2,
          f"{len(confs)} fato(s) confirmados na memória do cliente")

    # §10: retorno — o Chase lembra da resposta humana
    t0 = int(time.time())
    acao("como o LEAD, mande: 'ok great, thanks!' e depois qualquer pergunta "
         "de acompanhamento")
    time.sleep(5)
    lembra = sim("o Chase seguiu tratando as respostas humanas como fatos "
                 "(sem re-escalar nenhuma das duas)?")
    if not lembra:
        marca("Resume after human response", False, "regrediu no retorno")

    # CRM + contaminação
    marca("CRM updated", sim("no card do Kommo: notas das respostas humanas, "
                             "tags e estágio coerentes, sem lead duplicado?"))
    with state.db() as conn:
        vazadas = conn.execute(
            "SELECT COUNT(*) c FROM confirmations WHERE lead_id != ? AND "
            "(answer LIKE '%inspect%' OR answer LIKE '%discount%')",
            (lead,)).fetchone()["c"]
    marca("No cross-lead contamination", vazadas == 0,
          f"{vazadas} confirmação(ões) deste teste em OUTROS leads")

    # ------------------------------------------------------------- tabela
    ordem = ["Historical context recovered", "Customer memory recovered",
             "Human confirmation recovered", "No repeated questions",
             "Conversation continuation", "Immediate escalation",
             "Human response ingestion", "Resume after human response",
             "Memory updated", "CRM updated", "No cross-lead contamination"]
    out("\n### EXISTING LEAD TEST\n")
    out("| Test | Result |")
    out("| --- | --- |")
    for t in ordem:
        out(f"| {t} | {R.get(t, 'NOT RUN')} |")
    pronto = all(R.get(t) == "PASS" for t in ordem)
    out(f"\nRESULTADO: {'TODOS PASS' if pronto else 'HÁ FALHAS — ver acima'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", type=int, required=True)
    ap.add_argument("--snapshot", action="store_true",
                    help="só o retrato read-only, sem teste")
    args = ap.parse_args()
    out(f"# Teste de lead existente {args.lead} — "
        f"{datetime.datetime.now():%d/%m/%Y %H:%M}")
    if args.snapshot:
        snapshot(args.lead)
    else:
        rodar(args.lead)
    destino = URACE_DIR / (f"existing-lead-{args.lead}-"
                           f"{datetime.date.today():%Y%m%d}.md")
    destino.write_text("\n".join(REL), encoding="utf-8")
    out(f"\nRelatório: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
