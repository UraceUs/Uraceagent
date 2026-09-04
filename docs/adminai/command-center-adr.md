# URACE Command Center — decisões de arquitetura (ADR)

Data: 04/09/2026. Origem: spec "URACE AI OPERATIONS & COMMAND CENTER",
entregue pelo dono. Este documento registra **o que foi decidido, por
quê, e o que do spec não vale para a URACE**. É lido antes do código.

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

Enquanto o motor de execução (Fase 6) não existe, **toda escrita da IA
é proposta**: `APLICAR=0` no VPS faz o servidor MCP devolver *"teria
feito X"*, e o Command Center mostra isso como ação pendente. Nada
executa por trás do dono.

## 4. Sem dado falso

Integração sem credencial mostra **"Integration not connected"**. Mock
só em desenvolvimento, marcado como tal. O `QuickBooks` entra assim até
a Intuit liberar a produção.

## 5. Fases

A ordem do spec, com o que cada uma reaproveita:

1. **Auth, shell, design system, dashboard, clientes, busca, AI Command** — reaproveita Pit Wall (identidade aprovada), MCP como providers, `urace-admin` como IA.
2. Motor de workflow, Client 360 completo, Asana, tarefas, calendário.
3. Gmail e inteligência de e-mail — o `gmail_mcp` já classifica; falta a camada de prioridade contextual.
4. QuickBooks — **depende da Intuit** (P-11).
5. "Offsight" — **depende de U-08**.
6. Automação, atividade da IA, auditoria, alertas, aprovações executando.
7. Testes, segurança, performance, acessibilidade.

## 6. Onde mora

`command_center/` no repositório: `api/` (FastAPI), `db/`
(`schema.sql`, migrações), `providers/`, `web/` (React). Serviço
`urace-command-center` em `127.0.0.1:8790`, Caddy em `/ops/*`. O Pit
Wall continua existindo como relatório dentro do Command Center.
