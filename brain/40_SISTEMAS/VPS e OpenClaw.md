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
| `docusign_mcp.py` | [[DocuSign]] | ativo desde 02/09 · em **produção** desde 04/09 |
| `gmail_mcp.py` | [[Gmail]] · [[Google Calendar]] · Sheets | escrito 04/09 — espera o cliente OAuth e o consentimento por caixa |

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

### O painel (Pit Wall)

`adminai/painel/gerar_painel.py` lê o estado da máquina e escreve
`~/.urace/painel/index.html`. Timer próprio, a cada 15 minutos. A seção
**Em progresso** mostra o último relatório de cada rotina, com selo de
idade — relatório velho vira alerta em vez de passar por atual.

⚠️ **O gerador nunca tinha rodado até 04/09.** `TEMPLATE.format()`
quebrava nas variáveis de CSS (`{--paper:…}`), lidas como campos. A
página aprovada em 01/09 era o desenho, feito à mão. Mesma família do
[[P-13 - Deploy verde sem agente existir]]: aprovado como ideia, nunca
executado como código.

**Publicado em `https://urace-bridge.duckdns.org/painel/`**, atrás de
página de login própria (`adminai/painel/servidor_painel.py`), servida
pelo Caddy por `reverse_proxy` para `127.0.0.1:8787`.

Não é o `basic_auth` do Caddy: aquele abre a caixinha cinza do navegador,
sem como sair e sem explicar nada. Aqui: senha em **scrypt** com sal,
sessão em cookie **assinado com HMAC** (12 h, `HttpOnly`, `Secure`,
`SameSite=Strict`), bloqueio após 5 erros por IP, e botão de sair.

⚠️ `hashlib.scrypt` com `n=2**15, r=8` precisa de `maxmem` explícito — o
padrão do OpenSSL é 32 MB e falha com *"memory limit exceeded"*.

O painel **observa, não trabalha**: lê log, systemd e os relatórios.
Nunca chama API. Das credenciais mostra só a presença, nunca o valor.

Testes do renderizador em `adminai/painel/tests/test_md.py` — cada caso
é um padrão real que quebrou (negrito atravessando quebra de linha,
negrito dentro de célula, `>` de citação, asterisco escapado).

### O Command Center (`/ops/`)

`command_center/` no repositório: FastAPI + SQLite (`~/.urace/command-center.sqlite`,
600) + SPA React construído em `command_center/web/dist`. Serviço
`urace-command-center` em `127.0.0.1:8790`, Caddy `handle /ops*` no
mesmo bloco do domínio, ao lado de `/painel*` e `/legal/*`. Instalação
por `adminai/deploy/command_center/servir_command_center.sh` (venv em
`~/.urace/cc-venv`, `npm ci && npm run build`, pytest, primeiro ADMIN,
unit, Caddy, prova real).

O que ele é: login próprio (scrypt, sessão revogável, cookie `HttpOnly`
+ CSRF), papéis ADMIN/MANAGER/OPERATOR/VIEWER checados **no servidor**,
auditoria em tabela que gatilhos impedem de alterar, espelhos de Asana,
DocuSign e Gmail lidos pelos mesmos módulos MCP, "Precisa de atenção"
com prioridade contextual (VIP fora, RACES fora, delivered ≠ assinada)
e **AI Command** que fala com o `urace-admin` por
`openclaw agent --json`. Toda ação com efeito vira proposta e passa por
política (`action_policies`); invoice só sai depois de aprovada (04/09).

⚠️ Dois erros pegos em teste de navegador antes de subir, em 04/09:
`sqlite3` recusa a conexão em outra thread (o FastAPI abre a dependência
num thread e roda a rota em outro) — `check_same_thread=False`, uma
conexão por requisição; e "Sair" seguido de novo login devolvia a
pessoa à última página, que para um VIEWER era "Sem permissão".

O unit usa `bash -lc` de propósito: sem o PATH de login, o serviço não
acha o `openclaw` e o AI Command falha com "não está no PATH". Se ainda
falhar, `OPENCLAW_BIN=/caminho/openclaw` no `adminai.env`.

### Command Center (no ar desde 04/09/2026)

**`https://urace-bridge.duckdns.org/ops/`** — serviço `urace-command-center`
(uvicorn no venv `~/.urace/cc-venv`, `127.0.0.1:8790`), Caddy com
`handle /ops*` dentro do bloco do domínio. Banco em
`~/.urace/command-center.sqlite`. Primeiro ADMIN: Eduardo Resende
(`eduardoffresende@gmail.com`, id 1). Prova real do deploy: `/ops/` 200
com o SPA, `/ops/api/dashboard` sem sessão 401, zero dado de cliente no
HTML, `/legal/` intacto.

Deploy e atualização: `bash adminai/deploy/command_center/servir_command_center.sh`
(idempotente: venv, build, 27 testes isolados do `~/.urace`, unit,
Caddy com backup, prova). Usuários pela tela **Usuários** ou
`~/.urace/cc-venv/bin/python -m command_center.manage`.

⚠️ O Pit Wall em `/painel/` **não está publicado** no VPS (404 em
04/09): `servir_painel.sh` só chegou lá com o pull do Command Center.
Publicar é opcional — o Command Center cobre o que ele mostrava.

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
