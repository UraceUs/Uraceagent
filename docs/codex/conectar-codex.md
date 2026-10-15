# Ligar o Codex nas mesmas conexões do Claude

Dono, 15/10: *"me de o md para conectar o codex com as mesmas conexões q vc tem"*.

Este arquivo é o passo a passo. Vale para o **Codex CLI** (`~/.codex/config.toml`), rodando
na VPS ou na máquina de quem for usar.

> **Antes de tudo, a verdade sobre o que é transportável.** As ferramentas que eu uso vêm de
> dois lugares diferentes, e só um deles passa para o Codex.
>
> | O que eu tenho | Passa para o Codex? | Por quê |
> |---|---|---|
> | Command Center (`urace_*`) | **Sim** | servidor nosso: `adminai/mcp/command_center_mcp.py` e a rota `/ops/mcp` |
> | Asana, DocuSign, Gmail, Kommo, QuickBooks | **Sim** | servidores nossos em `adminai/mcp/*_mcp.py`, credencial em `~/.urace/*.env` |
> | GitHub | **Sim, com token próprio** | o meu acesso é da sessão; não dá para copiar |
> | Google Calendar, Google Drive | **Ainda não** | não existe servidor nosso para eles (ver o item 4) |
> | Claude Docs, n8n | **Não** | são conectores da conta do Claude; o login mora lá dentro |
>
> Conector do claude.ai é **login da conta do Claude**: não existe arquivo de token para
> copiar, e nem deveria existir. O que é nosso, por outro lado, é código deste repositório —
> e aí o Codex usa a mesma ferramenta, com a mesma trava, lendo a mesma credencial.

## 0. O que precisa estar pronto

- Codex CLI instalado e logado (`codex --version`).
- O repositório clonado. Na VPS: `/home/ubuntu/Uraceagent`, branch `claude/commandcenter-vps`.
- `python3` (a VPS tem um venv pronto em `/home/ubuntu/.urace/cc-venv/bin/python`).
- A pasta `~/.urace/` com os `.env` de sempre, permissão `600`. **Ela nunca entra no
  repositório** — o repositório é público.

Confira de onde cada servidor lê a credencial (nenhuma chave aparece no `config.toml`):

| servidor | arquivo | variáveis |
|---|---|---|
| Command Center | `~/.urace/command-center.env` | `CC_API_KEY`, `CC_URL` |
| Asana · DocuSign · QuickBooks | `~/.urace/adminai.env` | `ASANA_TOKEN`, `DS_*`, `QBO_*` |
| Gmail | `~/.urace/google-token.json` (e `-support`) | gravado por `adminai/google_auth.py` |
| Kommo | `~/.urace/kommo.env` | `KOMMO_DOMAIN`, `KOMMO_TOKEN` |

## 1. Command Center

### Na VPS (o jeito melhor: nenhuma chave no arquivo de configuração)

```toml
# ~/.codex/config.toml

[mcp_servers.urace]
command = "/home/ubuntu/.urace/cc-venv/bin/python"
args = ["/home/ubuntu/Uraceagent/adminai/mcp/command_center_mcp.py"]
startup_timeout_sec = 20
tool_timeout_sec = 120
```

Ele lê `CC_API_KEY` do `~/.urace/command-center.env`. Se não existir, crie a chave no painel:
**Usuários → Chaves de API → nova, papel VIEWER, "só leitura" marcado**. Ela aparece **uma
vez**; grave na hora em `~/.urace/command-center.env` (`CC_API_KEY=urk_...`), nunca no chat e
nunca no repositório.

### De outra máquina (pela rota HTTP)

```toml
# ~/.codex/config.toml
experimental_use_rmcp_client = true     # necessário para servidor por `url =`

[mcp_servers.urace]
url = "https://ops.urace.us/ops/mcp"
bearer_token_env_var = "URACE_MCP_KEY"
startup_timeout_sec = 20
tool_timeout_sec = 120
```

A chave fica **no ambiente**, não no arquivo:

```bash
# no ~/.bashrc, ~/.zshrc ou no gerenciador de segredos da máquina
export URACE_MCP_KEY='urk_...'
```

Dá para confiar que a rota está no ar antes de mexer no Codex:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://ops.urace.us/ops/mcp
# 401 é a resposta certa sem chave. Com a chave:
curl -s -H "Authorization: Bearer $URACE_MCP_KEY" https://ops.urace.us/ops/mcp | head -3
# tem de vir {"ok": true, ... "somente_leitura": true}
```

**Se o Codex reclamar do transporte** (a nossa rota responde só `POST` com JSON, sem fluxo
SSE, e versão antiga do Codex não fala `url =`), use a ponte stdio:

```toml
[mcp_servers.urace]
command = "npx"
args = ["-y", "mcp-remote@latest", "--http", "https://ops.urace.us/ops/mcp",
        "--header", "Authorization: Bearer ${URACE_MCP_KEY}"]
```

### O que o Codex ganha com isso

As dezesseis ferramentas de leitura (`urace_resumo`, `urace_atencao`, `urace_cliente`,
`urace_invoices`, `urace_corridas`, `urace_estoque`, as `urace_kommo_*`…) e, **se a
credencial tiver escopo de operar**, `urace_operacoes` + `urace_api` para agir pelas mesmas
rotas dos botões do painel. Com chave `read_only`, o banco abre em `mode=ro` e escrita é
recusada pelo SQLite — a promessa é impedimento, não confiança. Detalhe em
`docs/adminai/conector-mcp.md` e `docs/command-center-mcp-operar.md`.

## 2. Asana, DocuSign, Gmail, Kommo e QuickBooks

São servidores nossos, por stdio. **Rodam na máquina onde está o `~/.urace`** (a VPS).

```toml
[mcp_servers.urace-asana]
command = "python3"
args = ["/home/ubuntu/Uraceagent/adminai/mcp/asana_mcp.py"]
env = { APLICAR = "0" }
startup_timeout_sec = 20

