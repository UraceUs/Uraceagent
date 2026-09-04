#!/usr/bin/env python3
"""Grava a chave Anthropic íntegra (lida de ~/.urace/anthropic.key) direto no
auth_profile_store dos agentes, limpa o cooldown de auth e corrige o modelo
do urace-sales. Zero clipboard.

Uso: python3 salesagent/tools/fix_key.py
"""
import json
import os
import sqlite3
import subprocess
import sys

HOME = os.path.expanduser("~")
KEY_FILE = os.path.join(HOME, ".urace", "anthropic.key")
AGENTS = ["main", "urace-sales"]


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return (p.stdout + p.stderr).strip()


def main():
    key = open(KEY_FILE).read().strip()
    if not key.startswith("sk-ant-api03-") or len(key) < 80:
        sys.exit(f"ABORTADO: chave em {KEY_FILE} parece inválida "
                 f"(len={len(key)}, prefixo={key[:12]!r}). Corrija o arquivo primeiro.")
    print(f"chave OK: {key[:12]}...{key[-4:]} ({len(key)} chars)")

    print("\nparando gateway (evita que ele regrave o valor antigo)...")
    print(run(["openclaw", "gateway", "stop"])[:200])

    for name in AGENTS:
        db = os.path.join(HOME, ".openclaw", "agents", name, "agent", "openclaw-agent.sqlite")
        if not os.path.exists(db):
            print(f"{name}: sqlite ausente, pulando")
            continue
        con = sqlite3.connect(db)
        row = con.execute(
            "SELECT store_json FROM auth_profile_store WHERE store_key='primary'").fetchone()
        store = json.loads(row[0]) if row else {"version": 1, "profiles": {}}
        store.setdefault("profiles", {})["anthropic:default"] = {
            "type": "api_key", "provider": "anthropic", "key": key}
        con.execute(
            "INSERT OR REPLACE INTO auth_profile_store (store_key, store_json, updated_at) "
            "VALUES ('primary', ?, strftime('%s','now')*1000)", (json.dumps(store),))
        con.execute("DELETE FROM auth_profile_state")  # limpa cooldown de auth
        con.commit()
        con.close()
        print(f"{name}: chave gravada + cooldown limpo")

    # corrige o modelo do urace-sales no config global (opus-4-8 -> sonnet-5)
    cfg_path = os.path.join(HOME, ".openclaw", "openclaw.json")
    cfg = json.loads(open(cfg_path).read())
    for a in cfg.get("agents", {}).get("list", []):
        if a.get("id") == "urace-sales" and a.get("model") != "anthropic/claude-sonnet-5":
            a["model"] = "anthropic/claude-sonnet-5"
            open(cfg_path, "w").write(json.dumps(cfg, indent=2))
            print("urace-sales: modelo corrigido para anthropic/claude-sonnet-5")

    print("\nreiniciando gateway...")
    print(run(["openclaw", "gateway", "restart"])[:200])

    print("\n--- teste main ---")
    print(run(["openclaw", "agent", "--agent", "main", "--session-key", "fixk1",
               "-m", "Say OK"])[:500])
    print("\n--- teste urace-sales ---")
    print(run(["openclaw", "agent", "--agent", "urace-sales", "--session-key", "fixk2",
               "-m", "Hi, how much is a training day?"])[:900])


if __name__ == "__main__":
    main()
