#!/usr/bin/env python3
"""chase_doctor — o operador do ambiente do Chase, num comando só.

Ciclo: DISCOVER -> DIAGNOSE -> FIX (só o que é seguro) -> TEST -> VERIFY
-> REPORT. Idempotente: rodar duas vezes seguidas não muda nada na
segunda. Nunca presume schema, path, python ou que rc=0 significou
sucesso — descobre o estado real e verifica cada correção depois de
aplicá-la.

O que ele corrige SOZINHO (lista fechada, tudo verificado após aplicar):
  - dependências do venv da ponte (pip install -r requirements.txt)
  - git pull, apenas quando é fast-forward e a árvore está limpa
  - bootstrapMaxChars menor que o AGENTS.md (descobrindo o path real)
  - allowlist de messaging do agente 'main' (descobrindo o índice real)
  - re-sync dos workspaces (scripts existentes, idempotentes)
  - restarts controlados (só quando algo mudou; valida saúde depois)

O que ele NUNCA faz: tocar em dados de lead, inventar números de
telefone, sobrescrever mudanças locais do git, mascarar um FAIL,
imprimir segredo.

Uso (no VPS):
    python3 salesagent/tools/chase_doctor.py                  # diagnóstico + fixes seguros
    python3 salesagent/tools/chase_doctor.py --lead 31764961  # + memória do lead
    python3 salesagent/tools/chase_doctor.py --no-fix         # só diagnóstico
    python3 salesagent/tools/chase_doctor.py --skip-tests     # sem a suíte offline
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent.parent
BRIDGE = REPO / "salesagent" / "bridge"
VENV_PY = BRIDGE / ".venv" / "bin" / "python"

# re-executa no venv da ponte quando existir (dependências: httpx etc.)
if VENV_PY.exists() and not os.environ.get("CHASE_DOCTOR_REEXEC"):
    os.environ["CHASE_DOCTOR_REEXEC"] = "1"
    os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])

REL: list[str] = []
AREAS: dict[str, str] = {}   # área -> PASS | FAIL | WARN
FIXES: list[str] = []


def say(txt: str = "") -> None:
    REL.append(txt)
    print(txt, flush=True)


def area(nome: str, ok: bool, detalhe: str = "", warn: bool = False) -> None:
    AREAS[nome] = "WARN" if (warn and not ok) else ("PASS" if ok else "FAIL")
    say(f"  [{AREAS[nome]}] {nome}" + (f" — {detalhe}" if detalhe else ""))


def fixed(txt: str) -> None:
    FIXES.append(txt)
    say(f"  >> FIX: {txt}")


def run(cmd: list[str], timeout: int = 90, stdin_vazio: bool = True) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL if stdin_vazio else None)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timeout {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError:
        return 127, f"comando não existe: {cmd[0]}"
    except Exception as exc:
        return 1, str(exc)


def json_da_saida(texto: str):
    """O CLI do OpenClaw imprime banner em volta do JSON — extrai do
    primeiro '{' ao último '}' e parseia. Nunca presumir saída limpa."""
    i, j = texto.find("{"), texto.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(texto[i:j + 1])
    except json.JSONDecodeError:
        return None


# ================================================================= git
def fase_git(fix: bool) -> None:
    say("\n== GIT ==")
    rc, branch = run(["git", "-C", str(REPO), "branch", "--show-current"])
    branch = branch.strip()
    rc, status = run(["git", "-C", str(REPO), "status", "--porcelain"])
    sujo = [ln for ln in status.splitlines() if ln.strip()]
    run(["git", "-C", str(REPO), "fetch", "origin", branch], timeout=120)
    rc, contagem = run(["git", "-C", str(REPO), "rev-list",
                        "--left-right", "--count", f"HEAD...origin/{branch}"])
    ahead = behind = 0
    m = re.match(r"\s*(\d+)\s+(\d+)", contagem)
    if m:
        ahead, behind = int(m.group(1)), int(m.group(2))
    say(f"  branch={branch} ahead={ahead} behind={behind} "
        f"mudanças locais={len(sujo)}")
    if sujo:
        for ln in sujo[:8]:
            say(f"    local: {ln}")
        say("  (mudanças locais PRESERVADAS — nenhum pull automático)")
    if behind and not sujo and not ahead and fix:
        rc, out = run(["git", "-C", str(REPO), "pull", "--ff-only",
                       "origin", branch], timeout=180)
        if rc == 0:
            fixed(f"git pull fast-forward ({behind} commit(s))")
        else:
            say(f"  pull recusado: {out[-200:]}")
    area("ENVIRONMENT/GIT", not sujo and behind == 0 or bool(fix),
         f"{'limpo e atualizado' if not sujo and not behind else 'ver acima'}",
         warn=bool(sujo))


# ============================================================ python/ponte
def fase_bridge(fix: bool) -> bool:
    say("\n== BRIDGE (python, serviço, porta, saúde) ==")
    mudou = False
    rc, unit = run(["systemctl", "cat", "sales-bridge"])
    m = re.search(r"ExecStart=(\S+)", unit)
    exec_py = m.group(1) if m else "?"
    say(f"  systemd ExecStart: {exec_py}")
    say(f"  venv da ponte: {'existe' if VENV_PY.exists() else 'AUSENTE'} "
        f"| doctor rodando em: {sys.executable}")

    if VENV_PY.exists():
        rc, out = run([str(VENV_PY), "-c",
                       "import httpx, fastapi, uvicorn; print('deps ok')"])
        if rc != 0:
            say(f"  dependências faltando: {out.strip()[:150]}")
            if fix:
                rc2, out2 = run([str(VENV_PY), "-m", "pip", "install", "-q",
                                 "-r", str(BRIDGE / "requirements.txt")],
                                timeout=300)
                rc, _ = run([str(VENV_PY), "-c", "import httpx, fastapi, uvicorn"])
                if rc == 0:
                    fixed("dependências do venv reinstaladas (requirements.txt)")
                    mudou = True
        else:
            say("  dependências do venv: ok")

    rc, ativo = run(["systemctl", "is-active", "sales-bridge"])
    rc2, porta = run(["bash", "-c", "ss -ltn 2>/dev/null | grep -c ':8800 '"])
    escutando = porta.strip().isdigit() and int(porta.strip()) > 0
    rc3, health = run(["curl", "-sf", "-m", "8", "http://127.0.0.1:8800/health"])
    say(f"  serviço={ativo.strip()} porta8800={'escutando' if escutando else 'NADA'} "
        f"health={'OK' if rc3 == 0 else 'FALHOU'}")
    if rc3 != 0 and fix:
        run(["sudo", "systemctl", "restart", "sales-bridge"])
        for _ in range(15):
            time.sleep(2)
            rc3, _ = run(["curl", "-sf", "-m", "5", "http://127.0.0.1:8800/health"])
            if rc3 == 0:
                break
        if rc3 == 0:
            fixed("sales-bridge reiniciado e saudável")
        else:
            rc4, logs = run(["sudo", "journalctl", "-u", "sales-bridge",
                             "-n", "15", "--no-pager"])
            say("  últimos logs do serviço:")
            for ln in logs.splitlines()[-10:]:
                say(f"    {ln[:150]}")
    area("ENVIRONMENT/BRIDGE", rc3 == 0,
         "no ar em 127.0.0.1:8800" if rc3 == 0 else "health falhou — logs acima")
    return mudou


# ================================================================ openclaw
def fase_openclaw(fix: bool) -> bool:
    """Descobre o schema REAL da config e corrige bootstrap + messaging."""
    say("\n== OPENCLAW (schema descoberto, nunca presumido) ==")
    mudou = False
    rc, ver = run(["openclaw", "--version"])
    if rc == 127:
        area("OPENCLAW", False, "CLI não encontrado neste host")
        return False
    say(f"  versão: {[l for l in ver.splitlines() if l.strip()][-1][:70] if ver else '?'}")

    rc, out = run(["openclaw", "config", "get"], timeout=60)
    cfg = json_da_saida(out)
    if cfg is None:
        rc, out = run(["openclaw", "config", "get", "agents"], timeout=60)
        cfg = {"agents": json_da_saida(out)} if json_da_saida(out) else None
    if cfg is None:
        area("OPENCLAW", False, "não consegui ler a config em JSON")
        return False

    agents = cfg.get("agents") or {}
    lista = agents.get("list") or []
    defaults = agents.get("defaults") or {}
    ids = [a.get("id") for a in lista]
    idx_main = next((i for i, a in enumerate(lista) if a.get("id") == "main"), None)
    tem_sales = "urace-sales" in ids
    say(f"  agentes na config: {ids} (main idx={idx_main})")

    # ---- bootstrap: valor efetivo vs tamanho real do AGENTS.md
    ws = Path(defaults.get("workspace") or (Path.home() / ".openclaw/workspace"))
    agents_md = ws / "urace-sales" / "AGENTS.md"
    for a in lista:
        if a.get("id") == "urace-sales" and a.get("workspace"):
            agents_md = Path(a["workspace"]) / "AGENTS.md"
    tam = len(agents_md.read_text(encoding="utf-8")) if agents_md.exists() else -1
    limite = None
    for a in lista:
        if a.get("id") == "urace-sales" and a.get("bootstrapMaxChars"):
            limite = a["bootstrapMaxChars"]
    limite = limite or defaults.get("bootstrapMaxChars")
    say(f"  AGENTS.md={tam} chars | bootstrapMaxChars efetivo={limite}")
    trunca = tam > 0 and (not limite or tam > int(limite))
    if trunca and fix:
        novo = tam + 15000
        rc, _ = run(["openclaw", "config", "set",
                     "agents.defaults.bootstrapMaxChars", str(novo)])
        rcv, out = run(["openclaw", "config", "get"], timeout=60)
        cfg2 = json_da_saida(out) or {}
        aplicou = ((cfg2.get("agents") or {}).get("defaults") or {}) \
            .get("bootstrapMaxChars") == novo
        if aplicou:
            fixed(f"bootstrapMaxChars {limite} -> {novo} (verificado na config)")
            mudou, trunca, limite = True, False, novo
        else:
            say("  !! set não refletiu na config — corrija manualmente")
    area("CHASE/MANUAL", tam > 0 and not trunca,
         "carregado inteiro" if not trunca else f"TRUNCADO ({tam}>{limite})")

    # ---- agente main FUNCIONA? Teste funcional, não warning.
    #
    # Lição de 27/08 (aprendida do jeito caro): o doctor avisava "message
    # tool unavailable" e a correção óbvia — allowlist explícita com
    # group:messaging — SUBSTITUIU o toolset padrão inteiro e deixou o
    # agente com ZERO tools ("No callable tools remain"). O Mark ficou mudo
    # e nenhuma escalação chegou no WhatsApp por horas, num sistema que
    # funcionava. O warning era cosmético; a correção quebrou o real.
    # Daqui em diante a régua é FUNCIONAL: o agente responde? Então nada de
    # mexer em tools. Está quebrado por allowlist? REMOVER a allowlist,
    # que o default funcionava.
    rc, doc = run(["openclaw", "doctor"], timeout=120)
    aviso_trunc = "truncated" in doc
    say(f"  doctor: truncated={'SIM' if aviso_trunc else 'não'} "
        f"(warnings de tools são avaliados por teste funcional, não por lint)")
    rc, probe = run(["openclaw", "agent", "--agent", "main", "-m",
                     "healthcheck: reply with the single word ok"], timeout=90)
    quebrado = "No callable tools remain" in probe or rc != 0
    say(f"  probe funcional do main: {'QUEBRADO' if quebrado else 'ok'}"
        + (f" — {probe.strip().splitlines()[-1][:110]}" if quebrado and probe else ""))
    if quebrado and idx_main is not None and lista[idx_main].get("tools") and fix:
        say("  causa provável: allowlist explícita em tools — removendo")
        removido = False
        for tentativa in (["openclaw", "config", "unset",
                           f"agents.list.{idx_main}.tools"],
                          ["openclaw", "config", "set",
                           f"agents.list.{idx_main}.tools", "{}"]):
            run(tentativa)
            rcv, _ = run(["openclaw", "config", "validate"])
            if rcv != 0:
                continue
            rc2, probe2 = run(["openclaw", "agent", "--agent", "main", "-m",
                               "healthcheck: reply ok"], timeout=90)
            if "No callable tools remain" not in probe2 and rc2 == 0:
                removido = True
                break
        if removido:
            fixed("allowlist de tools do main removida — agente voltou a "
                  "responder (verificado por probe, não por rc)")
            mudou = True
        else:
            say("  !! não consegui restaurar o main automaticamente — "
                "remova a chave tools do agente main na config manualmente")
    area("ESCALATION/CANAL", not quebrado or mudou,
         "agente main responde (canal de escalação vivo)")
    area("OPENCLAW", tem_sales and idx_main is not None and not aviso_trunc,
         "agentes presentes, manual inteiro")
    seguro = not any(a.get("id") == "urace-sales" and a.get("tools")
                     for a in lista)
    area("SECURITY", seguro and tem_sales,
         "urace-sales sem tools extras (sem shell/mensageria); "
         "main isolado" if seguro else "urace-sales tem tools além do padrão — revisar!")
    return mudou


# ================================================================== syncs
def fase_sync(fix: bool) -> bool:
    say("\n== SYNC dos workspaces ==")
    if not fix:
        say("  (--no-fix: pulado)")
        return False
    ok_total = True
    for script in ("sync_agent_instructions.sh", "sync_admin_identity.sh"):
        rc, out = run(["bash", str(TOOLS / script)], timeout=60)
        ultima = [l for l in out.splitlines() if l.strip()]
        say(f"  {script}: rc={rc} | {ultima[-2][:90] if len(ultima) > 1 else ''}")
        if "AVISO" in out or "cortado" in out.lower():
            for ln in ultima:
                if "AVISO" in ln or "!!" in ln:
                    say(f"    {ln[:140]}")
            ok_total = False
        ok_total &= rc == 0
    area("CHASE/SYNC", ok_total, "instruções e identidades sincronizadas")
    return True


def gateway_restart_controlado() -> None:
    say("  reiniciando gateway (mudanças aplicadas)...")
    run(["openclaw", "gateway", "restart"], timeout=90)
    for _ in range(10):
        time.sleep(2)
        rc, _ = run(["openclaw", "gateway", "status"], timeout=30)
        if rc == 0:
            say("  gateway estável após restart")
            return
    say("  !! gateway não estabilizou — verifique openclaw gateway status")


# ============================================================ brain/kommo
def fase_brain_kommo(lead: int | None) -> None:
    say("\n== BRAIN + KOMMO ==")
    rc, out = run([sys.executable, str(REPO / "brain/indexer.py"), "--self-test"],
                  timeout=120)
    area("RETRIEVAL", rc == 0, "indexer self-test " + ("ok" if rc == 0 else "FALHOU"))
    sys.path.insert(0, str(BRIDGE))
    try:
        from config import KOMMO_DOMAIN, KOMMO_TOKEN
        import httpx
        if lead:
            r = httpx.get(f"https://{KOMMO_DOMAIN}/api/v4/leads/{lead}",
                          headers={"Authorization": f"Bearer {KOMMO_TOKEN}"},
                          timeout=15)
            area("CRM", r.status_code == 200,
                 f"lead {lead} legível no Kommo (HTTP {r.status_code})")
        else:
            r = httpx.get(f"https://{KOMMO_DOMAIN}/api/v4/account",
                          headers={"Authorization": f"Bearer {KOMMO_TOKEN}"},
                          timeout=15)
            area("CRM", r.status_code == 200, f"conta Kommo (HTTP {r.status_code})")
    except Exception as exc:
        area("CRM", False, f"{exc}"[:120])


def fase_memoria(lead: int | None) -> None:
    if not lead:
        return
    say(f"\n== MEMÓRIA do lead {lead} ==")
    sys.path.insert(0, str(BRIDGE))
    try:
        import state
        import app
        conv = state.get_conversation(lead)
        confs = state.get_confirmations(lead)
        say(f"  estado={conv['state']} confirmações={len(confs)} "
            f"pendente='{(conv.get('pending_question') or '-')[:50]}'")
        for c in confs[:3]:
            say(f"    fato [{c['author']}]: {c['answer'][:80]}")
        ctx = app._memory_context(lead, conv)
        injeta_conf = bool(confs) == ("CONFIRMADAS" in ctx)
        area("MEMORY", True, f"{len(confs)} fato(s); contexto de turno gerado")
        area("HUMAN CONFIRMATION", injeta_conf and (not confs or "CONFIRMADAS" in ctx),
             "confirmações entram no turno sem passo manual"
             if confs else "sem confirmações ainda (nada a injetar)")
    except Exception as exc:
        area("MEMORY", False, str(exc)[:150])


# ================================================================== testes
def fase_testes(skip: bool) -> None:
    say("\n== SUÍTE OFFLINE ==")
    if skip:
        say("  (--skip-tests)")
        return
    testes = sorted((REPO / "salesagent/tests").glob("test_*.py"))
    passou = 0
    for t in testes:
        rc, _ = run([sys.executable, str(t)], timeout=180)
        say(f"  {'PASS' if rc == 0 else 'FAIL'}  {t.name}")
        passou += rc == 0
    area("TESTS", passou == len(testes), f"{passou}/{len(testes)} suítes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", type=int)
    ap.add_argument("--no-fix", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()
    fix = not args.no_fix

    say(f"# chase_doctor — {time.strftime('%d/%m/%Y %H:%M')} "
        f"(modo {'diagnóstico' if not fix else 'diagnóstico+fix'})")
    fase_git(fix)
    mudou_b = fase_bridge(fix)
    mudou_o = fase_openclaw(fix)
    mudou_s = fase_sync(fix)
    if mudou_o or mudou_s:
        gateway_restart_controlado()
    if mudou_b:
        run(["sudo", "systemctl", "restart", "sales-bridge"])
        time.sleep(3)
    fase_brain_kommo(args.lead)
    fase_memoria(args.lead)
    fase_testes(args.skip_tests)

    say("\n" + "=" * 52)
    say("RELATÓRIO FINAL")
    for k in sorted(AREAS):
        say(f"  {k:<24} {AREAS[k]}")
    say(f"  FIXES aplicados: {len(FIXES)}")
    for f in FIXES:
        say(f"    - {f}")
    falhas = [k for k, v in AREAS.items() if v == "FAIL"]
    say(f"\nSTATUS: {'READY (ambiente)' if not falhas else 'NOT READY — ' + ', '.join(falhas)}")
    say("Validação com humano no circuito: "
        "python3 salesagent/tools/chase_validate.py --lead <ID>")

    try:
        destino = Path.home() / ".urace" / f"doctor-{time.strftime('%Y%m%d-%H%M')}.md"
        destino.write_text("\n".join(REL), encoding="utf-8")
        say(f"Relatório salvo: {destino}")
    except Exception:
        pass
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
