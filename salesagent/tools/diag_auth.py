#!/usr/bin/env python3
"""Diagnóstico (e conserto) da autenticação Anthropic dos agentes OpenClaw.

Uso:
    python3 salesagent/tools/diag_auth.py           # só diagnostica
    python3 salesagent/tools/diag_auth.py --fix     # diagnostica e tenta consertar

Compara o agente que FUNCIONA (main) com o que FALHA (urace-sales), encontra onde
a credencial realmente vive (config global, models.json do agente, sqlite do agente)
e, com --fix, replica a credencial boa para o agente quebrado.

Segredos são mascarados na saída — pode colar/printar o resultado com segurança.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

HOME = os.path.expanduser("~")
OC = os.path.join(HOME, ".openclaw")
GOOD = "main"
BAD = "urace-sales"
FIX = "--fix" in sys.argv


def mask(s: str) -> str:
    s = re.sub(r"(sk-ant-[a-z0-9]+-)[A-Za-z0-9_\-]{6,}", r"\1<MASCARADO>", s)
    s = re.sub(r"(ey[A-Za-z0-9_\-]{10,})", "<JWT-MASCARADO>", s)
    s = re.sub(r'("(?:access_token|refresh_token|apiKey|api_key|token|secret)"\s*:\s*")[^"]{8,}',
               r"\1<MASCARADO>", s)
    return s


def head(title: str) -> None:
    print(f"\n{'=' * 8} {title} {'=' * 8}")


def agent_dir(name: str) -> str:
    return os.path.join(OC, "agents", name, "agent")


def dump_json_auth(path: str, label: str) -> dict:
    head(label)
    if not os.path.exists(path):
        print("AUSENTE:", path)
        return {}
    raw = open(path).read()
    print(mask(raw)[:1500])
    try:
        return json.loads(raw)
    except Exception as exc:
        print("(json inválido:", exc, ")")
        return {}


def sqlite_report(name: str) -> dict:
    """Lista tabelas e conteúdo de tabelas que cheiram a auth/credencial."""
    db = os.path.join(agent_dir(name), "openclaw-agent.sqlite")
    out = {}
    head(f"SQLITE {name}")
    if not os.path.exists(db):
        print("AUSENTE:", db)
        return out
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        print("tabelas:", ", ".join(tables))
        for t in tables:
            if not any(k in t.lower() for k in ("auth", "cred", "profile", "model", "provider")):
                continue
            cur = con.execute(f'SELECT * FROM "{t}" LIMIT 10')
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            out[t] = (cols, rows)
            print(f"\n-- {t} ({len(rows)} linhas) cols={cols}")
            for r in rows:
                print("   ", mask(str(r))[:300])
        con.close()
    except Exception as exc:
        print("erro lendo sqlite:", exc)
    return out


def run(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (p.stdout + p.stderr).strip()
    except Exception as exc:
        return f"(falhou: {exc})"


def main() -> None:
    print("DIAGNÓSTICO DE AUTENTICAÇÃO — OpenClaw")
    print("bom:", GOOD, "| quebrado:", BAD, "| modo:", "FIX" if FIX else "somente leitura")

    # 1. Config global
    gcfg = dump_json_auth(os.path.join(OC, "openclaw.json"), "CONFIG GLOBAL (openclaw.json)")
    if gcfg:
        head("CONFIG GLOBAL — chaves de auth/modelo")
        def walk(o, p=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    kl = k.lower()
                    if any(x in kl for x in ("auth", "key", "token", "mode", "provider", "model")) \
                            and not isinstance(v, (dict, list)):
                        print(f"  {p}{k} = {mask(str(v))[:80]}")
                    walk(v, f"{p}{k}.")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{p}[{i}].")
        walk(gcfg)

    # 2. models.json de cada agente
    for name in (GOOD, BAD):
        dump_json_auth(os.path.join(agent_dir(name), "models.json"), f"models.json — {name}")

    # 3. Arquivos presentes em cada agent dir
    for name in (GOOD, BAD):
        head(f"ARQUIVOS — {name}")
        d = agent_dir(name)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                print(" ", f, os.path.getsize(os.path.join(d, f)), "bytes")
        else:
            print("AUSENTE:", d)

    # 4. SQLite dos dois
    good_tables = sqlite_report(GOOD)
    bad_tables = sqlite_report(BAD)

    # 5. models status
    for name in (GOOD, BAD):
        head(f"openclaw models status --agent {name}")
        print(mask(run(["openclaw", "models", "status", "--agent", name]))[:1200])

    # 6. Env do serviço
    head("ENV DO GATEWAY (systemd)")
    print(mask(run(["systemctl", "--user", "show", "openclaw-gateway", "-p", "Environment"]))[:400])

    # 7. Diferença de tabelas de auth
    head("COMPARAÇÃO DE TABELAS DE AUTH")
    keys = set(good_tables) | set(bad_tables)
    for t in sorted(keys):
        g = len(good_tables.get(t, ((), ()))[1])
        b = len(bad_tables.get(t, ((), ()))[1])
        flag = "  <-- DIFERENÇA" if g != b else ""
        print(f"  {t}: {GOOD}={g} linhas, {BAD}={b} linhas{flag}")

    if not FIX:
        head("PRÓXIMO PASSO")
        print("Rode com --fix para replicar a credencial do agente que funciona:")
        print("  python3 salesagent/tools/diag_auth.py --fix")
        return

    # ---------------- FIX ----------------
    head("APLICANDO CORREÇÃO")
    changed = False

    # 7a. Copiar linhas de tabelas de auth do bom para o quebrado
    src_db = os.path.join(agent_dir(GOOD), "openclaw-agent.sqlite")
    dst_db = os.path.join(agent_dir(BAD), "openclaw-agent.sqlite")
    auth_tables = [t for t in good_tables if any(
        k in t.lower() for k in ("auth", "cred", "profile"))]
    if auth_tables and os.path.exists(dst_db):
        shutil.copy2(dst_db, dst_db + ".bak")
        print("backup:", dst_db + ".bak")
        try:
            con = sqlite3.connect(dst_db)
            con.execute(f"ATTACH DATABASE '{src_db}' AS good")
            for t in auth_tables:
                try:
                    con.execute(f'DELETE FROM "{t}"')
                    con.execute(f'INSERT INTO "{t}" SELECT * FROM good."{t}"')
                    print(f"  tabela {t}: replicada de {GOOD}")
                    changed = True
                except Exception as exc:
                    print(f"  tabela {t}: falhou ({exc})")
            con.commit()
            con.execute("DETACH DATABASE good")
            con.close()
        except Exception as exc:
            print("  erro no sqlite:", exc)

    # 7b. Garantir models.json igual ao do agente bom
    src_json = os.path.join(agent_dir(GOOD), "models.json")
    dst_json = os.path.join(agent_dir(BAD), "models.json")
    if os.path.exists(src_json):
        shutil.copy2(src_json, dst_json)
        print("models.json replicado de", GOOD)
        changed = True

    if not changed:
        print("nada foi alterado — cole a saída acima para análise")
        return

    head("REINICIANDO E TESTANDO")
    print(run(["openclaw", "gateway", "restart"])[:300])
    print("\n--- teste", GOOD, "---")
    print(mask(run(["openclaw", "agent", "--agent", GOOD, "--session-key", "diag1",
                    "-m", "Say OK"]))[:600])
    print("\n--- teste", BAD, "---")
    print(mask(run(["openclaw", "agent", "--agent", BAD, "--session-key", "diag2",
                    "-m", "Hi, how much is a training day?"]))[:900])


if __name__ == "__main__":
    main()
