#!/usr/bin/env bash
# Expõe o painel web do OpenClaw (127.0.0.1:18789) com HTTPS + senha,
# via Caddy, num subdomínio DuckDNS dedicado.
#
# Pré-requisito: criar o subdomínio no painel do DuckDNS apontando pro
# mesmo IP do VPS (ex.: urace-claw.duckdns.org -> 34.230.114.116).
#
# Uso (no VPS):
#   bash salesagent/deploy/setup_claw_ui.sh urace-claw.duckdns.org 'SUA_SENHA_FORTE'
#
# Depois: abrir https://<dominio> no navegador -> usuário "urace" + a senha.
# O painel do OpenClaw ainda tem a própria autenticação por token por cima.
set -euo pipefail

DOMAIN="${1:?uso: setup_claw_ui.sh <dominio-duckdns> '<senha>'}"
PASS="${2:?uso: setup_claw_ui.sh <dominio-duckdns> '<senha>'}"

HASH="$(caddy hash-password --plaintext "$PASS")"

sudo tee /etc/caddy/claw-ui.caddy > /dev/null <<EOF
# Painel do OpenClaw — gerado por setup_claw_ui.sh (não editar à mão;
# rodar o script de novo para trocar dominio/senha)
$DOMAIN {
	basic_auth {
		urace $HASH
	}
	reverse_proxy 127.0.0.1:18789
}
EOF

# Garante o import no Caddyfile principal (idempotente)
if ! sudo grep -q "import /etc/caddy/claw-ui.caddy" /etc/caddy/Caddyfile; then
    echo "import /etc/caddy/claw-ui.caddy" | sudo tee -a /etc/caddy/Caddyfile > /dev/null
fi

sudo systemctl reload caddy
echo "== OK: painel do OpenClaw em https://$DOMAIN (usuário: urace) =="
echo "   O certificado é emitido na primeira visita (~30s)."
echo "   Se o painel pedir token, rode no VPS: openclaw dashboard"
echo "   (imprime a URL local com o token; use o token no painel)."
