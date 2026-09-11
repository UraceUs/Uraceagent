#!/usr/bin/env bash
# Remove o basic_auth (a senha do navegador) do painel do OpenClaw.
#
# Decisão do dono (27/08): com o gateway autenticando por TOKEN +
# PAREAMENTO DE DISPOSITIVO, a senha do Caddy virou só atrito -- o
# WebSocket já passava sem ela (fix_claw_ui_ws.sh) e a segurança real é
# do gateway. O que muda: a PÁGINA fica carregável publicamente; conectar
# continua exigindo token e dispositivo aprovado.
#
# Idempotente, com backup, valida a config ANTES do reload (o bridge do
# Kommo vive no mesmo Caddy) e termina com prova real.
# Para voltar a ter senha: bash salesagent/deploy/setup_claw_ui.sh <dominio> '<senha>'
#
# Uso (no VPS):
#   bash salesagent/deploy/remove_claw_ui_password.sh
set -euo pipefail

ARQ=/etc/caddy/claw-ui.caddy
[ -f "$ARQ" ] || { echo "ERRO: $ARQ não existe"; exit 1; }
DOMINIO="$(grep -m1 -oE '^[a-z0-9.-]+\.[a-z]{2,}' "$ARQ" || true)"
[ -n "$DOMINIO" ] || { echo "ERRO: domínio não encontrado em $ARQ"; exit 1; }

if ! grep -q "basic_auth" "$ARQ"; then
    echo "-- basic_auth já não existe em $ARQ (idempotente): nada a fazer"
else
    sudo cp "$ARQ" "$ARQ.bak"
    sudo tee "$ARQ" > /dev/null <<EOF
# Painel do OpenClaw — SEM basic_auth (remove_claw_ui_password.sh, 27/08).
# Autenticação: token do gateway + pareamento de dispositivo (camada do
# próprio OpenClaw). Origin/Host reescritos porque o gateway em mode:local
# rejeita origins externos no WebSocket.
$DOMINIO {
	reverse_proxy 127.0.0.1:18789 {
		header_up Host "127.0.0.1:18789"
		header_up Origin "http://127.0.0.1:18789"
	}
}
EOF
    if sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
        sudo systemctl reload caddy
        echo "-- Caddy recarregado sem basic_auth"
    else
        echo "ERRO: config inválida — restaurando backup, NADA recarregado:"
        sudo caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -5
        sudo mv "$ARQ.bak" "$ARQ"
        exit 1
    fi
fi

CODE="$(curl -sk -o /dev/null -w '%{http_code}' -m 8 \
    --resolve "$DOMINIO:443:127.0.0.1" "https://$DOMINIO/")"
echo "-- página do painel -> HTTP $CODE (200 = sem prompt de senha; 401 = ainda com senha)"
echo "-- e o bridge do Kommo continua de pé?"
curl -sf -m 8 http://127.0.0.1:8800/health >/dev/null && echo "   bridge OK" || echo "   !! bridge sem responder — investigar"
