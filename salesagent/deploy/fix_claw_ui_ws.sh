#!/usr/bin/env bash
# Conserta o WebSocket do painel do OpenClaw atrás do Caddy.
#
# Sintoma (27/08): a página do painel carrega (basic_auth ok), mas o
# Control UI cai com "disconnected (1006): no reason" ao conectar o
# WebSocket. Duas causas se somam atrás deste proxy:
#   1. navegadores não reenviam a credencial de basic_auth no handshake
#      de WebSocket de forma confiável -> Caddy responde 401 -> o browser
#      só enxerga 1006;
#   2. o gateway roda em mode:local e valida o Origin do handshake
#      (anti DNS-rebinding) -> Origin https://urace-claw... é rejeitado.
#
# O conserto: requisições de UPGRADE (WebSocket) passam SEM basic_auth
# (a autenticação delas é o TOKEN do gateway, que continua obrigatório)
# e com Origin/Host reescritos para o que o gateway local espera. Todo o
# resto (a página em si) continua atrás do basic_auth.
#
# Idempotente e sem pedir senha: reaproveita o hash existente do
# claw-ui.caddy. Valida a config antes de recarregar; se inválida,
# restaura o backup e aborta (o bridge do Kommo vive no mesmo Caddy).
#
# Uso (no VPS):
#   bash salesagent/deploy/fix_claw_ui_ws.sh
set -euo pipefail

ARQ=/etc/caddy/claw-ui.caddy
[ -f "$ARQ" ] || { echo "ERRO: $ARQ não existe (painel nunca exposto?)"; exit 1; }

DOMINIO="$(grep -m1 -oE '^[a-z0-9.-]+\.[a-z]{2,}' "$ARQ" || true)"
HASH="$(grep -m1 -oE '\$2[aby]\$[^ ]+' "$ARQ" || true)"
[ -n "$DOMINIO" ] && [ -n "$HASH" ] || {
    echo "ERRO: não achei domínio/hash em $ARQ — formato inesperado:"; cat "$ARQ"; exit 1; }

if grep -q "@ws" "$ARQ"; then
    echo "-- $ARQ já tem a rota de WebSocket (idempotente): nada a fazer"
else
    sudo cp "$ARQ" "$ARQ.bak"
    sudo tee "$ARQ" > /dev/null <<EOF
# Painel do OpenClaw — com rota de WebSocket (fix_claw_ui_ws.sh, 27/08)
# Página protegida por basic_auth; o handshake de WS passa direto e a
# autenticação dele é o TOKEN do gateway (obrigatório). Origin/Host são
# reescritos porque o gateway em mode:local rejeita origins externos.
$DOMINIO {
	@ws {
		header Connection *Upgrade*
		header Upgrade websocket
	}
	handle @ws {
		reverse_proxy 127.0.0.1:18789 {
			header_up Host "127.0.0.1:18789"
			header_up Origin "http://127.0.0.1:18789"
		}
	}
	handle {
		basic_auth {
			urace $HASH
		}
		reverse_proxy 127.0.0.1:18789
	}
}
EOF
    if sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
        sudo systemctl reload caddy
        echo "-- Caddy recarregado com a rota de WebSocket"
    else
        echo "ERRO: config inválida — restaurando backup, NADA recarregado:"
        sudo caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -5
        sudo mv "$ARQ.bak" "$ARQ"
        exit 1
    fi
fi

# Prova real: handshake de WS pelo caminho público interno.
CODE="$(curl -sk -o /dev/null -w '%{http_code}' -m 8 \
    --resolve "$DOMINIO:443:127.0.0.1" "https://$DOMINIO/" \
    -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
    -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGVzdGtleTEyMzQ1Njc4OQ==')"
echo "-- handshake WS -> HTTP $CODE (101=perfeito; 4xx do GATEWAY=ok, é o token; 401 basic=ainda bloqueado)"
echo
echo "No painel: URL WebSocket = wss://$DOMINIO   Token = o do relatório   Senha = vazio"
