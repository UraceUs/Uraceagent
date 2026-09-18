# URACE Command Center — decisões de arquitetura (ADR)

Data: 04/09/2026. **Revisado em 17/09/2026.** Origem: spec "URACE AI
OPERATIONS & COMMAND CENTER", entregue pelo dono. Este documento registra
**o que foi decidido, por quê, e o que do spec não vale para a URACE**. É
lido antes do código.

> **Estado em 17/09/2026: o painel está no ar e em uso.** As decisões
> abaixo continuam valendo — o que mudou é que deixaram de ser plano. O
> motor de execução existe, o QuickBooks está em produção e a área de
> vendas fecha venda de ponta a ponta. Fotografia completa em
> `brain/04_PROJETOS/Administrative AI - Estado completo em 2026-09-17.md`;
> manual de uso em `docs/manual-do-command-center.md`.

## 1. O que o spec não sabia sobre a URACE

| No spec | Na URACE | Decisão |
|---|---|---|
| Onboarding passo 5: "enviar invoice" | Regra de 28/08: humano envia | **Dono decidiu em 04/09: IA envia DEPOIS de aprovação no painel.** Política `REQUIRES_APPROVAL`, nunca auto-approved. `D-2026-09-04` |
| "Offsight" (8 vezes) | Não existe em lugar nenhum | **UNKNOWN (U-08).** Nada implementado até o dono dizer o que é |
| Turo, Hostaway como integrações futuras | Aluguel de carro e de casa; nada a ver com kart | **Não usar para nada** (dono, 04/09) |
| "John Smith", "$819", HubSpot, Stripe, Twilio | Template genérico | Estrutura aproveitada; nomes e valores ignorados |
| Clientes por e-mail/nome | Identidade é chave externa (`asana_gid`, id QBO, `envelopeId`) — regra do cérebro | `entity_links` obrigatório; nome nunca é identidade |
| "Enviar e-mail: configurável" | Regra: IA **não envia e-mail** (exceções: depósito via QBO, waiver via DocuSign) | `BLOCKED` para e-mail livre; as duas exceções existem como ações próprias |
| "Delete customer: BLOCKED / ADMIN" | Regra: IA **nunca apaga nada** | `BLOCKED` sem exceção — não existe a ação |

## 2. Stack

**Backend: Python 3.11 + FastAPI + SQLite** (arquivo em `~/.urace/`,
fora do repositório). Sem ORM: SQL explícito em `schema.sql` e um
repositório fino. Por quê: o projeto inteiro é Python; os três
servidores MCP (`adminai/mcp/`) **são os providers** — importados como
módulo, com as regras do dono já em código; SQLite basta para 5
usuários e uma operação de dezenas de clientes, e migra para Postgres
sem mudar o modelo.

**Frontend: React + TypeScript + Vite**, servido como estático pelo
backend. Por quê: Cmd+K, drill-down, timeline ao vivo e o chat do AI
Command pedem interface reativa; o VPS tem Node 24 para o build.

**IA: o agente `urace-admin` do OpenClaw**, que já existe, já lê o
cérebro e já tem as 27 ferramentas. O Command Center **não** reimplementa
o agente: chama `openclaw agent --agent urace-admin` com uma chave de
sessão por usuário e dia, grava o comando e a saída, e extrai as ações
propostas. Um segundo cérebro de IA seria duplicar regra.

**Autenticação:** e-mail + senha (`scrypt`, sal por usuário), cookie
assinado **e** tabela `sessions` (revogação de verdade, não só
expiração), CSRF por header em toda mutação, rate limit por IP e por
conta, mensagem única *"Invalid email or password."*.

**RBAC:** `ADMIN · MANAGER · OPERATOR · VIEWER`, checado no backend em
cada rota. O frontend só esconde; o backend recusa.

**Auditoria:** `audit_logs` é **append-only por trigger no banco** —
sem `DELETE`/`UPDATE` possíveis, nem por bug, nem por interface.

## 3. Política de ações da IA

