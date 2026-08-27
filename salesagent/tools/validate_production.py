#!/usr/bin/env python3
"""VALIDAÇÃO FINAL DE PRODUÇÃO do Chase — testes A-J do brief de 27/08.

O que este harness é: o executor da validação ponta a ponta NO VPS. Ele
automatiza tudo que pode ser verificado por máquina (config, serviços,
logs de auditoria, memória, estado, vault) e conduz o operador pelos
passos que só um humano pode dar (mandar mensagem como lead, responder no
WhatsApp, confirmar que a mensagem APARECEU na tela).

Critério inegociável, herdado do brief: rc=0/200/202 NUNCA é prova de
entrega. Prova é (a) evidência no log de auditoria E (b) o operador
confirmando que viu a mensagem no canal real. Todo PASS registra as duas.

Uso (no VPS):
    python3 salesagent/tools/validate_production.py --check
        # fase 0: ambiente (config, serviços, tamanho do AGENTS.md)
    python3 salesagent/tools/validate_production.py --lead <ID> [--lead-b <ID2>]
        # roda os testes A-J interativamente e imprime o veredito final

O relatório com evidências fica em ~/.urace/validation-report-<data>.md.
"""
import argparse
import datetime
import re
import subprocess
import sys
import time
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent / "bridge"
sys.path.insert(0, str(BRIDGE))

import state  # noqa: E402
from config import (BRAIN_RETRIEVAL, FOLLOWUP_BOT_ID,  # noqa: E402
                    HUMAN_WHATSAPP_LIST, SALESBOT_DISPLAY, URACE_DIR)

RELATORIO: list[str] = []
RESULTADOS: dict[str, str] = {}


def log_rel(txt: str) -> None:
    RELATORIO.append(txt)
    print(txt)


def evidencia(lead_id: int | None, desde: int, kinds: tuple[str, ...] = ()) -> list[dict]:
    """Entradas do audit log desde `desde` (epoch), do lead ou globais."""
    with state.db() as conn:
        q = "SELECT ts, lead_id, kind, detail FROM audit WHERE ts >= ?"
        args: list = [desde]
        if lead_id is not None:
            q += " AND (lead_id = ? OR lead_id IS NULL)"
            args.append(lead_id)
        if kinds:
            q += " AND kind IN (%s)" % ",".join("?" * len(kinds))
            args.extend(kinds)
        q += " ORDER BY id"
        return [dict(r) for r in conn.execute(q, args)]


def mostrar(entradas: list[dict], filtro: tuple[str, ...] = ()) -> None:
    for e in entradas:
        if filtro and e["kind"] not in filtro:
            continue
        ts = datetime.datetime.fromtimestamp(e["ts"]).strftime("%H:%M:%S")
        log_rel(f"    [{ts}] {e['kind']}: {e['detail'][:160]}")


def pergunta_sim(pergunta: str) -> bool:
    while True:
        r = input(f"  >> {pergunta} [s/n] ").strip().lower()
        if r in ("s", "sim", "y", "yes"):
            return True
        if r in ("n", "nao", "não", "no"):
            return False


def espera_operador(instrucao: str) -> None:
    input(f"\n  AÇÃO SUA: {instrucao}\n  (Enter quando tiver feito) ")


def veredito(teste: str, ok: bool, motivo: str = "") -> None:
    RESULTADOS[teste] = "PASS" if ok else "FAIL"
    log_rel(f"  ==> {teste}: {'PASS' if ok else 'FAIL'}"
            + (f" — {motivo}" if motivo else ""))


