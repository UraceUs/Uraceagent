#!/usr/bin/env python3
"""Descobre QUAL rota da API do Kommo dispara um Salesbot nesta conta.

Por que este script existe: `kommo_client.run_bot()` chamava
`POST /api/v4/bots/{id}/run` desde que foi escrito, e isso NUNCA foi
exercitado -- `FOLLOWUP_BOT_ID` sempre esteve vazio em produção, então o
agendador caía direto no fallback de nota. Quando fomos ligar a entrega
espontânea (25/08), duas evidências da conta real apontaram para outra
rota: o `return_url` que o widget manda vive em
`/api/v4/salesbot/{bot}/continue/{id}`, e o JWT do widget_request traz
`"entity_type":"2"` (numérico), não `"leads"`.

Chutar qual está certa seria construir o loop de resposta humana em cima
de uma suposição. Este script tira a dúvida contra a conta real.

É SEGURO rodar num lead de verdade: o bot dispara, chama a ponte, e a
ponte -- sem `pending_followup_text` para aquele lead -- responde que não
tem nada a dizer. Nenhuma mensagem chega ao lead. Confira antes com:
    python3 salesagent/tools/show_recent_audit.py -n 5

Uso (no VPS):
    python3 salesagent/tools/probe_salesbot_run.py --bot 162247 --lead 31764961
"""
import argparse
import json
import os
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent / "bridge"
sys.path.insert(0, str(BRIDGE))

# httpx vive no venv da ponte, não no python do sistema. Em vez de exigir
# que quem roda saiba disso, o script se re-executa com o interpretador
# certo -- uma vez só (URACE_PROBE_REEXEC evita laço se o venv também não
# tiver a dependência).
try:
    import httpx  # noqa: E402
except ModuleNotFoundError:
    _venv = BRIDGE / ".venv" / "bin" / "python"
    if _venv.exists() and not os.environ.get("URACE_PROBE_REEXEC"):
        os.environ["URACE_PROBE_REEXEC"] = "1"
        os.execv(str(_venv), [str(_venv), str(Path(__file__).resolve()), *sys.argv[1:]])
    print("httpx não encontrado. Rode com o python da ponte:")
    print(f"  {_venv} {Path(__file__).resolve()} " + " ".join(sys.argv[1:]))
    sys.exit(2)

from config import KOMMO_DOMAIN, KOMMO_TOKEN  # noqa: E402

BASE = f"https://{KOMMO_DOMAIN}/api/v4"


def rotas(bot_id: int, lead_id: int):
    """As candidatas, na ordem em que run_bot() as tenta."""
    return [
        ("salesbot/run (lista, entity_type=2)", "POST", f"{BASE}/salesbot/run",
         [{"bot_id": bot_id, "entity_id": lead_id, "entity_type": 2}]),
        ("salesbot/run (objeto, entity_type=2)", "POST", f"{BASE}/salesbot/run",
         {"bot_id": bot_id, "entity_id": lead_id, "entity_type": 2}),
        ("bots/{id}/run (entity_type=leads)", "POST", f"{BASE}/bots/{bot_id}/run",
         {"entity_id": lead_id, "entity_type": "leads"}),
        ("bots/{id}/run (entity_type=2)", "POST", f"{BASE}/bots/{bot_id}/run",
         {"entity_id": lead_id, "entity_type": 2}),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", type=int, required=True, help="id do Salesbot (ex.: 162247)")
    ap.add_argument("--lead", type=int, required=True, help="lead_id para o teste")
    args = ap.parse_args()

    if not KOMMO_TOKEN:
        print("KOMMO_TOKEN vazio — confira ~/.urace/kommo.env")
        return 2

    print(f"conta: {KOMMO_DOMAIN} | bot: {args.bot} | lead: {args.lead}\n")
    vencedoras = []
    with httpx.Client(headers={"Authorization": f"Bearer {KOMMO_TOKEN}"},
                      timeout=20) as c:
        for nome, metodo, url, body in rotas(args.bot, args.lead):
            try:
                r = c.request(metodo, url, json=body)
                ok = r.status_code < 300
                print(f"  {'OK  ' if ok else 'FALHA'}  {nome}")
                print(f"         {metodo} {url}")
                print(f"         corpo enviado: {json.dumps(body, ensure_ascii=False)}")
                print(f"         rc={r.status_code}  resposta={r.text[:220]}\n")
                if ok:
                    vencedoras.append(nome)
            except Exception as exc:
                print(f"  ERRO   {nome}: {exc}\n")

    if vencedoras:
        print(f"ROTA(S) QUE A CONTA ACEITA: {', '.join(vencedoras)}")
        print("run_bot() já tenta a primeira delas primeiro — nada a mudar se "
              "a vencedora for 'salesbot/run (lista...)'.")
        print("\nConfira agora se o disparo chegou na ponte:")
        print("  python3 salesagent/tools/show_recent_audit.py -n 10")
        print("  (esperado: um hook_raw com data[message] vazio, e NENHUM "
              "outbound — ou seja, o lead não recebeu nada)")
        return 0

    print("NENHUMA rota funcionou. Possibilidades, nesta ordem:")
    print("  1. o token do Kommo não tem escopo para disparar bots")
    print("  2. o bot_id está errado (confira em Communication > Bots)")
    print("  3. esta conta não expõe disparo de Salesbot por API")
    print("Se for (3), a entrega espontânea ao lead precisa de outro canal — "
          "me diga e eu desenho a alternativa.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
