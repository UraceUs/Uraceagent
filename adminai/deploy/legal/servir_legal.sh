#!/usr/bin/env bash
# Publica as duas páginas exigidas pela revisão do app da Intuit.
#
# A Intuit precisa de URLs que RESOLVAM de verdade para liberar as chaves
# de produção. Enquanto não houver página no site da URACE, o próprio VPS
# serve — o Caddy já está instalado desde o Chase.
#
# Uso (no VPS):
#   bash adminai/deploy/legal/servir_legal.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DST="/var/www/urace-legal"
DOMINIO="${DOMINIO:-urace-bridge.duckdns.org}"

echo "== publicando páginas legais =="
sudo mkdir -p "$DST"
sudo cp "$REPO/adminai/deploy/legal/privacy.html" "$DST/privacy.html"
sudo cp "$REPO/adminai/deploy/legal/eula.html"    "$DST/eula.html"
sudo chmod 644 "$DST"/*.html
echo "-- copiadas para $DST"

BLOCO="/etc/caddy/conf.d/urace-legal.caddy"
sudo mkdir -p /etc/caddy/conf.d
sudo tee "$BLOCO" >/dev/null <<CADDY
$DOMINIO {
    handle_path /legal/* {
        root * $DST
        file_server
    }
}
CADDY
echo "-- bloco do Caddy escrito em $BLOCO"

if ! grep -q "conf.d" /etc/caddy/Caddyfile 2>/dev/null; then
    echo "!! O Caddyfile principal não importa /etc/caddy/conf.d."
    echo "   Acrescente esta linha no topo de /etc/caddy/Caddyfile:"
    echo "       import /etc/caddy/conf.d/*.caddy"
    exit 1
fi

sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null && echo "-- Caddyfile válido"
sudo systemctl reload caddy
echo "-- Caddy recarregado"

echo
echo "================= PROVA REAL ================="
for p in privacy eula; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/legal/$p.html" || echo 000)"
    echo "   https://$DOMINIO/legal/$p.html  ->  HTTP $code"
done
echo
echo "As duas precisam devolver 200. É essa URL que vai no formulário da Intuit."
