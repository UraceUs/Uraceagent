#!/usr/bin/env bash
# Publica o Command Center em https://<dominio>/ops/ (login próprio, RBAC
# no servidor, auditoria imutável).
#
# O que faz, nesta ordem, e para se qualquer passo falhar:
#   1. venv em ~/.urace/cc-venv com fastapi/uvicorn (sem tocar no Python do sistema)
#   2. build do frontend (npm ci && npm run build) -> command_center/web/dist
#   3. testes do backend (pytest) contra um banco temporário
#   4. primeiro ADMIN, se ainda não existe nenhum usuário (interativo)
#   5. unit systemd urace-command-center em 127.0.0.1:8790
#   6. handle /ops* no bloco existente do Caddyfile (mesma técnica do /painel)
#   7. prova real: /ops/ responde 200 com o SPA, /ops/api/dashboard sem sessão
#      responde 401, e as páginas legais seguem 200
#
# Uso (no VPS):  bash adminai/deploy/command_center/servir_command_center.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DOMINIO="${DOMINIO:-urace-bridge.duckdns.org}"
CADDYFILE="/etc/caddy/Caddyfile"
PORTA="${CC_PORT:-8790}"
URACE_DIR="${URACE_DIR:-$HOME/.urace}"
VENV="$URACE_DIR/cc-venv"
UNIT=urace-command-center

echo "== Command Center -> https://$DOMINIO/ops/ =="
mkdir -p "$URACE_DIR"; chmod 700 "$URACE_DIR"

# ---------------------------------------------------------------- 1. venv
if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    echo "!! python3-venv ausente. Rode: sudo apt-get install -y python3-venv"; exit 1
fi
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip >/dev/null
"$VENV/bin/pip" install -q -r "$REPO/command_center/requirements.txt"
"$VENV/bin/pip" install -q pytest httpx >/dev/null
echo "-- venv pronto: $("$VENV/bin/python" -c 'import fastapi; print("fastapi", fastapi.__version__)')"

# ------------------------------------------------------------- 2. frontend
if ! command -v npm >/dev/null; then
    echo "!! npm ausente. Instale Node 20+ (ex.: NodeSource) e rode de novo"; exit 1
fi
( cd "$REPO/command_center/web" && npm ci --no-audit --no-fund --silent && npm run build --silent )
[ -f "$REPO/command_center/web/dist/index.html" ] || { echo "!! build do frontend não gerou dist/index.html"; exit 1; }
echo "-- frontend construído: $(du -sh "$REPO/command_center/web/dist" | cut -f1)"

# --------------------------------------------------------------- 3. testes
( cd "$REPO" && CC_DB_PATH=/tmp/cc-test-$$.sqlite "$VENV/bin/python" -m pytest -q command_center/tests 2>&1 | tail -3 )
rm -f /tmp/cc-test-$$.sqlite*

# ------------------------------------------------------ 4. primeiro ADMIN
N_USERS=$(cd "$REPO" && "$VENV/bin/python" - <<'PY'
from command_center.db import conectar, aplicar_schema, um
con = conectar(); aplicar_schema(con)
print(um(con, "SELECT COUNT(*) AS n FROM users")["n"])
PY
)
if [ "$N_USERS" = "0" ]; then
    echo "-- nenhum usuário ainda; criando o primeiro ADMIN (interativo)"
    ( cd "$REPO" && "$VENV/bin/python" -m command_center.manage create-admin )
fi

# --------------------------------------------------------------- 5. systemd
sudo cp "$REPO/adminai/deploy/command_center/$UNIT.service" "/etc/systemd/system/$UNIT.service"
sudo sed -i "s|/home/ubuntu/Uraceagent|$REPO|g; s|/home/ubuntu/.urace|$URACE_DIR|g; s|^User=ubuntu|User=$(id -un)|; s|8790|$PORTA|g" \
        "/etc/systemd/system/$UNIT.service"
