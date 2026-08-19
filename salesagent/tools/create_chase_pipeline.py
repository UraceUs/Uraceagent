#!/usr/bin/env python3
"""Cria (uma vez) o pipeline dedicado do Chase no Kommo, com os 13 estagios
conceituais do documento "URACE Automated Lead Qualification System" secao
18, e salva o mapeamento real (pipeline_id + status ids) em
salesagent/config/kommo-pipeline-chase.json — o config.py da ponte passa a
usar esse arquivo automaticamente assim que ele existir.

Idempotente: se um pipeline com esse nome ja existir, so re-le e regrava o
arquivo, sem duplicar.

As tags de qualificacao (academy-price-aware, academy-qualified,
current-racer-qualified, one-day-checkout-sent, escalated) NAO precisam ser
pre-criadas: o Kommo cria uma tag automaticamente na primeira vez que ela e
aplicada a um lead via API. Elas ficam listadas aqui só para documentacao.

Uso: python3 salesagent/tools/create_chase_pipeline.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

HOME = os.path.expanduser("~")


def load_env(path):
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


env = load_env(os.path.join(HOME, ".urace", "kommo.env"))
TOKEN = env["KOMMO_TOKEN"]
DOMAIN = env["KOMMO_DOMAIN"].rstrip("/")
BASE = f"https://{DOMAIN}/api/v4"

PIPELINE_NAME = "Chase — AI Sales Funnel"

STAGE_NAMES = [
    "New Inquiry",
    "Contact Information Collected",
    "Program Recommended",
    "Information Sent",
    "Academy Price-Aware",
    "Academy Qualified",
    "Academy Call Scheduled",
    "Current Racer Qualified",
    "Racing Call Scheduled",
    "One-Day Checkout Sent",
    "Payment Received",
    "Scheduling Required",
    "Nurture",
]

TAGS = [
    "academy-price-aware",
    "academy-qualified",
    "current-racer-qualified",
    "one-day-checkout-sent",
    "escalated",
]


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


def find_existing():
    data = api("GET", "/leads/pipelines")
    for p in data.get("_embedded", {}).get("pipelines", []):
        if p["name"] == PIPELINE_NAME:
            return p
    return None


def create():
    body = {
        "name": PIPELINE_NAME,
        "_embedded": {
            "statuses": [{"name": n, "sort": (i + 1) * 10}
                         for i, n in enumerate(STAGE_NAMES)]
        },
    }
    # Kommo v4 tem variacoes de formato entre contas/versoes para "criar um
    # recurso" — tenta objeto unico primeiro, depois envelope de array.
    for label, payload in (("objeto único", body), ("array", [body])):
        try:
            resp = api("POST", "/leads/pipelines", payload)
        except urllib.error.HTTPError as e:
            print(f"  formato '{label}' falhou: {e.code} {e.read().decode()[:300]}")
            continue
        pid = None
        if isinstance(resp, dict):
            emb = resp.get("_embedded", {})
            if "pipelines" in emb and emb["pipelines"]:
                pid = emb["pipelines"][0]["id"]
            elif "id" in resp:
                pid = resp["id"]
        if pid:
            print(f"  criado com formato '{label}' (id {pid})")
            return api("GET", f"/leads/pipelines/{pid}")
    sys.exit("ABORTADO: não foi possível criar o pipeline em nenhum formato conhecido.")


def main():
    print(f"Verificando se '{PIPELINE_NAME}' já existe...")
    existing = find_existing()
    if existing:
        print(f"Já existe (id {existing['id']}) — relendo, nada será criado.")
        pipeline = api("GET", f"/leads/pipelines/{existing['id']}")
    else:
        print(f"Criando pipeline '{PIPELINE_NAME}' com {len(STAGE_NAMES)} estágios...")
        pipeline = create()

    stages = {}
    for s in pipeline["_embedded"]["statuses"]:
        key = s["name"].lower().replace(" ", "_").replace("-", "_")
        stages[key] = {"id": s["id"], "name": s["name"]}

    out = {
        "_meta": {
            "source": "criado via create_chase_pipeline.py",
            "pipeline_name": PIPELINE_NAME,
            "note": "Pipeline operado pelo agente Chase (nao e o 'Sales funnel' "
                    "original, usado pelo time humano). Tags de qualificacao "
                    "aplicadas pelo agente (nao sao estagios, criam-se sozinhas "
                    "no primeiro uso): " + ", ".join(TAGS),
        },
        "pipeline_id": pipeline["id"],
        "pipeline_name": pipeline["name"],
        "stages": stages,
        "tags": TAGS,
    }

    out_path = os.path.join(HOME, "Uraceagent", "salesagent", "config",
                             "kommo-pipeline-chase.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSalvo em {out_path}")
    print("\nCONTEÚDO (cole de volta no chat para eu commitar oficialmente):\n")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
