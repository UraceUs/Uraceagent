#!/usr/bin/env bash
# Aposenta o Pit Wall: tira a rota /painel do Caddy e desliga o serviço web dele.
#
# Decisão do dono (18/09/2026): "Aposentar: tirar a rota". O Command Center
# cobre o que o Pit Wall mostrava, e quem digitava o endereço antigo batia num
# 404 — agora nem a rota existe.
#
# NÃO apaga nada: o código do Pit Wall continua no repositório e
# `servir_painel.sh` republica quando alguém quiser de volta. O Caddyfile é
# copiado antes de qualquer mudança, validado depois, e restaurado se reprovar.
#
# Uso (no VPS):
#   bash adminai/deploy/painel/aposentar_painel.sh
set -euo pipefail

DOMINIO="${DOMINIO:-urace-bridge.duckdns.org}"
CADDYFILE="/etc/caddy/Caddyfile"

echo "== aposentando o Pit Wall (/painel) em $DOMINIO =="

# ---------------------------------------------------------------- serviço
for unidade in urace-painel-web.service urace-painel.timer urace-painel.service; do
    if systemctl list-unit-files | grep -q "^$unidade"; then
        sudo systemctl disable --now "$unidade" 2>/dev/null || true
        echo "-- $unidade desligado e fora do boot"
    else
        echo "-- $unidade não existe aqui (nada a fazer)"
    fi
done

# ---------------------------------------------------------------- rota
if ! sudo grep -q "/painel\*" "$CADDYFILE" 2>/dev/null; then
    echo "-- o Caddyfile não tem bloco /painel: a rota já não existia"
else
    sudo cp "$CADDYFILE" "$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)"
    echo "-- backup do Caddyfile guardado"
    sudo python3 - <<'PY'
import re
caddyfile = "/etc/caddy/Caddyfile"
s = open(caddyfile).read()
novo, n = re.subn(r"\n\thandle /painel\*\s*\{.*?\n\t\}\n", "\n", s, count=1, flags=re.S)
open(caddyfile, "w").write(novo)
print(f"-- bloco /painel removido ({n} ocorrência)")
PY
    sudo caddy fmt --overwrite "$CADDYFILE"
    sudo caddy validate --config "$CADDYFILE" >/dev/null 2>&1 \
        && echo "-- Caddyfile válido" \
        || { echo "!! Caddyfile INVÁLIDO — restaurando backup"; \
             sudo cp "$(ls -t $CADDYFILE.bak-* | head -1)" "$CADDYFILE"; \
             sudo systemctl reload caddy; exit 1; }
    sudo systemctl reload caddy
    echo "-- Caddy recarregado"
fi

# ---------------------------------------------------------------- prova
COD="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/painel/" || echo 000)"
OPS="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/ops/" || echo 000)"
echo
echo "   /painel/  -> HTTP $COD  (esperado 404: a rota saiu)"
echo "   /ops/     -> HTTP $OPS  (esperado 200: o Command Center segue no ar)"
[ "$OPS" = "200" ] || { echo "!! o /ops/ parou de responder — confira o Caddy"; exit 1; }
echo
echo "== Pit Wall aposentado. Para trazer de volta: bash adminai/deploy/painel/servir_painel.sh"
