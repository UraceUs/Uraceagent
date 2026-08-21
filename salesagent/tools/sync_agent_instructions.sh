#!/usr/bin/env bash
# Sincroniza as instruções versionadas no repo com o workspace real do
# agente urace-sales no OpenClaw.
#
# Por que isso existe: o agente urace-sales NÃO lê
# salesagent/instructions/urace-sales-agent.md do repo em tempo de execução.
# Ele lê arquivos próprios dentro de ~/.openclaw/workspace/urace-sales/
# (AGENTS.md, IDENTITY.md, SOUL.md), que são uma CÓPIA feita na configuração
# inicial. `git pull` no repo NUNCA atualiza essa cópia -- é preciso rodar
# este script (ou copiar manualmente) toda vez que
# salesagent/instructions/urace-sales-agent.md ou salesagent/identity/*.md
# mudarem. Descoberto em 21/08 quando um teste mostrou o agente ainda usando
# texto de saudação removido dois commits antes.
#
# Uso (no VPS, depois de git pull):
#   bash salesagent/tools/sync_agent_instructions.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${OPENCLAW_URACE_SALES_WORKSPACE:-$HOME/.openclaw/workspace/urace-sales}"

if [ ! -d "$WORKSPACE" ]; then
    echo "Workspace não encontrado em $WORKSPACE" >&2
    echo "Defina OPENCLAW_URACE_SALES_WORKSPACE se o caminho for outro." >&2
    exit 1
fi

cp "$REPO_DIR/salesagent/instructions/urace-sales-agent.md" "$WORKSPACE/AGENTS.md"
cp "$REPO_DIR/salesagent/identity/IDENTITY.md" "$WORKSPACE/IDENTITY.md"
cp "$REPO_DIR/salesagent/identity/SOUL.md" "$WORKSPACE/SOUL.md"

echo "Sincronizado: AGENTS.md, IDENTITY.md, SOUL.md -> $WORKSPACE"
echo "Reinicie o gateway para o agente reler os arquivos: openclaw gateway restart"
