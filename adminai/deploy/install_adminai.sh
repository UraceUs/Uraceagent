#!/usr/bin/env bash
# Instala o Administrative AI no VPS. Idempotente: pode rodar de novo
# depois de um git pull para aplicar código novo.
#
# O que ele FAZ:
#   - cria ~/.urace (700) e ~/.urace/logs
#   - cria ~/.urace/adminai.env a partir do exemplo, SE não existir
#   - liga as skills do repo no diretório de skills do OpenClaw
#   - instala os timers do systemd, mas SÓ os que têm credencial
#   - prova, no fim, o que ficou de pé
#
# O que ele NÃO faz:
#   - não sobrescreve o adminai.env preenchido (seus segredos ficam)
#   - não escreve em Asana, Gmail, QuickBooks ou DocuSign
#   - não liga nada com APLICAR=1 sem você mandar
#
# Uso (no VPS):
#   bash adminai/deploy/install_adminai.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_DIR="$REPO_DIR/adminai/deploy"
URACE_DIR="${URACE_DIR:-$HOME/.urace}"
ENV_FILE="$URACE_DIR/adminai.env"
RUN_USER="$(id -un)"
SKILLS_DST="${SKILLS_DST:-$HOME/.openclaw/skills}"

echo "== instalador do Administrative AI =="
echo "repo:     $REPO_DIR"
echo "usuário:  $RUN_USER"
echo "segredos: $URACE_DIR"
echo

# ---------------------------------------------------------------- 1. pastas
mkdir -p "$URACE_DIR/logs"
chmod 700 "$URACE_DIR"
echo "-- $URACE_DIR pronto (700)"

# ------------------------------------------------------------------- 2. env
if [ ! -f "$ENV_FILE" ]; then
    cp "$DEPLOY_DIR/adminai.env.example" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "-- $ENV_FILE criado a partir do exemplo"
    echo "   ⚠️  PREENCHA AS CREDENCIAIS e rode este script de novo:"
    echo "       nano $ENV_FILE"
else
    chmod 600 "$ENV_FILE"
    echo "-- $ENV_FILE já existe (preservado, permissão 600)"
fi

# lê o env sem vazar valor nenhum para o log
set -a; . "$ENV_FILE"; set +a

tem() { [ -n "${!1:-}" ]; }
# o Google não guarda segredo em variável, e sim num arquivo de token
tem_google() { [ -f "${GOOGLE_TOKEN_JSON:-/nao/existe}" ]; }

# devolve 0 quando FALTA o requisito (nome vazio = sem requisito)
falta_para() {
    case "$1" in
        "")                 return 1 ;;
        GOOGLE_TOKEN_JSON)  tem_google && return 1 || return 0 ;;
        *)                  tem "$1"   && return 1 || return 0 ;;
    esac
}

