# Mapa de agentes — quem é quem na operação URACE

Documento operacional, não técnico — para orientar qualquer sessão nova (Claude
ou humano) que entre no meio do trabalho e precise entender rápido quem faz o
quê. Para a arquitetura de software do agente de vendas em si, ver
`docs/urace-ai-agent-arquitetura.md`.

## Um agente só — desde 23/09/2026

Até 22/09 a operação rodava com 4 sessões Claude Code separadas (U RACE na
nuvem, CRM no Mac, COMERCIAL e AGREGADOR no Windows). Foi aposentado: mensagem
entre sessões exige as duas rodando ao mesmo tempo com Remote Control
conectado (não estava configurado), e a base real (`AGENTES_ATIVOS.md`, da
operação) documenta um incidente concreto de duas sessões disputando o mesmo
login do Dialpad — mensagem sem autoria rastreável chegando num cliente.

**Hoje é uma sessão só — esta, na nuvem (U RACE)** — fazendo os quatro papéis
que antes eram separados: organizar o Kommo, disparar/responder (Dialpad +
Kommo + Gmail), administrativo (Asana/QuickBooks/Docusign), e infraestrutura
do repositório. O loop recorrente que executa isso é
`prompts/LOOP_URACE.md`, seguindo a cadência e a divisão de responsabilidade
(disparo/follow-up/C&S vs. administrativo) definidas originalmente pelo Lucas
em `ARQUITETURA_LOOPS.md` (base da operação, fora deste repositório) — só que
agora nas mãos de uma sessão em vez de duas.

**Se você é uma sessão nova entrando neste repositório**: você é essa sessão
única. Não pergunte "qual das 4 eu sou" — essa pergunta não existe mais. Leia
`prompts/LOOP_URACE.md` e `prompts/PLAYBOOK_COMERCIAL.md` antes de agir.

## O Orchestrator — não é uma sessão

`agent/orchestrator.py`, no repositório. É código, não um chat separado: o
motor que, quando estiver plugado nos canais reais, vai conversar com o lead
sozinho — decide o modo da conversa de forma determinística (`escalation`,
`qualification`, `faq`, `scheduling`, `followup`), monta o prompt, chama o
Claude com tools, executa as tools, salva no Postgres.

Status real (ver `README.md`): **ainda não conversou com lead nenhum de
verdade via essa via** — só roda em `--dry-run`, e depende de um Postgres que
não está provisionado nesta sessão. O loop de hoje (`LOOP_URACE.md`) não usa
o Orchestrator diretamente — espelha as regras dele (`route()`,
`db/002_seed_config.sql`) por referência, sem duplicar a lógica de cabeça.
Ligar o Orchestrator de verdade (Postgres + `agent/api.py` como serviço) é
um passo maior, ainda não feito.

## Ferramentas que este agente único usa

- `agent/kommo_client.py` — ler/escrever Kommo (leads, campos, etapas, notas).
- Dialpad API — SMS real (`+1 407-487-3184`, mesmo número usado antes pela
  operação manual — não duplicar disparo se outra sessão/pessoa também
  estiver usando esse mesmo número ao mesmo tempo).
- Gmail (`urace@urace.us`) — e-mail real.
- Asana, QuickBooks, Docusign — administrativo.
- `data/leads_master.xlsx` — banco central de quem é quem, documentado em
  `CLAUDE.md`.
