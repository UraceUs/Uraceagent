# URace — AI Sales Agent

Agente comercial da URace: atende leads que chegam pelo Kommo, qualifica,
recomenda o programa certo e agenda — ou passa para uma pessoa quando é o caso.

---

## O princípio que governa tudo

**As garantias vivem abaixo do modelo, não no prompt.**

Prompt pode derivar, ser reescrito ou ser contornado por uma conversa hábil. Por
isso as três regras que não podem falhar não são pedidos ao modelo — são
estrutura:

| Regra | Onde é imposta |
|---|---|
| Preço só depois de qualificar | `agent_program()` **não devolve o número** quando não pode ser dito |
| Criança abaixo da idade da pista | trigger no banco recusa a reserva, venha ela de onde vier |
| Conversa escalada não volta a vender | roteador determinístico, antes de qualquer chamada ao modelo |

Um modelo que nunca recebe um número não pode ser convencido a dizê-lo.

---

## Estrutura

```
db/            Schema, seed e a camada de tools como funções Postgres
catalog/       Sincronização Google Sheets → banco
kb/            Indexador da base de conhecimento (RAG)
agent/         Orchestrator, camada de tools em Python, API HTTP
prompts/       Master prompt + 5 modos + definições de tools
tests/         Cenários, calibração do judge, mocks
postman/       Collection que prova os portões contra o banco real
docs/          Arquitetura (26 seções) e planilhas do catálogo
```

---

## Duas formas de rodar

**A — n8n + Supabase** (sem servidor próprio)
O n8n chama as funções SQL por HTTP. Os portões vivem no Postgres. É o caminho
com menos infraestrutura, e o que está montado no workflow atual.

**B — Orchestrator Python** (mais controle)
`agent/orchestrator.py` com roteamento determinístico e a camada de tools em
Python. Precisa de host com endereço público.

As duas compartilham banco, catálogo e prompts. A diferença é onde o loop roda.

---

## Começando

```bash
cp .env.example .env          # preencha DATABASE_URL
pip install -r requirements.txt
```

**1. Banco** — aplique na ordem, no SQL Editor do Supabase ou via `db/apply.py`:

```
001_schema.sql          22 tabelas
002_seed_config.sql     regras de negócio como dado
003_constraints.sql     portão de idade, domínio de canal, índice vetorial
005_handoff_to_human.sql  dois destinos de handoff
006_agent_functions.sql   camada de tools em SQL
```

**2. Catálogo** — o fixture dispensa credencial do Google:

```bash
python catalog/validate_mapping.py
python catalog/sync.py --fixture catalog/fixtures/urace-catalog-fixture.json --dry-run
```

**3. Base de conhecimento**:

```bash
python kb/indexer.py --self-test          # 17 checks, sem chave, sem custo
python kb/indexer.py --provider fake --dry-run
```

**4. Provar os portões** — importe `postman/` no Postman e rode na ordem.
Sem servidor, sem saldo de API: as funções SQL já são a camada de tools.

---

## Verificações

Rode antes de qualquer commit. Todas funcionam offline.

```bash
python prompts/compose.py --check      # nenhum dado de negócio nos prompts
python tests/validate_scenarios.py     # cenários e calibração em lockstep
python db/validate_sql.py              # enums cruzados com tools.json
python catalog/validate_mapping.py     # planilha ↔ mapeamento ↔ DDL
python kb/indexer.py --self-test       # lógica do indexador
python agent/orchestrator.py --dry-run # roteamento e portão de preço
```

**Uma regra aprendida caro:** ao adicionar uma verificação, pergunte o que ela
reporta quando não mediu nada. Se a resposta for "passou", ela é decorativa.
Isso apareceu quatro vezes neste projeto — `0 de 0 = OK`, runs inválidos fora do
denominador, e um guard cujos dois contadores vinham da mesma fonte.

E o corolário: **verificação nunca vista acusando não é verificação.** Vale para
trigger, para checador e para teste. Todo checador aqui foi submetido a teste
negativo antes de ser considerado pronto.

---

## O catálogo é uma planilha

Programas, ofertas e preços vivem no Google Sheets, não no código. A equipe edita
lá; o sync traz para o banco; o indexador gera os documentos que o agente
consulta. Nenhum preço aparece em prompt ou em código.

**Campo vazio significa "não avalie esse critério", nunca "assuma algo
razoável".** Programa sem descrição não é descrito — o agente diz que vai
confirmar. É o que permite operar com o catálogo pela metade sem inventar.

`docs/urace-catalogo-template.xlsx` — estrutura das três abas
`docs/urace-programs-preenchido.xlsx` — conteúdo comercial redigido, para revisão

---

## O que o agente vende, e o que ele não vende

| Ação | Programas |
|---|---|
| `recommend` | 1-Day, Academy, Summer Camp, Lead & Follow, Corporate Events, Arrive & Drive |
| `handoff_to_owner` | Race Team Support, DIY, Mechanic, Engine Rental, Chassis Rental |
| `handoff_to_human` | Kart Rentals, Workshop Services |

Nada fora dos seis primeiros é vendido pelo agente. Piloto que **já compete** é
conversa do Italo; pedido operacional vai para a equipe.

---

## Estado

| Camada | Estado |
|---|---|
| Schema | aplicado no Supabase, 5 portões provados |
| Prompts | 5 modos, sem dado de negócio |
| Catálogo | 13 programas, 113 ofertas, 5 segmentos |
| Camada de tools | 17 asserções contra Postgres |
| Orchestrator | dry-run verde |
| Suíte de testes | 17 cenários, judge calibrado em 0.96 |
| **Conversa com lead real** | **ainda não aconteceu** |

Pendências: revisar o texto comercial dos 6 programas, IDs de campo do Kommo,
plano Advanced no Kommo (requisito do `widget_request`), e o Recommendation
Engine, que hoje devolve `insufficient_data` sempre.

---

## Kommo — restrições que moldam a integração

- **2 segundos.** O `widget_request` exige HTTP 200 nesse prazo. Um turno leva
  10–60s, então o fluxo é assíncrono: confirma, processa, e devolve pelo
  `return_url`.
- **Chats API não serve.** Cada integração só acessa o próprio canal. Salesbot é
  o único caminho para escrever no chat.
- **Plano Advanced** é necessário para widget customizado e WebSDK.
- Não é possível continuar um bot se outro já está rodando para a mesma entidade.
