#!/usr/bin/env bash
# Entrega ao sales-bridge uma decisão que Italo ou Eduardo tomaram no
# WhatsApp interno ("aprovar 31764961 pode trazer o kart", "retomar ...",
# "fechar ...").
#
# Por que existe: até 26/08 a escalação chegava no WhatsApp pedindo
# "responda 'aprovar <lead> ...'" e a resposta caía no vazio -- não havia
# nada ligando o WhatsApp de volta à ponte. O Italo respondeu "aprovado"
# numa escalação real e não aconteceu nada.
#
# Este script é o que o agente Mark (OpenClaw) chama quando recebe uma
# dessas mensagens. Ele NÃO decide nada: só entrega o texto cru e o
# telefone de quem falou. Quem valida autoridade, interpreta a intenção e
# aplica os portões é a ponte -- um agente não deve ser o guardião de uma
# regra que precisa ser garantida.
#
# Uso:
#   bash salesagent/tools/whatsapp_decision.sh "+14074878143" "aprovar 31764961 pode trazer"
#
# Imprime a resposta em texto para o agente repassar a quem falou.
set -euo pipefail

NUMERO="${1:?uso: whatsapp_decision.sh <telefone> <texto>}"
TEXTO="${2:?uso: whatsapp_decision.sh <telefone> <texto>}"
URACE_DIR="${URACE_DIR:-$HOME/.urace}"

KEY="$(grep -m1 '^AGENT_API_KEY=' "$URACE_DIR/bridge.env" | cut -d= -f2-)"
if [ -z "$KEY" ]; then
    echo "AGENT_API_KEY não encontrada em $URACE_DIR/bridge.env" >&2
    exit 1
fi

RESP="$(curl -sS -X POST http://127.0.0.1:8800/human/whatsapp \
    -H "X-Api-Key: $KEY" -H 'Content-Type: application/json' \
    --data "$(python3 -c '
import json, sys
print(json.dumps({"from": sys.argv[1], "text": sys.argv[2]}))
' "$NUMERO" "$TEXTO")")"

python3 -c '
import json, sys
try:
    print(json.loads(sys.argv[1]).get("reply", "(sem resposta da ponte)"))
except Exception:
    print(sys.argv[1])
' "$RESP"
