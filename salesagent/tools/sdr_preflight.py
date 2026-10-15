#!/usr/bin/env python3
"""Pré-voo do robô SDR: confere, no VPS, se está tudo no lugar antes de liberar para todos os leads.

Não escreve nada, não manda mensagem a ninguém e não imprime chave nem token. Só diz OK, AVISO ou
FALHA para cada item e termina com código 0 (tudo certo ou só avisos) ou 1 (alguma FALHA).

Uso, no VPS, com o python do bridge:
    ~/.urace/venv/bin/python salesagent/tools/sdr_preflight.py        (ou o python que roda a ponte)
    ... --sem-rede     pula a checagem dos links e do Kommo
"""
import hashlib
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "bridge"))
sys.path.insert(0, str(RAIZ))

SEM_REDE = "--sem-rede" in sys.argv
RESULTADOS = []


def item(nivel, texto):
    RESULTADOS.append(nivel)
    print(f"  {nivel:<5} {texto}")


def main():
    import config

    print("1. Configuração da ponte")
    item("OK" if config.SDR_MODO == "atender" else "FALHA",
         f"nível do robô: {config.SDR_MODO} (precisa ser 'atender' para responder)")
    if config.SDR_ATENDER_SO_TAG:
        item("AVISO", f"escopo de teste LIGADO: só responde card com a tag '{config.SDR_ATENDER_SO_TAG}'. "
                      "Para liberar a todos, apague a linha SDR_ATENDER_SO_TAG de ~/.urace/bridge.env e reinicie a ponte")
    else:
        item("OK", "escopo de teste desligado: o robô responde todo lead no escopo dele")
    item("OK" if config.FOLLOWUP_BOT_ID else "FALHA", "bot de entrega (FOLLOWUP_BOT_ID) configurado")
    item("OK" if config.SALESBOT_DISPLAY == "json_reply" else "AVISO",
         f"modo de entrega: {config.SALESBOT_DISPLAY} (o validado em produção é json_reply)")
    item("OK" if config.AGENT_API_KEY else "FALHA", "chave da ponte (AGENT_API_KEY) existe")
    item("OK" if config.KOMMO_TOKEN else "FALHA", "token do Kommo existe")
    item("OK" if config.BRAIN_RETRIEVAL == "on" else "AVISO", f"base de conhecimento por turno: {config.BRAIN_RETRIEVAL}")

    print("\n2. Persona sincronizada com o repositório")
    repo = RAIZ / "instructions" / "urace-sales-agent.md"
    ws = Path(os.environ.get("OPENCLAW_URACE_SALES_WORKSPACE", Path.home() / ".openclaw/workspace/urace-sales")) / "AGENTS.md"
    if not ws.exists():
        item("FALHA", f"AGENTS.md do agente não encontrado em {ws}")
    else:
        igual = hashlib.sha256(repo.read_bytes()).hexdigest() == hashlib.sha256(ws.read_bytes()).hexdigest()
        item("OK" if igual else "FALHA", "AGENTS.md do agente é idêntico ao do repositório" if igual else
             "AGENTS.md do agente é DIFERENTE do repositório: rode salesagent/tools/sync_agent_instructions.sh e reinicie o gateway")
        chars = len(ws.read_text(encoding="utf-8"))
        item("OK" if chars < 30000 else "AVISO", f"tamanho do AGENTS.md: {chars} caracteres (limite configurado no VPS: 40.000)")

    print("\n3. Links que o robô manda")
    links = {k: v for k, v in config.PROGRAM_LINKS.items() if isinstance(v, str) and v.startswith("http")}
    texto = repo.read_text(encoding="utf-8")
    import re
    links.update({f"persona:{i}": u.rstrip(".,)") for i, u in enumerate(sorted(set(re.findall(r"https?://[^\s)\"']+", texto))))})
    if SEM_REDE:
        item("AVISO", "checagem de links pulada (--sem-rede)")
    else:
        import httpx
        for nome, url in links.items():
            try:
                r = httpx.get(url, follow_redirects=True, timeout=15)
                item("OK" if r.status_code < 400 else "FALHA", f"{r.status_code}  {url}")
            except Exception as exc:  # noqa: BLE001
                item("AVISO" if "youtu" in url or "calendar.app" in url else "FALHA", f"sem resposta ({type(exc).__name__})  {url}")
    item("OK" if config.PROGRAM_LINKS.get("call_link") else "FALHA", "link da call (call_link) configurado")

    print("\n4. Kommo")
    if SEM_REDE:
        item("AVISO", "checagem do Kommo pulada (--sem-rede)")
    else:
        try:
            import httpx
            r = httpx.get(f"https://{config.KOMMO_DOMAIN}/api/v4/account",
                          headers={"Authorization": f"Bearer {config.KOMMO_TOKEN}"}, timeout=15)
            item("OK" if r.status_code == 200 else "FALHA", f"API do Kommo respondeu {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            item("FALHA", f"API do Kommo sem resposta ({type(exc).__name__})")

    print("\n5. Pausas e estado")
    try:
        import pausas
        n = len(pausas.pausadas())
        item("OK", f"{n} conversa(s) com a IA pausada")
    except Exception as exc:  # noqa: BLE001
        item("AVISO", f"não consegui ler as pausas ({type(exc).__name__})")

    falhas = RESULTADOS.count("FALHA")
    avisos = RESULTADOS.count("AVISO")
    print(f"\nResultado: {RESULTADOS.count('OK')} ok, {avisos} aviso(s), {falhas} falha(s)")
    print("PRONTO para liberar." if not falhas else "NÃO libere ainda: corrija as FALHAS acima.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
