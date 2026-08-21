#!/usr/bin/env python3
"""Roda os cenários de teste do Chase (salesagent/tests/scenarios.json) contra
o agente real no OpenClaw, uma sessão isolada por cenário, e checa as regras
automáticas (regex) definidas em global_checks contra TODAS as respostas.

Isto testa o MODELO diretamente via CLI (openclaw agent), não a ponte inteira
-- é o nível certo de teste para agora, antes do circuito completo com Kommo
estar ligado. As checagens "expect_manual_review" ficam impressas para você
(ou eu) avaliar lendo a transcrição -- não são automatizáveis por regex com
segurança (julgamento de tom, roteamento correto etc.).

Uso:
    python3 salesagent/tests/run_scenarios.py                # roda todos
    python3 salesagent/tests/run_scenarios.py --only 08 12    # so esses ids (prefixo)
    python3 salesagent/tests/run_scenarios.py --agent urace-sales
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS_PATH = HERE / "scenarios.json"
BRIDGE_DIR = HERE.parent / "bridge"
sys.path.insert(0, str(BRIDGE_DIR))
import textproc  # noqa: E402 -- mesma função que a ponte usa antes de enviar ao cliente


class AgentCallError(Exception):
    """Uma chamada ao CLI do OpenClaw travou ou falhou (timeout, gateway
    fora, etc.) -- não é uma violação de regra, é a infraestrutura de
    teste falhando. Isolado por cenário para não derrubar a suíte inteira
    (achado em 21/08: um único timeout matava os 16 cenários restantes)."""


def run_agent(agent: str, session_key: str, message: str, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--agent", agent, "--session-key", session_key,
             "-m", message],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentCallError(f"timeout após {timeout}s") from exc
    except OSError as exc:
        raise AgentCallError(f"falha ao chamar openclaw: {exc}") from exc
    if result.returncode != 0:
        raise AgentCallError(
            f"exit code {result.returncode}: {(result.stderr or '').strip()[:300]}")
    return (result.stdout or "").strip()


def check_global(text: str, checks: list[dict]) -> list[dict]:
    hits = []
    for c in checks:
        if re.search(c["pattern"], text):
            hits.append(c)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="urace-sales")
    ap.add_argument("--only", nargs="*", default=None,
                     help="IDs (ou prefixos de ID) de cenários a rodar")
    ap.add_argument("--sleep", type=float, default=1.0,
                     help="pausa entre turnos, segundos")
    args = ap.parse_args()

    data = json.loads(SCENARIOS_PATH.read_text())
    global_checks = data["global_checks"]["must_not"]
    scenarios = data["scenarios"]
    if args.only:
        scenarios = [s for s in scenarios
                     if any(s["id"].startswith(o) for o in args.only)]

    run_tag = str(int(time.time()))
    total = len(scenarios)
    failed = 0
    errored = []

    print(f"Rodando {total} cenário(s) contra --agent {args.agent}\n")

    for i, sc in enumerate(scenarios, 1):
        sid = sc["id"]
        session_key = f"test-{sid}-{run_tag}"
        print(f"{'=' * 70}")
        print(f"[{i}/{total}] {sid} — {sc.get('category', '')}")
        print(f"fonte: {sc.get('source', '-')}")
        print(f"{'-' * 70}")

        transcript = []
        scenario_hits = []
        seen_directives = []
        call_failed = False
        for turn_n, msg in enumerate(sc["messages"], 1):
            try:
                raw = run_agent(args.agent, session_key, msg)
            except AgentCallError as exc:
                # Infraestrutura falhou (timeout, gateway fora etc.), não é
                # violação de regra -- registra e pula pro próximo cenário
                # em vez de derrubar a suíte inteira.
                print(f"  lead[{turn_n}]: {msg}")
                print(f"  ⚠️  FALHA DE INFRAESTRUTURA: {exc}")
                print()
                errored.append(sid)
                call_failed = True
                break
            # Checa exatamente o que o cliente veria (mesma função que a
            # ponte aplica em app.py: diretivas [[...]] removidas, dash
            # sanitizado) -- não o texto bruto do modelo, que pode conter
            # instrução interna nunca destinada ao lead.
            visible = textproc.customer_facing(raw)
            seen_directives.extend(textproc.extract_directives(raw))
            transcript.append((msg, raw, visible))
            print(f"  lead[{turn_n}]: {msg}")
            print(f"  chase[{turn_n}]: {visible}")
            if visible != raw:
                print(f"  (bruto, p/ auditoria): {raw}")
            print()
            hits = check_global(visible, global_checks)
            scenario_hits.extend(hits)
            time.sleep(args.sleep)

        if call_failed:
            print()
            continue

        scenario_failed = False
        if scenario_hits:
            scenario_failed = True
            print("  ❌ REGRAS VIOLADAS:")
            for h in scenario_hits:
                print(f"     - {h['id']}: {h['reason']} (padrão: {h['pattern']})")
        else:
            print("  ✅ nenhuma regra automática violada")

        # Checklist opcional: para cenários de jornada completa, confirma que
        # cada família de diretiva esperada apareceu ALGUMA vez na sessão
        # inteira -- não valida ORDEM nem conteúdo exato, só presença (prova
        # que aquele processo de fato disparou em algum turno).
        expected_directives = sc.get("expect_directives_any")
        if expected_directives:
            all_directives_text = " | ".join(seen_directives)
            print("  🧩 diretivas esperadas nesta jornada:")
            missing = []
            for key in expected_directives:
                hit = key in all_directives_text
                print(f"     {'✅' if hit else '❌'} {key}")
                if not hit:
                    missing.append(key)
            if missing:
                scenario_failed = True
                print(f"  ❌ processo(s) que nunca disparou/dispararam na sessão: {', '.join(missing)}")

        if scenario_failed:
            failed += 1

        review = sc.get("expect_manual_review")
        if review:
            print(f"\n  👀 revisar manualmente: {review}")
        print()

    print(f"{'=' * 70}")
    ran = total - len(errored)
    print(f"RESUMO: {ran - failed}/{ran} rodados sem violação automática"
          f" ({failed} com violação de regra crítica).")
    if errored:
        print(f"⚠️  {len(errored)} cenário(s) não rodaram por falha de infraestrutura"
              f" (timeout/gateway), não regra: {', '.join(errored)}")
        print(f"   Reroda só esses: python3 {Path(__file__).name} --only "
              + " ".join(s.split('_')[0] for s in errored))
    print("Toda a transcrição acima ainda precisa de revisão manual/humana"
          " para as checagens de julgamento (tom, roteamento correto etc.).")
    return 1 if (failed or errored) else 0


if __name__ == "__main__":
    sys.exit(main())
