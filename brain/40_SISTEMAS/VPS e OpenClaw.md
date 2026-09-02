---
tipo: sistema
tipo_info: FACT
fonte: adminai/deploy + docs/openclaw-setup.md
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# VPS e OpenClaw

[[Sistemas]] · [[Administrative AI]] · [[Etapa de conexão]]

Onde o [[Administrative AI]] realmente mora. O Claude Code é backup e
ambiente de desenvolvimento — **o destino é aqui**.

## O que roda sozinho

| Rotina | Quando | Processo |
|---|---|---|
| Triagem de e-mail | todo dia **07:00** | [[Triagem de e-mail]] |
| Varredura de waiver | todo dia **07:30** | [[Waiver de responsabilidade]] |
| Sincronia status ↔ quadro | seg–sex **06:40** | [[Compra e envio]] |
| Saúde do grafo | segunda **06:00** | [[Como o cérebro cresce]] |

Todas com `Persistent=true`: VPS desligado na hora não perde a execução.

## O agente que executa

As duas rotinas de julgamento (e-mail e waiver) chamam
`openclaw agent --agent "$OPENCLAW_AGENT"`. As outras duas são script
Python puro e não passam por modelo nenhum.

| | |
|---|---|
| Agente | **`urace-admin`** |
| Modelo | **`anthropic/claude-opus-4-8`** |
| Workspace | `~/.openclaw/workspace/urace-admin` |
| Agent dir | `~/.openclaw/agents/urace-admin/agent` — auth própria |
| Routing | **nenhum** — sem `--bind`, não recebe conversa de canal |

O cérebro entra no workspace por **link simbólico**
(`brain -> /home/ubuntu/Uraceagent/brain`), e não apontando o workspace
para o repositório. A razão é concreta: `openclaw agents delete`
**apaga o workspace**. Com o repositório como workspace, um `delete`
levaria o repositório junto; com o link, leva só o link.

⚠️ **O default do OpenClaw ainda é o `urace-sales`**, o agente de vendas
arquivado. Chamada sem `--agent` cai nele. Ver
[[P-13 - Deploy verde sem agente existir]].

### Modelos disponíveis nesta instalação

`anthropic/claude-opus-4-8` (alias `opus`) ·
`anthropic/claude-sonnet-5` (alias `sonnet`) ·
`anthropic/claude-sonnet-4-6` ·
`bedrock/global.anthropic.claude-sonnet-4-6`

**Não há Opus 5 aqui.** O teto é o `opus-4-8`, e é ele que o
`urace-admin` usa — o trabalho dele é julgamento sobre dinheiro e
assinatura, não volume.

### Ler saída do OpenClaw sem virar salada

A CLI desenha spinner e reescreve linhas; saída longa se sobrepõe. A
receita é mandar para arquivo e limpar os códigos de controle:

```bash
{ ...comandos... } > /tmp/oc.txt 2>&1
sed -e 's/\x1b\[[0-9;]*[a-zA-Z]//g' -e 's/\r/\n/g' /tmp/oc.txt
```

Cuidado: `openclaw models list` **quebra** com a saída redirecionada
(`Cannot read properties of undefined`). Use `models status --json`.

⚠️ `agents` no `openclaw.json` **não é um mapa** — é
`agents.list[]`, um array de objetos com `id`. `config set
agents.<nome>.model` não funciona e corrompe a validação.

## Como está montado

- **Segredos** em `~/.urace/adminai.env`, permissão 600, **fora do
  repositório**. Nunca no cérebro, nunca no git.
- **Skills** ligadas por link simbólico de `skills/` para o diretório do
  OpenClaw — `git pull` atualiza a skill sem reinstalar nada.
- **Logs** em `~/.urace/logs/`.
- **`APLICAR=0` é o padrão**: tudo em simulação até o dono ler os
  relatórios e liberar.

## O que o token do [[Asana]] destrava

Além das rotinas: **anexar arquivo na tarefa**, via REST
`POST /attachments`. O conector do Claude não faz isso — é o
[[P-09 - Conector do Asana nao sobe anexo]], e é o que trava o passo do
anexo da waiver assinada.

## Runbook

`adminai/deploy/README.md` — instalação, verificação real (não `rc=0`),
comandos do dia a dia e o que fazer quando der errado.