def _cmd(args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as exc:
        return 1, str(exc)


# ------------------------------------------------------------------ fase 0
def fase0_ambiente() -> bool:
    log_rel("\n===== FASE 0 — AMBIENTE =====")
    ok_geral = True

    rc, out = _cmd(["curl", "-sf", "http://127.0.0.1:8800/health"])
    ok = rc == 0
    ok_geral &= ok
    log_rel(f"  sales-bridge /health: {'OK' if ok else 'FALHOU — ' + out[:120]}")

    rc, out = _cmd(["openclaw", "gateway", "status"])
    log_rel(f"  gateway status: rc={rc} {out.splitlines()[-1][:100] if out else ''}")
    ok_geral &= rc == 0

    rc, out = _cmd(["openclaw", "config", "get", "agents.defaults.bootstrapMaxChars"])
    limite = int(re.sub(r"\D", "", out) or 0) if rc == 0 else 0
    agents_md = Path.home() / ".openclaw/workspace/urace-sales/AGENTS.md"
    tam = len(agents_md.read_text(encoding="utf-8")) if agents_md.exists() else -1
    log_rel(f"  bootstrapMaxChars={limite or '?'} | AGENTS.md no workspace={tam} chars")
    if tam < 0:
        log_rel("  !! AGENTS.md não encontrado no workspace — rode sync_agent_instructions.sh")
        ok_geral = False
    elif limite and tam > limite:
        log_rel(f"  !! TRUNCAMENTO: o manual do Chase será cortado ({tam} > {limite}).")
        log_rel(f"     Corrija: openclaw config set agents.defaults.bootstrapMaxChars {tam + 15000}")
        ok_geral = False
    elif not limite:
        log_rel("  !! não consegui ler o limite — confirme no `openclaw doctor` que não há 'truncated'")

    log_rel(f"  SALESBOT_DISPLAY={SALESBOT_DISPLAY} "
            f"{'(OK, único modo com entrega comprovada)' if SALESBOT_DISPLAY == 'balloons' else '!! json_reply teve 202 sem exibição em 26/08'}")
    ok_geral &= SALESBOT_DISPLAY == "balloons"
    log_rel(f"  FOLLOWUP_BOT_ID={'OK (' + FOLLOWUP_BOT_ID + ')' if FOLLOWUP_BOT_ID else 'VAZIO — entrega espontânea desligada!'}")
    ok_geral &= bool(FOLLOWUP_BOT_ID)
    log_rel(f"  BRAIN_RETRIEVAL={BRAIN_RETRIEVAL} | operadores WhatsApp={len(HUMAN_WHATSAPP_LIST)}")
    if len(HUMAN_WHATSAPP_LIST) < 2:
        log_rel("  !! só 1 número em HUMAN_WHATSAPP — Eduardo fora das escalações")

    rc, out = _cmd(["openclaw", "agent", "list"])
    tem_sales = "urace-sales" in out
    tem_main = "main" in out
    log_rel(f"  agentes: urace-sales={'OK' if tem_sales else 'AUSENTE'} main={'OK' if tem_main else 'AUSENTE'}")
    ok_geral &= tem_sales and tem_main
    return ok_geral


# ------------------------------------------------------------------ testes
def teste_a_novo_lead(lead: int) -> None:
    log_rel("\n===== TESTE A — NOVO LEAD =====")
    t0 = int(time.time())
    espera_operador(f"mande 'Hi' pelo canal do lead {lead} (Instagram/site)")
    time.sleep(3)
    ev = evidencia(lead, t0)
    mostrar(ev, ("inbound", "outbound", "salesbot_continue", "outbound_fallback", "error"))
    inbound = any(e["kind"] == "inbound" for e in ev)
    outbound = any(e["kind"] == "outbound" for e in ev)
    fallback = any(e["kind"] == "outbound_fallback" for e in ev)
    conv = state.get_conversation(lead)
    memoria = conv.get("last_inbound_at") is not None
    log_rel(f"  memória inicial: state={conv['state']} nome={conv.get('contact_name') or '?'}")
    visivel = pergunta_sim("a apresentação do Chase (menu A/B/C/D) APARECEU no chat do lead?")
    veredito("New lead", inbound and outbound and not fallback and memoria and visivel,
             "" if visivel else "entrega não confirmada na tela")


def teste_b_continuidade(lead: int) -> None:
    log_rel("\n===== TESTE B — CONTINUIDADE =====")
    espera_operador("continue a conversa como lead: responda a classificação "
                    "(ex.: 'A'), informe idade quando pedida, e o objetivo. "
                    "Depois PARE de responder")
    time.sleep(3)
    conv = state.get_conversation(lead)
    log_rel(f"  registrado: experience={conv.get('q_experience') or '?'} "
            f"idade={conv.get('driver_age') or '?'} nome={conv.get('contact_name') or '?'}")
    import app
    ctx = app._memory_context(lead, conv)
    log_rel("  memória que entraria no PRÓXIMO turno (mesmo daqui a dias):")
    for ln in ctx.splitlines():
        log_rel(f"    | {ln}")
    espera_operador("simule o retorno: mande 'hi again' como o mesmo lead")
    time.sleep(3)
    with state.db() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM conversations WHERE lead_id=?",
                         (lead,)).fetchone()["c"]
    sem_dup = n == 1
    log_rel(f"  linhas de memória para o lead: {n} (1 = sem duplicação)")
    nao_rezera = pergunta_sim("o Chase CONTINUOU (sem mandar o menu A/B/C/D de novo, "
                              "sem re-perguntar o que já sabia)?")
    veredito("Conversation continuity", sem_dup and nao_rezera)
    veredito("Customer memory", ("experience=" in ctx and "Próxima ação" in ctx
                                 and sem_dup))


