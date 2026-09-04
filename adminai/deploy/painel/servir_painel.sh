#!/usr/bin/env bash
# Publica o Pit Wall em https://<dominio>/painel/, atrás de uma página de
# login própria (adminai/painel/servidor_painel.py).
#
# O painel mostra nome de cliente e status de waiver. Não mostra credencial
# (só presença) nem valor financeiro — mas é dado de cliente, então nunca
# sobe sem autenticação.
#
# Reaproveita o que o servir_legal.sh ensinou em 01/09:
#   - o Caddyfile JÁ declara o domínio; um segundo bloco derruba tudo, então
#     a inserção é DENTRO do bloco existente
#   - o arquivo usa TAB; âncora por indentação não casa. Regex no domínio
#   - backup antes, restaura se o validate reprovar, e a prova é HTTP
#
# Uso (no VPS):
#   bash adminai/deploy/painel/servir_painel.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DOMINIO="${DOMINIO:-urace-bridge.duckdns.org}"
CADDYFILE="/etc/caddy/Caddyfile"
PORTA="${PAINEL_PORTA:-8787}"

echo "== publicando o painel em https://$DOMINIO/painel/ =="

if [ ! -f "${URACE_DIR:-$HOME/.urace}/painel-auth.json" ]; then
    echo "-- nenhuma senha definida ainda; definindo agora"
    python3 "$REPO/adminai/painel/servidor_painel.py" senha
fi

sudo cp "$REPO/adminai/deploy/urace-painel-web.service" \
        /etc/systemd/system/urace-painel-web.service
sudo sed -i "s|/home/ubuntu/Uraceagent|$REPO|g; s|^User=ubuntu|User=$(id -un)|" \
        /etc/systemd/system/urace-painel-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now urace-painel-web.service >/dev/null
sleep 1
systemctl is-active --quiet urace-painel-web.service \
    || { echo "!! o serviço do painel não subiu:"; \
         journalctl -u urace-painel-web -n 15 --no-pager; exit 1; }
echo "-- serviço do painel no ar em 127.0.0.1:$PORTA"

sudo cp "$CADDYFILE" "$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)"
echo "-- backup do Caddyfile guardado"

sudo DOMINIO="$DOMINIO" PORTA="$PORTA" python3 - <<'PY'
import os, re
caddyfile = "/etc/caddy/Caddyfile"
dominio, porta = os.environ["DOMINIO"], os.environ["PORTA"]
s = open(caddyfile).read()
# handle (não handle_path): o servidor espera o prefixo /painel no caminho
bloco = ("\n\thandle /painel* {\n"
         f"\t\treverse_proxy 127.0.0.1:{porta}\n"
         "\t}\n")
if "/painel*" in s:
    s = re.sub(r"\n\thandle /painel\*\s*\{.*?\n\t\}\n", bloco, s, count=1, flags=re.S)
    open(caddyfile, "w").write(s); print("-- bloco do painel atualizado")
elif re.search(re.escape(dominio) + r"\s*\{", s):
    s = re.sub(re.escape(dominio) + r"\s*\{", lambda m: m.group(0) + bloco, s, count=1)
    open(caddyfile, "w").write(s); print("-- handle /painel inserido no bloco existente")
else:
    open(caddyfile, "a").write(f"\n{dominio} {{{bloco}}}\n")
    print("-- bloco de site criado (o domínio ainda não existia)")
PY

sudo caddy fmt --overwrite "$CADDYFILE"
sudo caddy validate --config "$CADDYFILE" >/dev/null 2>&1 \
    && echo "-- Caddyfile válido" \
    || { echo "!! Caddyfile INVÁLIDO — restaurando backup"; \
         sudo cp "$(ls -t $CADDYFILE.bak-* | head -1)" "$CADDYFILE"; \
         sudo systemctl reload caddy; exit 1; }
sudo systemctl reload caddy
echo "-- Caddy recarregado"

echo
echo "================= PROVA REAL ================="
CODE="$(curl -s -o /tmp/p.html -w '%{http_code}' "https://$DOMINIO/painel/" || echo 000)"
TEM_LOGIN=$(grep -c 'name=senha' /tmp/p.html 2>/dev/null || echo 0)
VAZOU=$(grep -ciE 'Renato|Hubbard|waiver|envelope' /tmp/p.html 2>/dev/null || echo 0)
LEGAL="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/legal/privacy.html" || echo 000)"
echo "   /painel/ sem sessão      -> HTTP $CODE  (200 com formulário de login)"
echo "   formulário de senha      -> $TEM_LOGIN  (tem que ser 1)"
echo "   dado de cliente vazando  -> $VAZOU  (tem que ser 0)"
echo "   /legal/privacy.html      -> HTTP $LEGAL  (tem que continuar 200)"
rm -f /tmp/p.html
echo
if [ "$CODE" = "200" ] && [ "$TEM_LOGIN" = "1" ] && [ "$VAZOU" = "0" ] && [ "$LEGAL" = "200" ]; then
    echo "✅ https://$DOMINIO/painel/ — abre na página de login, e o painel só"
    echo "   aparece depois de entrar. As páginas legais seguem no ar."
else
    echo "❌ Algo não bate. Se 'dado de cliente vazando' for maior que 0, o painel"
    echo "   está ABERTO — restaure agora:"
    echo "   sudo cp \$(ls -t $CADDYFILE.bak-* | head -1) $CADDYFILE && sudo systemctl reload caddy"
    exit 1
fi