| Classe | Exemplos |
|---|---|
| `SAFE` | buscar cliente, ler tarefa, ler envelope, ler e-mail, criar tarefa no Asana, comentar, rascunho de e-mail |
| `REQUIRES_CONFIRMATION` | mover tarefa, concluir subtarefa, rotular e arquivar `wNews` |
| `REQUIRES_APPROVAL` | **enviar invoice**, enviar invoice do depósito, **enviar waiver** (as 4 travas continuam no servidor), criar invoice acima de um teto configurável |
| `BLOCKED` | apagar qualquer coisa, enviar e-mail livre, mexer em `Matt tasks`, escrever no ADM URACE, editar template do DocuSign, `sendReminder` (U-01 não decidido) |

**Toda escrita da IA nasce como proposta.** O agente no VPS roda com
`APLICAR=0` e devolve *"teria feito X"*; o Command Center mostra isso
como ação pendente. Desde 09/09/2026 o motor de execução existe
(`command_center/api/motor.py`): aprovar no painel executa na hora, com o
`APLICAR` ligado só naquele clique e registro em `audit_logs`. Nada
executa por trás do dono.

## 4. Sem dado falso

Integração sem credencial mostra **"Integration not connected"**. Mock
só em desenvolvimento, marcado como tal. O `QuickBooks` entrou assim até
**09/09/2026**, quando a Intuit liberou a produção (P-11); desde 10/09 as
invoices são reais.

## 5. Fases

A ordem do spec, com o estado de **17/09/2026** ao lado:

1. **Auth, shell, design system, dashboard, clientes, busca, AI Command** — **feito** (04/09). Reaproveitou o Pit Wall (identidade aprovada), MCP como providers, `urace-admin` como IA.
2. Motor de workflow, Client 360 completo, Asana, tarefas, calendário — **feito** (04–09/09).
3. Gmail e inteligência de e-mail — **feito** (04/09): as duas caixas, três colunas, marcador sugerido pela IA e aplicado no botão Mover.
4. QuickBooks — **feito** (produção liberada em 09/09; invoice real desde 10/09).
5. "Offsight" — **não existe**, continua dependendo de U-08.
6. Automação, atividade da IA, auditoria, alertas, aprovações executando — **feito**; `audit_logs` imutável por gatilho.
7. Testes, segurança, performance, acessibilidade — **207 testes** automatizados, e o deploy para se um falhar.

Fora do spec, entraram depois: **Kommo** com o chat do lead dentro do
painel (16–17/09), a **área de vendas** com fechamento em uma tela
(17/09), **voz** para ditar e ouvir (17/09) e o botão **Atualizar agora**
(17/09).

## 6. Onde mora

`command_center/` no repositório: `api/` (FastAPI), `db/`
(`schema.sql`, migrações), `providers/`, `web/` (React). Serviço
`urace-command-center` em `127.0.0.1:8790`, Caddy em `/ops/*`. O Pit
Wall continua existindo como relatório dentro do Command Center.

### Deploy e prova (04/09/2026)

`adminai/deploy/command_center/servir_command_center.sh` faz, nesta
ordem e parando no primeiro erro: venv em `~/.urace/cc-venv`; `npm ci &&
npm run build`; `pytest command_center/tests` (27 naquele dia; 207 em 17/09); primeiro ADMIN se a
tabela de usuários está vazia; unit `urace-command-center` (`bash -lc`
para herdar o PATH onde está o `openclaw`); `handle /ops*` inserido no
bloco existente do Caddyfile com backup e `caddy validate`; prova real
em HTTPS: `/ops/` 200 com o SPA e zero nome de cliente no HTML,
`/ops/api/dashboard` **401** sem sessão, `/painel/` e `/legal/` seguem
200.

Antes do VPS, o frontend foi exercitado num Chromium real contra o
backend com banco de teste: login com senha errada mostra só *"Invalid
email or password."*; VIEWER não vê Usuários/Políticas nem o botão de
sincronizar e recebe *"Sem permissão"* em `/ops/users`; ⌘K acha cliente,
serviço e oferece "perguntar à IA"; o sino mostra CRITICAL/HIGH; tema
escuro persiste; 390 px de largura funciona; AI Command sem `openclaw`
termina em **FAILED** com o motivo, não pendurado.