def teste_c_escalacao(lead: int) -> int:
    log_rel("\n===== TESTE C — ESCALAÇÃO IMEDIATA =====")
    t0 = int(time.time())
    espera_operador("mande como lead: 'Can I bring my own kart?'")
    time.sleep(5)
    ev = evidencia(lead, t0)
    mostrar(ev, ("inbound", "escalation", "notify_human", "outbound", "gate"))
    t_in = next((e["ts"] for e in ev if e["kind"] == "inbound"), None)
    notif = [e for e in ev if e["kind"] == "notify_human"]
    if not notif:
        log_rel("  aguardando o repasse assíncrono (até 90s)...")
        time.sleep(60)
        notif = [e for e in evidencia(None, t0) if e["kind"] == "notify_human"]
        mostrar(notif)
    ok_log = any(" OK " in f" {e['detail']} " for e in notif)
    latencia = (notif[0]["ts"] - t_in) if (notif and t_in) else 9999
    log_rel(f"  latência inbound→notify: {latencia}s (disparo é imediato; o "
            f"tempo é o repasse do modelo)")
    completa = bool(notif) and all(
        x in notif[0]["detail"] for x in (str(lead),)) if notif else False
    recebeu = pergunta_sim("a escalação CHEGOU no WhatsApp interno (com nome, "
                           "id, pergunta e contexto)?")
    espera = pergunta_sim("e o LEAD recebeu a mensagem de espera citando a "
                          "pergunta dele?")
    veredito("Human escalation", ok_log and completa and recebeu and espera
             and latencia < 120)
    return t0


def teste_d_resposta_humana(lead: int) -> None:
    log_rel("\n===== TESTE D — RESPOSTA HUMANA =====")
    t0 = int(time.time())
    espera_operador("no WhatsApp interno, RESPONDA a mensagem da escalação "
                    "(reply) escrevendo: 'Yes, he can bring his own kart. We "
                    "need to inspect it before use.'")
    time.sleep(5)
    ev = evidencia(lead, t0)
    mostrar(ev, ("human_reply", "outbound", "followup", "knowledge", "error", "gate"))
    conv = state.get_conversation(lead)
    confirmacoes = state.get_confirmations(lead)
    resumed = conv["state"] == "RESUMED"
    guardou = any("inspect" in c["answer"].lower() for c in confirmacoes)
    log_rel(f"  estado={conv['state']} | confirmações={len(confirmacoes)}")
    entregou = pergunta_sim("a resposta APARECEU no chat do lead?")
    veredito("Human response", resumed and guardou and entregou,
             "" if guardou else "confirmação não gravada — o reply chegou na ponte? "
             "veja 'gate: número não autorizado' acima")


