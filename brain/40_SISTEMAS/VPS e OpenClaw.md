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

### Como o cérebro chega até o agente

⚠️ **O agente roda dentro de um container Docker** (`sandbox.mode:
"all"`, imagem `openclaw-sandbox:bookworm-slim`). Só o workspace é
montado. Isso derruba as soluções óbvias:

| Tentativa | Por que não funciona |
|---|---|
| Link simbólico para o repositório | o alvo não existe dentro do container — link quebrado |
| Workspace = o repositório | `agents delete` **apaga o workspace**: apagaria o repositório |
| Bind para `/workspace/brain` | `/workspace` é **caminho reservado**; o OpenClaw recusa |
| Bind de `~/Uraceagent/brain` para `/opt/...` | origem **fora do workspace**; recusado sem override perigoso |

O que funciona: **o cérebro é copiado para dentro do workspace antes de
cada execução**, por `ExecStartPre` nas duas units que chamam o agente:

```
rsync -a --delete brain/ "$HOME/.openclaw/workspace/$OPENCLAW_AGENT/brain/"
```

O `--delete` é intencional: a cópia é reescrita a cada run, então o
**repositório continua sendo a única fonte de verdade** e rabisco do
agente não vira fato. Se o agente precisar um dia escrever no cérebro,
isso passa a ser uma decisão consciente, não um efeito colateral.

Recusar o override `dangerouslyAllowExternalBindSources` foi escolha:
ele resolveria com uma linha, mas abriria a config para montar qualquer
caminho do host dentro do sandbox — trava geral aberta por um caso
específico.

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

### Ferramentas: servidores MCP próprios

O agente no container não tem CLI nem credencial. O que ele tem são
**ferramentas MCP**, expostas pelo gateway a partir de servidores que
rodam no host — os nossos, em `adminai/mcp/`:

| Servidor | Sistema | Estado |
|---|---|---|
| `asana_mcp.py` | [[Asana]] | ativo desde 02/09 |
| `docusign_mcp.py` | [[DocuSign]] | a escrever — espera o go-live |

Os oficiais (Asana `mcp.asana.com/v2/mcp`, DocuSign `mcp-d.docusign.com`)
existem, mas **exigem Client ID + Secret pré-registrados**, e o `oauth` do
OpenClaw só aceita `scope`, `redirectUrl` e `clientMetadataUrl` — registro
dinâmico, nada mais. Confirmado no schema, não no palpite.

O esqueleto é `mcp_stdio.py`: JSON-RPC por stdio, zero dependência. Fala
`initialize`, `tools/list`, `tools/call`. Uma chamada que falha devolve
`isError` e o servidor **continua de pé** — nunca `sys.exit` dentro de
ferramenta.

O instalador registra cada servidor com `openclaw mcp set` (idempotente)
só quando a credencial existe, e prova com `openclaw mcp probe` — a
sondagem real, com token.

⚠️ **Sondagem verde não é agente vendo.** A política de ferramentas do
sandbox só deixa passar o que está listado, e o padrão não inclui MCP
nenhum: o gateway conhecia o `asana` e o agente via zero ferramentas.
Descoberto com `openclaw sandbox explain --agent urace-admin`. O
instalador agora lê os nomes da sondagem (`asana__asana_tarefa`, …) e
grava em `agents.list[].tools.sandbox.tools.alsoAllow` — quando o
DocuSign entrar, entra sozinho.

### Sessão: uma por rotina e por dia

A sessão do agente **persiste entre execuções**. Na primeira semana tudo
caía em `agent:urace-admin:main`, e o agente chegou a dizer *"isto se
repetiu quatro vezes hoje"* — carregando a conclusão de ontem em vez de
olhar de novo.

As units agora passam `--session-key agent:urace-admin:waivers-AAAA-MM-DD`:
cada manhã começa limpa; duas execuções no mesmo dia compartilham
contexto. Também `--thinking medium` e `--timeout 900`.

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
