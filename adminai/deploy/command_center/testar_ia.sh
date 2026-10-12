#!/usr/bin/env bash
# #185: testa o motor da IA no VPS. Confere SDK, credencial, sistemas e cérebro, e roda pedidos
# incompletos em MODO ENSAIO (a IA lê os dados de verdade; nada é gravado nem enviado).
# Uso: bash adminai/deploy/command_center/testar_ia.sh          (completo, ~US$ 2-5)
#      bash adminai/deploy/command_center/testar_ia.sh --so-ambiente   (só o ambiente, grátis)
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
URACE_DIR="${URACE_DIR:-$HOME/.urace}"
VENV="$URACE_DIR/cc-venv"
# o mesmo ambiente do serviço (segredos ficam no arquivo; nada aparece na tela)
set -a
[ -f "$URACE_DIR/adminai.env" ] && . "$URACE_DIR/adminai.env"
[ -f "$URACE_DIR/kommo.env" ] && . "$URACE_DIR/kommo.env"
set +a
cd "$REPO" && exec "$VENV/bin/python" -m command_center.ensaio_ia "$@"