def teste_e_memoria_pos_handoff(lead: int) -> None:
    log_rel("\n===== TESTE E — MEMÓRIA PÓS-HANDOFF =====")
    t0 = int(time.time())
    espera_operador("como lead, mande: 'Great. What should we do next?'")
    time.sleep(5)
    ev = evidencia(lead, t0)
    mostrar(ev, ("inbound", "outbound", "escalation", "notify_human"))
    re_escalou = any(e["kind"] == "escalation" for e in ev)
    respondeu = any(e["kind"] == "outbound" for e in ev)
    coerente = pergunta_sim("a resposta do Chase mostrou que ele SABE da "
                            "confirmação do kart (sem re-perguntar, sem "
                            "re-escalar)?")
    veredito("Resume after handoff", respondeu and not re_escalou and coerente)


def teste_f_dois_leads(lead_a: int, lead_b: int | None) -> None:
    log_rel("\n===== TESTE F — DOIS LEADS =====")
    if not lead_b:
        log_rel("  (sem --lead-b; rode de novo com um segundo lead de teste)")
        veredito("Multi-lead isolation", False, "segundo lead não fornecido")
        return
    espera_operador(f"como o lead B ({lead_b}), mande uma pergunta DIFERENTE "
                    "(ex.: 'do you have birthday events?')")
    time.sleep(5)
    import app
    ctx_b = app._memory_context(lead_b, state.get_conversation(lead_b))
    vazou = "inspect" in ctx_b.lower() or "kart" in [
        c["answer"].lower() for c in state.get_confirmations(lead_b)]
    log_rel(f"  memória do lead B contém fatos do lead A? {'SIM (vazamento!)' if vazou else 'não'}")
    resp_b = pergunta_sim("o lead B recebeu uma resposta pertinente À PERGUNTA DELE?")
    veredito("Multi-lead isolation", not vazou and resp_b)


def teste_h_followup(lead_b: int | None) -> None:
    log_rel("\n===== TESTE H — FOLLOW-UP =====")
    alvo = lead_b
    if not alvo:
        veredito("Follow-up", False, "precisa do lead B (sem escalação ativa)")
        return
    conv = state.get_conversation(alvo)
    log_rel(f"  trilha ativa: {conv.get('followup_track') or 'nenhuma'} "
            f"próximo em: {conv.get('next_followup_at')}")
    tem_trilha = bool(conv.get("followup_track"))
    t0 = int(time.time())
    espera_operador(f"como lead B, responda qualquer coisa (cancela a trilha)")
    time.sleep(4)
    ev = evidencia(alvo, t0, ("followup",))
    mostrar(ev)
    cancelou = any("cancelada" in e["detail"] for e in ev)
    conv = state.get_conversation(alvo)
    veredito("Follow-up", tem_trilha and cancelou and not conv.get("followup_track"),
             "trilha iniciada e cancelada na resposta")


def teste_i_crm(lead: int) -> None:
    log_rel("\n===== TESTE I — CRM =====")
    try:
        import kommo_client
        info = kommo_client.get_lead(lead)
        log_rel(f"  Kommo: lead existe, status_id={info.get('status_id')} "
                f"pipeline={info.get('pipeline_id')}")
        existe = True
    except Exception as exc:
        log_rel(f"  falha lendo o lead no Kommo: {exc}")
        existe = False
    visto = pergunta_sim("abra o card no Kommo: tags (escalated), notas do "
                         "agente/humano e tarefa estão lá, SEM lead duplicado?")
    veredito("CRM sync", existe and visto)