[mcp_servers.urace-gmail]
command = "python3"
args = ["/home/ubuntu/Uraceagent/adminai/mcp/gmail_mcp.py"]
env = { APLICAR = "0" }

[mcp_servers.urace-kommo]
command = "python3"
args = ["/home/ubuntu/Uraceagent/adminai/mcp/kommo_mcp.py"]
env = { APLICAR = "0" }

[mcp_servers.urace-quickbooks]
command = "python3"
args = ["/home/ubuntu/Uraceagent/adminai/mcp/quickbooks_mcp.py"]
env = { APLICAR = "0" }

[mcp_servers.urace-docusign]
command = "python3"
args = ["/home/ubuntu/Uraceagent/adminai/mcp/docusign_mcp.py"]
env = { APLICAR = "0" }
```

**`APLICAR = "0"` é de propósito**: com zero, o que escreve só simula e diz o que faria.
Para valer, `APLICAR = "1"` — e aí vale a regra de sempre: enviar invoice, mandar waiver e
falar com cliente passam por aprovação humana no painel. As ferramentas que o dono nunca
liberou **não existem** no catálogo; não há o que desobedecer.

Cada servidor diz na partida o que carregou (vai para o `stderr`, não atrapalha o
protocolo). Para testar um deles sozinho, antes de ligar no Codex:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"teste","version":"0"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 /home/ubuntu/Uraceagent/adminai/mcp/asana_mcp.py | head -2
```

## 3. GitHub

O meu acesso ao GitHub é um token da sessão, com validade curta: não dá para copiar, e
copiar seria errado. O Codex usa o **servidor oficial do GitHub** com um token do dono:

```toml
[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/"
bearer_token_env_var = "GITHUB_PAT"
```

```bash
export GITHUB_PAT='github_pat_...'   # fine-grained, só no repositório UraceUs/Uraceagent
```

Crie o token em **GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained**, com acesso **só** a `UraceUs/Uraceagent` e o mínimo de permissão que o
trabalho pedir (Contents, Issues, Pull requests). Nunca um token de conta inteira.

## 4. Google Calendar e Google Drive — o que falta

Hoje não existe servidor MCP nosso para Calendar e Drive: só o Gmail tem. O token que a
VPS já guarda (`~/.urace/google-token.json`) **já tem** `calendar.readonly`,
`drive.readonly` e `spreadsheets.readonly`, então o caminho curto é escrever
`adminai/mcp/google_mcp.py` no mesmo molde do `gmail_mcp.py`, reaproveitando
`adminai/google_auth.py`. São poucas ferramentas de leitura (agenda do dia, achar arquivo,
ler planilha). **Me diga se quer que eu faça** — é uma issue pequena, e aí o Codex passa a
ter Calendar e Drive do mesmo jeito que tem o Gmail.

Enquanto isso, a alternativa é o Codex usar um servidor público do Google com o **login
dele** — o que significa outro consentimento, outro token e mais um lugar guardando acesso
à nossa conta. Eu não recomendo.

## 5. As regras também precisam ir

O Codex não lê `CLAUDE.md`: ele lê **`AGENTS.md`**. Sem isso ele tem as ferramentas e não
tem as travas — e várias dessas ferramentas tocam cliente, invoice e dinheiro. O jeito mais
simples é um `AGENTS.md` na raiz apontando para o que já existe:

```markdown
# Regras deste repositório

Valem integralmente as regras de `CLAUDE.md` — leia antes de qualquer alteração.
Resumo do que é "nunca": não destruir dado, não apagar banco, não regenerar credencial
crítica sem autorização; segredo nunca no código nem no repositório; nunca pôr serviço de
um cliente no card de outro; NO FAKE DATA; repositório público, então nenhum dado real de
cliente entra nele. Tudo no fuso da Flórida.
```

Quer que eu crie esse `AGENTS.md`? Falo uma vez e você decide — não vou criar sozinho.

## Conferir

```bash
codex mcp list          # mostra os servidores que ele enxerga
```

Dentro do Codex, peça algo que só o painel sabe (*"qual o resumo da operação hoje?"*). Se
vier número, está ligado.

Problemas comuns:

| sintoma | causa quase sempre |
|---|---|
| `401` no `urace` | chave errada, revogada, ou `URACE_MCP_KEY` não exportada naquele terminal |
| servidor nem sobe | `python3` errado, caminho errado, ou `~/.urace/*.env` ausente — a mensagem no `stderr` diz qual |
| ferramenta de escrita "não faz nada" | `APLICAR=0`, que é o certo até você decidir o contrário |
| `url =` não aceito | Codex antigo: atualize, ou use a ponte `mcp-remote` do item 1 |

## Nunca

- Chave, token ou senha dentro de `config.toml` versionado, ou em qualquer arquivo do
  repositório: **o repositório é público**. Credencial vive em `~/.urace/` (600) ou no
  ambiente.
- Token com mais permissão do que a tarefa pede. Para ler o painel, chave `read_only`.
- Copiar credencial de uma máquina para outra por chat, e-mail ou mensagem.
- `APLICAR=1` sem saber exatamente qual ferramenta vai ser usada.
