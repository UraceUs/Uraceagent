#!/usr/bin/env bash
# Instala (ou atualiza) a sales-bridge como servico systemd no VPS.
# Idempotente: pode rodar quantas vezes quiser, inclusive depois de git pull
# para aplicar codigo novo (ele reinstala deps e reinicia o servico).
#
# Uso (no VPS):
#   bash salesagent/deploy/install_bridge_service.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BRIDGE_DIR="$REPO_DIR/salesagent/bridge"
URACE_DIR="${URACE_DIR:-$HOME/.urace}"
UNIT_SRC="$REPO_DIR/salesagent/deploy/sales-bridge.service"
UNIT_DST="/etc/systemd/system/sales-bridge.service"
RUN_USER="$(id -un)"

echo "== sales-bridge installer =="
echo "repo: $REPO_DIR | usuario: $RUN_USER | segredos: $URACE_DIR"

# 1. venv + dependencias
if [ ! -d "$BRIDGE_DIR/.venv" ]; then
    echo "-- criando venv"
    python3 -m venv "$BRIDGE_DIR/.venv"
fi
"$BRIDGE_DIR/.venv/bin/pip" install -q --upgrade pip
"$BRIDGE_DIR/.venv/bin/pip" install -q -r "$BRIDGE_DIR/requirements.txt"
echo "-- dependencias OK"

# 2. segredos: garante bridge.env com AGENT_API_KEY (gera se nao existir)
mkdir -p "$URACE_DIR"
chmod 700 "$URACE_DIR"
BRIDGE_ENV="$URACE_DIR/bridge.env"
if [ ! -f "$BRIDGE_ENV" ] || ! grep -q '^AGENT_API_KEY=' "$BRIDGE_ENV"; then
    KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    echo "AGENT_API_KEY=$KEY" >> "$BRIDGE_ENV"
    echo "-- AGENT_API_KEY gerada e gravada em $BRIDGE_ENV"
else
    echo "-- AGENT_API_KEY ja existe em $BRIDGE_ENV"
fi
if ! grep -q '^HUMAN_WHATSAPP=' "$BRIDGE_ENV"; then
    echo "HUMAN_WHATSAPP=+14074878143" >> "$BRIDGE_ENV"
    echo "-- HUMAN_WHATSAPP padrao gravado (Italo)"
fi
chmod 600 "$BRIDGE_ENV"

# 3. unit do systemd, ajustando usuario/caminhos para o ambiente real
TMP_UNIT="$(mktemp)"
sed -e "s|/home/ubuntu/Uraceagent|$REPO_DIR|g" \
    -e "s|/home/ubuntu/.urace|$URACE_DIR|g" \
    -e "s|/home/ubuntu/.local|$HOME/.local|g" \
    -e "s|^User=ubuntu|User=$RUN_USER|" \
    "$UNIT_SRC" > "$TMP_UNIT"
sudo cp "$TMP_UNIT" "$UNIT_DST"
rm -f "$TMP_UNIT"
sudo systemctl daemon-reload
sudo systemctl enable sales-bridge >/dev/null 2>&1
sudo systemctl restart sales-bridge
echo "-- servico instalado e (re)iniciado"

# 4. health check
sleep 2
if curl -sf http://127.0.0.1:8800/health >/dev/null; then
    echo "== OK: sales-bridge no ar em 127.0.0.1:8800 =="
    echo "   status:  sudo systemctl status sales-bridge"
    echo "   logs:    sudo journalctl -u sales-bridge -f"
else
    echo "== FALHOU o health check -- veja os logs: =="
    sudo journalctl -u sales-bridge -n 30 --no-pager
    exit 1
fi