sudo systemctl daemon-reload
sudo systemctl enable "$UNIT.service" >/dev/null
sudo systemctl restart "$UNIT.service"
sleep 2
systemctl is-active --quiet "$UNIT.service" \
    || { echo "!! o serviço não subiu:"; journalctl -u "$UNIT" -n 20 --no-pager; exit 1; }
curl -sf "http://127.0.0.1:$PORTA/ops/ready" >/dev/null || { echo "!! /ops/ready não respondeu"; journalctl -u "$UNIT" -n 20 --no-pager; exit 1; }
echo "-- serviço no ar em 127.0.0.1:$PORTA"

# ----------------------------------------------------------------- 6. Caddy
sudo cp "$CADDYFILE" "$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)"
sudo DOMINIO="$DOMINIO" PORTA="$PORTA" python3 - <<'PY'
import os, re
caddyfile = "/etc/caddy/Caddyfile"
dominio, porta = os.environ["DOMINIO"], os.environ["PORTA"]
s = open(caddyfile).read()
# handle (não handle_path): o FastAPI espera o prefixo /ops
bloco = ("\n\thandle /ops* {\n"
         f"\t\treverse_proxy 127.0.0.1:{porta}\n"
         "\t}\n")
if "/ops*" in s:
    s = re.sub(r"\n\thandle /ops\*\s*\{.*?\n\t\}\n", bloco, s, count=1, flags=re.S)
    open(caddyfile, "w").write(s); print("-- bloco /ops atualizado")
elif re.search(re.escape(dominio) + r"\s*\{", s):
    s = re.sub(re.escape(dominio) + r"\s*\{", lambda m: m.group(0) + bloco, s, count=1)
    open(caddyfile, "w").write(s); print("-- handle /ops inserido no bloco existente")
else:
    open(caddyfile, "a").write(f"\n{dominio} {{{bloco}}}\n"); print("-- bloco de site criado")
PY
sudo caddy fmt --overwrite "$CADDYFILE"
sudo caddy validate --config "$CADDYFILE" >/dev/null 2>&1 \
    && echo "-- Caddyfile válido" \
    || { echo "!! Caddyfile INVÁLIDO — restaurando backup"; \
         sudo cp "$(ls -t $CADDYFILE.bak-* | head -1)" "$CADDYFILE"; sudo systemctl reload caddy; exit 1; }
sudo systemctl reload caddy

# ------------------------------------------------------------ 7. prova real
echo; echo "================= PROVA REAL ================="
SPA="$(curl -s -o /tmp/ops.html -w '%{http_code}' "https://$DOMINIO/ops/" || echo 000)"
TEM_APP=$(grep -c 'id="root"' /tmp/ops.html 2>/dev/null || echo 0)
VAZOU=$(grep -ciE 'Renato|Hubbard|Pionti|envelope' /tmp/ops.html 2>/dev/null || echo 0)
API="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/ops/api/dashboard" || echo 000)"
LEGAL="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/legal/privacy.html" || echo 000)"
PAINEL="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMINIO/painel/" || echo 000)"
rm -f /tmp/ops.html
echo "   /ops/ sem sessão           -> HTTP $SPA  (200, SPA com login)"
echo "   SPA montado                -> $TEM_APP  (tem que ser 1)"
echo "   dado de cliente no HTML    -> $VAZOU  (tem que ser 0)"
echo "   /ops/api/dashboard sem sessão -> HTTP $API  (tem que ser 401)"
echo "   /legal/privacy.html        -> HTTP $LEGAL  (continua 200)"
echo "   /painel/                   -> HTTP $PAINEL  (continua 200)"
echo
if [ "$SPA" = "200" ] && [ "$TEM_APP" = "1" ] && [ "$VAZOU" = "0" ] && [ "$API" = "401" ] && [ "$LEGAL" = "200" ] && [ "$PAINEL" = "200" ]; then
    echo "✅ https://$DOMINIO/ops/ no ar. Entre com o ADMIN criado; a API só responde com sessão."
else
    echo "❌ Algo não bate. Para voltar atrás:"
    echo "   sudo cp \$(ls -t $CADDYFILE.bak-* | head -1) $CADDYFILE && sudo systemctl reload caddy"
    exit 1
fi
