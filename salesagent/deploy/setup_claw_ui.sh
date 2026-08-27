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

# Garante que o Caddyfile principal importe este arquivo -- SEM duplicar.
#
# O Caddyfile do repo traz `import /etc/caddy/*.caddy`, que já cobre este
# arquivo. Até 27/08 a checagem procurava só a linha literal, não achava, e
# somava um import explícito: o mesmo site ficava declarado DUAS vezes e o
# Caddy recusava a config inteira ("reload failed"). Aconteceu de verdade ao
# trocar a senha do painel, depois que o Caddyfile com o glob foi instalado.
if sudo grep -qE '^import /etc/caddy/(\*|claw-ui)\.caddy$' /etc/caddy/Caddyfile; then
    echo "-- import ja coberto pelo Caddyfile principal"
else
    echo "import /etc/caddy/claw-ui.caddy" | sudo tee -a /etc/caddy/Caddyfile > /dev/null
    echo "-- import explicito adicionado ao Caddyfile"
fi

# Valida ANTES de recarregar: config inválida derruba o reload e leva junto
# o bridge do Kommo, que vive no mesmo Caddy.
if ! sudo caddy validate --config /etc/caddy/Caddyfile 2>/dev/null; then
    echo "== CONFIG INVALIDA -- nada foi recarregado. Detalhes: ==" >&2
    sudo caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -20 >&2
    exit 1
fi

sudo systemctl reload caddy
echo "== OK: painel do OpenClaw em https://$DOMAIN (usuário: urace) =="
echo "   O certificado é emitido na primeira visita (~30s)."
echo "   Se o painel pedir token, rode no VPS: openclaw dashboard"
echo "   (imprime a URL local com o token; use o token no painel)."