def teste_j_learning(lead: int) -> None:
    log_rel("\n===== TESTE J — LEARNING =====")
    vault = Path(__file__).resolve().parent.parent.parent / "brain/09_LEARNINGS"
    candidatos = sorted(vault.glob("humano - *.md"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidatos:
        veredito("Learning loop", False, "nenhum candidato 'humano - *.md' no vault")
        return
    doc = candidatos[0]
    corpo = doc.read_text(encoding="utf-8")
    log_rel(f"  candidato mais recente: {doc.name}")
    m_status = re.search(r"status: (\S+)", corpo)
    log_rel(f"  status atual: {m_status.group(1) if m_status else '?'}")
    espera_operador(f"no Obsidian (ou editor), mude o status de '{doc.name}' "
                    "para 'approved', salve, e rode: python3 brain/indexer.py")
    sys.path.insert(0, str(vault.parent))
    import importlib
    import indexer
    importlib.reload(indexer)
    hits = indexer.search("own kart inspection bring")
    achou = any("humano" in (h.get("path") or "") for h in hits)
    log_rel(f"  retrieval encontra o documento aprovado? {'SIM' if achou else 'não'}")
    for h in hits[:2]:
        log_rel(f"    hit: {h['path']} (score {h['score']})")
    veredito("Learning loop", achou,
             "nova conversa de qualquer lead já recebe este conhecimento" if achou else "")


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="só a fase 0 (ambiente)")
    ap.add_argument("--lead", type=int, help="lead de teste A (kart próprio)")
    ap.add_argument("--lead-b", type=int, help="lead de teste B (pergunta diferente)")
    args = ap.parse_args()

    log_rel(f"# Validação de produção — {datetime.datetime.now():%d/%m/%Y %H:%M}")
    amb = fase0_ambiente()
    if args.check:
        print("\nAmbiente:", "OK" if amb else "COM PENDÊNCIAS (corrija antes dos testes)")
        return 0 if amb else 1
    if not args.lead:
        print("\nuso: --check  OU  --lead <ID> [--lead-b <ID2>]")
        return 2
    if not amb and not pergunta_sim("ambiente com pendências — continuar mesmo assim?"):
        return 1

    teste_a_novo_lead(args.lead)
    teste_b_continuidade(args.lead)
    teste_c_escalacao(args.lead)
    teste_d_resposta_humana(args.lead)
    teste_e_memoria_pos_handoff(args.lead)
    teste_f_dois_leads(args.lead, args.lead_b)
    # G (entrega real) é o agregado das confirmações visuais acima:
    entregas = [RESULTADOS.get(k) for k in ("New lead", "Human escalation",
                                            "Human response")]
    veredito("Real message delivery", all(v == "PASS" for v in entregas),
             "agregado das confirmações visuais de A, C e D")
    teste_h_followup(args.lead_b)
    teste_i_crm(args.lead)
    teste_j_learning(args.lead)

    # ------------------------------------------------------------- veredito
    ordem = ["New lead", "Conversation continuity", "Customer memory",
             "Human escalation", "Human response", "Resume after handoff",
             "Multi-lead isolation", "Real message delivery", "Follow-up",
             "CRM sync", "Learning loop"]
    log_rel("\n## PRODUCTION VALIDATION\n")
    log_rel("| Test | Result |")
    log_rel("| --- | --- |")
    for t in ordem:
        log_rel(f"| {t} | {RESULTADOS.get(t, 'NOT RUN')} |")
    pronto = all(RESULTADOS.get(t) == "PASS" for t in ordem)
    log_rel(f"\n## FINAL STATUS\n\n{'READY' if pronto else 'NOT READY'}")
    if not pronto:
        falhas = [t for t in ordem if RESULTADOS.get(t) != "PASS"]
        log_rel(f"\nPendentes/falhos: {', '.join(falhas)}")

    destino = URACE_DIR / f"validation-report-{datetime.date.today():%Y%m%d}.md"
    destino.write_text("\n".join(RELATORIO), encoding="utf-8")
    log_rel(f"\nRelatório com evidências: {destino}")
    return 0 if pronto else 1


if __name__ == "__main__":
    sys.exit(main())
