# URACE — Command Center

O painel de operação da **URACE** (kart racing, Orlando, FL): **https://ops.urace.us/ops/**

Em um lugar só, o painel junta:
- **o espelho das fontes:** Asana, DocuSign, Gmail, QuickBooks e Kommo;
- **o dia a dia da equipe:** clientes e pilotos, calendário, balcão de peças, estoque, compras, vendas, Suits;
- **a área do cliente e o site novo:** reserva, pagamento e waiver.

A IA propõe e a pessoa aprova. Tudo fica registrado numa auditoria que não se apaga. O fuso de tudo é o da Flórida (America/New_York).

| Endereço | O que é |
|---|---|
| `https://ops.urace.us/ops/` | o painel da equipe (privado, `noindex`) |
| `https://ops.urace.us/ops/portal` | a área do cliente |
| `parts.urace.us` | só o balcão de peças no celular |
| `https://ops.urace.us/ops/mcp` | o MCP: o Claude de cada pessoa opera o painel com o usuário dela |

## Como usar o painel

Os guias ficam dentro do próprio painel, em **Administrativo › Como usar**, para ler ou baixar. Lá também está o **MD para a sua IA**. Os arquivos-fonte são estes:

| Guia | Para quem |
|---|---|
| [Geral](docs/playbooks/playbook-geral.md) | todo mundo e a IA de cada um; tem o mapa de todas as telas |
| [Vendas](docs/playbooks/playbook-vendas.md) | quem vende |
| [Mecânicos e coaches](docs/playbooks/playbook-mecanicos-e-coaches.md) ([PDF](docs/playbooks/playbook-mecanicos-e-coaches.pdf)) | o box: calendário e balcão de peças |
| [Suits · Alpha Line](docs/suits-guia-do-lucas.md) | os pedidos de macacão |
| [Conectar a sua IA (MCP e API)](docs/command-center-mcp-operar.md) | quem opera pelo Claude |

## Estrutura do repositório

| Pasta | O que tem |
|---|---|
| [`command_center/`](command_center) | **o sistema que está no ar** |
| `command_center/api/` | FastAPI: uma rota por área (vendas, balcão, suits, agenda, MCP, OAuth…), autenticação, auditoria e observabilidade |
| `command_center/providers/` | a regra de negócio e as integrações (Asana, QuickBooks, Kommo, DocuSign, Gmail, Stripe…) |
| `command_center/db/` | SQLite: `schema.sql` e as migrações em `MIGRACOES` (`db/__init__.py`) |
| `command_center/web/` | o painel em React + Vite (TypeScript); uma tela por arquivo em `src/pages/` |
| `command_center/vitrine/` | o site novo (páginas públicas, SEO, JSON-LD) |
| `command_center/tests/` | testes unitários, de integração e end-to-end (`tests/e2e`, Playwright) |
| [`adminai/`](adminai) | scripts de operação (sincronizar, backup, Google, estoque) e o **deploy** (`adminai/deploy/command_center/`) |
| [`docs/`](docs) | os guias (`docs/playbooks/`), o MCP, a extensão da VPS (`docs/extensao/`) e o histórico (`docs/historico/`) |
| [`brain/`](brain) | o "cérebro" da operação: decisões (`08_DECISOES`), processos (`10_PROCESSOS`), problemas, diário e as preferências do dono |
| [`salesagent/`](salesagent) | o agente de vendas Chase, hoje SDR do Kommo (em observação); [histórico](docs/historico/README-chase-agente-de-vendas.md) |
| [`skills/`](skills) | skills de apoio (Asana, calendário, DocuSign, faturamento no QuickBooks) |
| `relatorios/`, `tarefas/` | a ponte com a VPS: relatórios que ela escreve e tarefas para ela |
| `dados/` | dados derivados (por exemplo, as peças mais usadas a partir do QuickBooks) |
| `legacy-v1/`, `admagent/` | versões antigas, mantidas só como referência |

## Rodar e testar

```bash
# backend
python -m venv .venv && . .venv/bin/activate
pip install -r command_center/requirements.txt pytest httpx ruff
ruff check .
python -m pytest -q

# frontend
cd command_center/web && npm ci && npm run build && npx oxlint src

# end-to-end (Playwright no Chromium)
CC_E2E=1 python -m pytest -q command_center/tests/e2e
```

O CI (`.github/workflows/ci.yml`) roda tudo isso em cada PR: ruff, pytest, tsc, oxlint, build e end-to-end.

## Como uma mudança chega à VPS

O padrão completo de engenharia está em [`CLAUDE.md`](CLAUDE.md).

1. Uma **issue** com o pedido nas palavras do dono e o que conta como "feito".
2. Um **branch** `claude/issue-<n>-<assunto>`, saindo de `claude/commandcenter-vps` (o branch que roda na VPS).
3. Um **PR** para esse branch, com `Closes #<n>` e o template. O PR inclui teste novo que falha sem a mudança, e o guia do assunto atualizado (Playbook junto).
4. Com o CI verde, o merge, e então o **deploy** na VPS:

```bash
cd ~/Uraceagent && git fetch origin claude/commandcenter-vps && git checkout claude/commandcenter-vps && git pull origin claude/commandcenter-vps && bash adminai/deploy/command_center/servir_command_center.sh
```

O script prepara o ambiente Python, gera o build do painel, roda os testes do backend e reinicia o serviço (`uvicorn` em `127.0.0.1:8790`, atrás do Caddy). As migrações do banco rodam sozinhas quando o serviço sobe.

## Regras que não mudam

- Nada se destrói: dados, bancos e credenciais críticas só mudam com autorização do dono.
- Segredo (token, senha, chave) nunca vai para o código, o repositório ou o chat.
- Serviço, peça ou cobrança de um cliente nunca entra no card de outro.
- Nada de dado inventado.
