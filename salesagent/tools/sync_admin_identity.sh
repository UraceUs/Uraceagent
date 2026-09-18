#!/usr/bin/env bash
# Sincroniza a identidade do Mark (admagent/identity/*.md) com o workspace
# real do agente que o notify_human() da ponte usa para o WhatsApp interno
# (app.py chama `openclaw agent --agent main ...`).
#
# Causa raiz do bug "escalação chega confusa/sem resposta" (25/08): o
# admagent/identity/ foi escrito no repo mas NUNCA copiado para
# ~/.openclaw/workspace/main/ -- o mesmo problema já resolvido pro
# urace-sales em sync_agent_instructions.sh, só que ninguém tinha feito o
# equivalente pro agente do Mark. Sem a identidade, o agente "main" trata
# cada mensagem de escalação como uma conversa nova e pergunta "quem sou eu,
# quem é você" em vez de simplesmente repassar o texto -- então a
# escalação nunca chega de forma acionável a Italo/Eduardo.
#
# Uso (no VPS, depois de git pull, sempre que admagent/identity/*.md mudar):
#   bash salesagent/tools/sync_admin_identity.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="${OPENCLAW_MAIN_WORKSPACE:-$HOME/.openclaw/workspace/main}"

if [ ! -d "$WORKSPACE" ]; then
    echo "Workspace não encontrado em $WORKSPACE" >&2
    echo "Defina OPENCLAW_MAIN_WORKSPACE se o caminho real for outro" \
         "(confira com 'openclaw agent list' ou a config do gateway)." >&2
    exit 1
fi

# A IDENTITY do Mark carrega o placeholder {{HUMAN_REPLY_TOKEN}} -- o token
# de escopo minimo que so abre /human/whatsapp (gerado pelo instalador da
# ponte). E substituido AQUI, na copia para o workspace, para o token nunca
# entrar no repositorio. Sem token no env, o placeholder fica e o Mark nao
# consegue entregar decisoes -- o aviso abaixo existe por isso.
HRT="$(grep -m1 '^HUMAN_REPLY_TOKEN=' "${URACE_DIR:-$HOME/.urace}/bridge.env" 2>/dev/null | cut -d= -f2- || true)"
if [ -n "$HRT" ]; then
    sed "s|{{HUMAN_REPLY_TOKEN}}|$HRT|g" \
        "$REPO_DIR/admagent/identity/IDENTITY.md" > "$WORKSPACE/IDENTITY.md"
else
    cp "$REPO_DIR/admagent/identity/IDENTITY.md" "$WORKSPACE/IDENTITY.md"
    echo "AVISO: HUMAN_REPLY_TOKEN nao encontrado em ~/.urace/bridge.env --"
    echo "       o Mark NAO vai conseguir entregar decisoes de escalacao."
    echo "       Rode: bash salesagent/deploy/install_bridge_service.sh"
fi
cp "$REPO_DIR/admagent/identity/SOUL.md" "$WORKSPACE/SOUL.md"
cp "$REPO_DIR/admagent/identity/USER.md" "$WORKSPACE/USER.md"

echo "Sincronizado: IDENTITY.md, SOUL.md, USER.md -> $WORKSPACE"
echo "Reinicie o gateway para o agente reler os arquivos: openclaw gateway restart"
