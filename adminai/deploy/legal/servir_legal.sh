#!/usr/bin/env bash
# Publica as duas páginas exigidas pela revisão do app da Intuit.
#
# A Intuit precisa de URLs que RESOLVAM de verdade para liberar as chaves
# de produção. Enquanto não houver página no site da urace.us, o próprio
# VPS serve — o Caddy já está instalado desde o Chase.
#
# ⚠️ A primeira versão deste script escrevia um bloco de site novo, e isso
# estava errado: o Caddyfile JÁ declara urace-bridge.duckdns.org para a
# ponte do Chase, e o Caddy recusa o mesmo domínio em dois blocos — teria
# derrubado a configuração inteira. Agora ele insere o handle_path DENTRO
# do bloco existente. (Descoberto no deploy de 01/09.)
#
# Uso (no VPS):
#   bash adminai/deploy/legal/servir_legal.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DST="/var/www/urace-legal"
DOMINIO="${DOMINIO:-urace-bridge.duckdns.org}"
CADDYFILE="/etc/caddy/Caddyfile"

echo "== publicando páginas legais =="
sudo mkdir -p "$DST"
sudo cp "$REPO/adminai/deploy/legal/privacy.html" "$DST/privacy.html"
sudo cp "$REPO/adminai/deploy/legal/eula.html"    "$DST/eula.html"
sudo chmod 644 "$DST"/*.html
echo "-- páginas copiadas para $DST"

sudo cp "$CADDYFILE" "$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)"
echo "-- backup do Caddyfile guardado"

# A âncora é o nome do domínio, não a indentação: o arquivo usa TAB, e
# procurar por espaços não casa. Regex tolerante resolve os dois casos.
sudo DOMINIO="$DOMINIO" DST="$DST" python3 - <<'PY'
import os, re
caddyfile = "/etc/caddy/Caddyfile"
dominio = os.environ["DOMINIO"]
dst = os.environ["DST"]
s = open(caddyfile).read()
bloco = ("\n\thandle_path /legal/* {\n"
         f"\t\troot * {dst}\n"
         "\t\tfile_server\n\t}\n")
if dst in s:
    print("-- já estava configurado, nada a fazer")
elif re.search(re.escape(dominio) + r"\s*\{", s):
    # dentro do bloco que já existe, no começo: handle/handle_path são
    # avaliados na ordem escrita, então o catch-all de 404 segue por último
    s2 = re.sub(re.escape(dominio) + r"\s*\{",
                lambda m: m.group(0) + bloco, s, count=1)
    open(caddyfile, "w").write(s2)
    print("-- handle_path /legal/ inserido no bloco existente")
else:
    open(caddyfile, "a").write(
        f"\n{dominio} {{\n\thandle_path /legal/* {{\n\t\troot * {dst}\n"
        "\t\tfile_server\n\t}\n}\n")
    print("-- bloco de site criado (o domínio ainda não existia)")
PY

sudo caddy fmt --overwrite "$CADDYFILE"
sudo caddy validate --config "$CADDYFILE" >/dev/null 2>&1 \
    && echo "-- Caddyfile válido" \
    || { echo "!! Caddyfile INVÁLIDO — restaurando backup"; \
         sudo cp "$(ls -t $CADDYFILE.bak-* | head -1)" "$CADDYFILE"; exit 1; }
sudo systemctl reload caddy
echo "-- Caddy recarregado"

echo
echo "================= PROVA REAL ================="
FALHOU=0
for pagina in eula privacy; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/legal/$pagina.html" || echo 000)"
    echo "   https://$DOMINIO/legal/$pagina.html  ->  HTTP $code"
    [ "$code" = "200" ] || FALHOU=1
done
echo
if [ "$FALHOU" = "0" ]; then
    echo "✅ As duas respondem 200. É essa URL que vai no formulário da Intuit."
    echo "   Valores prontos em docs/adminai/intuit-app-review.md"
else
    echo "❌ Alguma página não respondeu 200 — a Intuit vai buscar de verdade."
    echo "   Confira: sudo grep -n legal $CADDYFILE"
    exit 1
fi