# ---------------------------------------------------------------- 3. skills
mkdir -p "$SKILLS_DST"
for dir in "$REPO_DIR"/skills/*/; do
    nome="$(basename "$dir")"
    [ -f "$dir/SKILL.md" ] || continue
    ln -sfn "$dir" "$SKILLS_DST/$nome"
    echo "-- skill ligada: $nome"
done
echo "   (link simbólico: git pull atualiza a skill sem reinstalar)"

# ------------------------------------------------------- 4. o que dá para ligar
echo
echo "== credenciais encontradas =="
FALTA=()
tem ASANA_TOKEN               && echo "   ✅ Asana"      || { echo "   ❌ Asana";      FALTA+=("ASANA_TOKEN"); }
tem QBO_REFRESH_TOKEN         && echo "   ✅ QuickBooks" || { echo "   ❌ QuickBooks"; FALTA+=("QBO_REFRESH_TOKEN"); }
tem DOCUSIGN_INTEGRATION_KEY  && echo "   ✅ DocuSign"   || { echo "   ❌ DocuSign";   FALTA+=("DOCUSIGN_INTEGRATION_KEY"); }
[ -f "${GOOGLE_TOKEN_JSON:-/nao/existe}" ] && echo "   ✅ Google" || { echo "   ❌ Google"; FALTA+=("GOOGLE_TOKEN_JSON"); }

# O agente que as rotinas chamam existe mesmo? Credencial presente e timer
# ativo não provam nada se o `openclaw agent --agent` cair num nome que não
# existe: a rotina morre na primeira linha, todo dia, com rc=1.
AG="${OPENCLAW_AGENT:-}"
if [ -z "$AG" ]; then
    echo "   ❌ OPENCLAW_AGENT vazio no env"
    FALTA+=("OPENCLAW_AGENT")
elif ! command -v openclaw >/dev/null 2>&1; then
    echo "   ⚠️  openclaw não está no PATH — não deu para conferir o agente"
elif openclaw agents list 2>/dev/null | grep -qE "^- ${AG}( |\$)"; then
    echo "   ✅ agente '$AG' existe no OpenClaw"
else
    echo "   ❌ agente '$AG' NÃO existe — as rotinas falham na primeira linha"
    echo "      crie com:"
    echo "      openclaw agents add $AG --non-interactive --workspace \$HOME/.openclaw/workspace/$AG"
    FALTA+=("OPENCLAW_AGENT")
fi

# ARGS_SYNC: simulação por padrão; só vira escrita com APLICAR=1
if [ "${APLICAR:-0}" = "1" ]; then
    ARGS="--aplicar"
    echo
    echo "   ⚠️  APLICAR=1 — a sincronia do Asana vai ESCREVER de verdade."
else
    ARGS=""
    echo
    echo "   🔒 APLICAR=0 — tudo em simulação. Nada é escrito nos sistemas."
fi
grep -q '^ARGS_SYNC=' "$ENV_FILE" \
    && sed -i "s|^ARGS_SYNC=.*|ARGS_SYNC=$ARGS|" "$ENV_FILE" \
    || echo "ARGS_SYNC=$ARGS" >> "$ENV_FILE"

# ------------------------------------------------------- 4b. servidores MCP (ANTES dos timers: timer atrasado dispara na hora em que é ligado)
# O agente roda num container e só vê ferramentas que o gateway expõe.
# Cada servidor é nosso (adminai/mcp/), roda no host e lê o token de
# $ENV_FILE -- a credencial nunca entra no sandbox. `mcp set` é idempotente.
instalar_mcp() {
    local nome="$1" precisa="$2" script="$3"
    if ! command -v openclaw >/dev/null 2>&1; then
        echo "-- mcp $nome: PULADO (openclaw fora do PATH)"; return
    fi
    if falta_para "$precisa"; then
        echo "-- mcp $nome: PULADO (falta $precisa)"
        openclaw --no-color mcp unset "$nome" >/dev/null 2>&1 || true
        return
    fi
    local json
    json=$(printf '{"command":"python3","args":["%s"],"env":{"URACE_ENV":"%s","OPENCLAW_AGENT":"%s"}}'                   "$REPO_DIR/adminai/mcp/$script" "$ENV_FILE" "${OPENCLAW_AGENT:-urace-admin}")
    if openclaw --no-color mcp set "$nome" "$json" >/dev/null 2>&1; then
        echo "-- mcp $nome: registrado ($script)"
    else
        echo "-- mcp $nome: FALHOU ao registrar — rode: openclaw mcp set $nome '$json'"
    fi
}

echo
echo "== servidores MCP =="
instalar_mcp asana ASANA_TOKEN asana_mcp.py
instalar_mcp docusign DOCUSIGN_INTEGRATION_KEY docusign_mcp.py
instalar_mcp google   GOOGLE_TOKEN_JSON        gmail_mcp.py
openclaw --no-color mcp reload >/dev/null 2>&1 || true

# A política do sandbox só deixa passar ferramenta listada. Sem isto o
# gateway conhece o servidor e o agente não vê nada (P-13, parte 2).
# Lê os nomes reais da sondagem e grava em agents.list[].tools.sandbox.tools.alsoAllow.
if command -v openclaw >/dev/null 2>&1 && openclaw --no-color mcp probe --json > /tmp/urace-probe.json 2>/dev/null; then
    LIBERADAS=$(python3 - "$HOME/.openclaw/openclaw.json" /tmp/urace-probe.json "${OPENCLAW_AGENT:-urace-admin}" <<'PYEOF'
import json, sys
cfg, probe, agente = sys.argv[1:4]
d = json.load(open(cfg))
tools = sorted(json.load(open(probe)).get("tools", []))
for a in d.get("agents", {}).get("list", []):
    if a.get("id") == agente:
        a.setdefault("tools", {}).setdefault("sandbox", {}).setdefault("tools", {})["alsoAllow"] = tools
json.dump(d, open(cfg, "w"), indent=2, ensure_ascii=False)
print(len(tools))
PYEOF
    )
    if openclaw --no-color config validate >/dev/null 2>&1; then
        echo "-- política do sandbox: $LIBERADAS ferramentas MCP liberadas para ${OPENCLAW_AGENT:-urace-admin}"
    else
        echo "-- política do sandbox: config INVÁLIDA depois da liberação — confira: openclaw config validate"
    fi
    rm -f /tmp/urace-probe.json
fi

# ---------------------------------------------------------------- 5. timers
instalar_timer() {
    local nome="$1" precisa="$2"
    if falta_para "$precisa"; then
        echo "-- $nome: PULADO (falta $precisa)"
        # se ficou de uma rodada anterior, desliga: sem credencial ele só
        # acumula falha no log todo dia. Volta a subir quando a credencial vier.
        if systemctl list-unit-files "$nome.timer" --no-legend 2>/dev/null | grep -q .; then
            sudo systemctl disable --now "$nome.timer" >/dev/null 2>&1 || true
            echo "   (timer que estava ligado foi desligado — voltaria a falhar)"
        fi
        PULADOS+=("$nome")
        return
    fi
    sudo cp "$DEPLOY_DIR/$nome.service" "/etc/systemd/system/$nome.service"
    sudo cp "$DEPLOY_DIR/$nome.timer"   "/etc/systemd/system/$nome.timer"
    # ajusta usuário e caminhos se o layout não for o padrão
    sudo sed -i "s|/home/ubuntu/Uraceagent|$REPO_DIR|g; \
                 s|/home/ubuntu/.urace|$URACE_DIR|g; \
                 s|^User=ubuntu|User=$RUN_USER|" \
                 "/etc/systemd/system/$nome.service"
    sudo systemctl enable --now "$nome.timer" >/dev/null
    echo "-- $nome: instalado e ligado"
}

echo
echo "== timers =="
PULADOS=()
instalar_timer urace-asana-sync    ASANA_TOKEN
instalar_timer urace-triagem-email GOOGLE_TOKEN_JSON
instalar_timer urace-waivers       DOCUSIGN_INTEGRATION_KEY
instalar_timer urace-brain-health  ""
sudo systemctl daemon-reload

# ----------------------------------------------------------------- 6. prova
echo
echo "================= PROVA REAL ================="
echo "-- timers ativos (não confiar em rc=0):"
systemctl list-timers 'urace-*' --no-pager --all | sed 's/^/   /' || true

echo
echo "-- o cérebro está íntegro?"
# informativo: cérebro com problema não pode abortar a instalação (set -e + pipefail)
{ python3 "$REPO_DIR/adminai/brain_health.py" || true; } | tail -6 | sed 's/^/   /'

echo
echo "-- skills visíveis para o agente:"
ls -1 "$SKILLS_DST" | sed 's/^/   /'

echo
echo "-- ferramentas MCP que o agente enxerga (sondagem real, com token):"
if command -v openclaw >/dev/null 2>&1; then
    openclaw --no-color mcp probe 2>&1 \
        | sed -e 's/\x1b\[[0-9;]*[a-zA-Z]//g' -e 's/\r/\n/g' \
        | grep -vE '^OpenClaw [0-9]|^\s*$' | head -30 | sed 's/^/   /' || true
else
    echo "   (openclaw fora do PATH — sem sondagem)"
fi

echo
if [ ${#FALTA[@]} -gt 0 ]; then
    echo "⚠️  AINDA FALTA: ${FALTA[*]}"
    echo "   Preencha em $ENV_FILE e rode este script de novo."
    if [ ${#PULADOS[@]} -gt 0 ]; then
        echo "   Timers desligados por falta de credencial: ${PULADOS[*]}"
    else
        echo "   Nenhum timer ficou de fora — as rotinas ligadas não dependem delas."
    fi
else
    echo "✅ Todas as credenciais presentes."
fi
echo
echo "Próximo passo, depois de ler os relatórios de simulação em"
echo "$URACE_DIR/logs/:  troque APLICAR=0 por APLICAR=1 no env e rode"
echo "este script de novo."
