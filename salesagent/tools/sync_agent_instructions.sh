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

# O OpenClaw TRUNCA arquivo de bootstrap acima do limite por arquivo, e faz
# isso em silencio -- so aparece em `openclaw doctor`. Em 27/08 o AGENTS.md
# estava com 25.378 chars e sendo cortado em 19.141: os 25% perdidos eram a
# secao "System protocol" INTEIRA, ou seja, o Chase nunca leu como usar
# NENHUMA diretiva ([[qualify]], [[price]], [[escalate]], [[unknown]],
# [[kb]]...). O manual terminava no meio de uma frase.
#
# O limite vive em agents.defaults.bootstrapMaxChars (ou por agente). Este
# aviso existe para o corte nunca mais ser descoberto por acaso.
CHARS="$(wc -m < "$WORKSPACE/AGENTS.md")"
LIMITE="$(openclaw config get agents.defaults.bootstrapMaxChars 2>/dev/null | tr -dc '0-9')"
LIMITE="${LIMITE:-20000}"   # default do OpenClaw quando nao configurado
if [ "$CHARS" -gt "$LIMITE" ]; then
    echo
    echo "!! AVISO: AGENTS.md tem $CHARS chars e o limite e $LIMITE."
    echo "   O FIM do arquivo sera CORTADO em silencio -- e o fim e onde"
    echo "   vive a secao 'System protocol' (as diretivas)."
    echo "   Corrija antes de testar qualquer coisa:"
    echo "     openclaw config set agents.defaults.bootstrapMaxChars $((CHARS + 15000))"
    echo "     openclaw gateway restart"
else
    echo "AGENTS.md: $CHARS chars (limite $LIMITE) -- cabe inteiro."
fi

echo "Reinicie o gateway para o agente reler os arquivos: openclaw gateway restart"
