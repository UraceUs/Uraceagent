#!/usr/bin/env python3
"""Testa o canal de escalação (WhatsApp interno) sem esperar 15 minutos.

Por que existe: em 25/08 uma escalação real ficou 3h sem chegar a ninguém,
e o log registrava `rc=0` — "sucesso" — em todas as tentativas. Duas causas
somadas: a identidade do agente que faz o repasse nunca tinha sido
sincronizada, e o re-alerta sem teto acabou fazendo esse agente tratar os
avisos como spam e recusar o repasse.

Depois de mexer em qualquer uma dessas peças (sync_admin_identity.sh,
HUMAN_WHATSAPP, gateway do OpenClaw), este probe diz em 30 segundos se o
canal voltou — em vez de esperar o próximo alarme de um lead real.

ATENÇÃO: manda uma mensagem DE VERDADE para cada número em
HUMAN_WHATSAPP. Ela é marcada como teste, mas chega no celular de alguém.

Uso (no VPS):
    python3 salesagent/tools/probe_notify_human.py
"""
import sys
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent / "bridge"
sys.path.insert(0, str(BRIDGE))

import app  # noqa: E402
import state  # noqa: E402
from config import HUMAN_WHATSAPP_LIST  # noqa: E402

# Id impossível de confundir com lead real, e que serve de marcador para a
# verificação de entrega do notify_human (ele procura "lead <numero>").
LEAD_FALSO = 999999


def main() -> int:
    if not HUMAN_WHATSAPP_LIST:
        print("HUMAN_WHATSAPP vazio em ~/.urace/bridge.env — nada a testar.")
        return 2

    print(f"destinos: {', '.join(HUMAN_WHATSAPP_LIST)}")
    print("enviando mensagem de teste...\n")

    antes = {r['id'] for r in _ultimos_ids()}
    app.notify_human(
        f"🧪 TESTE DO CANAL — lead {LEAD_FALSO} (não é um lead real).\n"
        f"Motivo: verificação do caminho de escalação depois de manutenção.\n"
        f"Se você recebeu isto no WhatsApp, o canal está funcionando. "
        f"Não precisa responder nada.")

    novos = [r for r in reversed(_ultimos_ids()) if r["id"] not in antes]
    ok = False
    for r in novos:
        print(f"  [{r['kind']}] {r['detail'][:400]}")
        if r["kind"] == "notify_human" and " OK " in f" {r['detail']} ":
            ok = True

    print()
    if ok:
        print("CANAL OK — o agente repassou o texto (o marcador do lead "
              "voltou na resposta dele). Confirme no celular que a mensagem "
              "chegou de fato.")
        return 0
    print("CANAL NÃO CONFIRMADO. Na ordem, o que checar:")
    print("  1. bash salesagent/tools/sync_admin_identity.sh && openclaw gateway restart")
    print("     (sem a identidade, o agente não sabe que o trabalho dele é repassar)")
    print("  2. openclaw channels login --channel whatsapp   (sessão do WhatsApp caiu?)")
    print("  3. o que o agente devolveu está acima — se ele está RECUSANDO,")
    print("     é o efeito do alarme repetido; o teto novo corrige daqui pra frente.")
    return 1


def _ultimos_ids() -> list:
    with state.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, kind, detail FROM audit ORDER BY id DESC LIMIT 12")]


if __name__ == "__main__":
    sys.exit(main())
