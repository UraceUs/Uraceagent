# URace — AI Sales Agent

Agente comercial da URace: atende leads que chegam pelo Kommo, qualifica,
recomenda o programa certo e agenda — ou passa para uma pessoa quando é o caso.

Persistência: **Firestore** (projeto Firebase `ia-sales-agent-urace`).

---

## O princípio que governa tudo

**As garantias vivem abaixo do modelo, não no prompt.**

Prompt pode derivar, ser reescrito ou ser contornado por uma conversa hábil. Por
isso as três regras que não podem falhar não são pedidos ao modelo — são
estrutura, concentrada em `db/gates.py`:

| Regra | Onde é imposta |
|---|---|
| Preço só depois de qualificar | `gates.shape_offers()` **não devolve o número** — o JSON que o modelo recebe não o contém |
| Criança abaixo da idade da pista | `gates.create_appointment()` — transação Firestore recusa a reserva com aprovação pendente/rejeitada |
| Conversa escalada não volta a vender | roteador determinístico, antes de qualquer chamada ao modelo + `gates.escalate()` atômico |

Um modelo que nunca recebe um número não pode ser convencido a dizê-lo.

**Honestidade da migração:** no Postgres o portão de idade era um trigger — nem
um humano com acesso direto ao banco furava. O Firestore não tem trigger
síncrono que recusa escrita, então o perímetro passou a ser a credencial: **só
o serviço do agente escreve**, e `tests/test_gates.py` inclui um check
estrutural que acusa qualquer módulo que toque `appointments`/`escalations`
fora de `db/gates.py`. A diferença está detalhada em `db/schema.md`.

---

## Estrutura

```
db/            Camada de dados: client, schema spec, PORTÕES, seed (Firestore)
catalog/       Sincronização Google Sheets → Firestore
kb/            Indexador da base de conhecimento (RAG, vector search nativo)
agent/         Orchestrator, camada de tools em Python, API HTTP
prompts/       Master prompt + 5 modos + definições de tools
tests/         Cenários, calibração do judge, mocks, gate tests
docs/          Arquitetura (26 seções) e planilhas do catálogo
```

---

## Como roda

```
Kommo → n8n (webhook) → POST /message (FastAPI) → orchestrator → Claude
                                     ↓
                              Firestore (portões em db/gates.py)
```

O n8n é transporte: recebe do Kommo, chama a API, devolve a resposta. Ele
**nunca** fala com o Firestore — um workflow só de prompt não consegue reter
um preço que o modelo já recebeu. O workflow está em `urace-n8n-workflow.json`
e só precisa de `AGENT_API_URL` e `AGENT_API_KEY`.

---

## Começando

```bash
cp .env.example .env          # aponte para a service account do Firebase
pip install -r requirements.txt
```

**1. Banco** — Firestore não tem DDL; as coleções nascem na primeira escrita.
Aplique o seed (regras de negócio como dado) e crie o índice vetorial:

```bash
python db/seed.py --dry-run   # confira
python db/seed.py             # configurations/* e segments/*

# índice vetorial (uma vez, antes do primeiro indexer):
gcloud firestore indexes composite create \
  --project=ia-sales-agent-urace \
  --collection-group=knowledge_chunks \
  --query-scope=COLLECTION \
  --field-config=vector-config='{"dimension":"1024","flat": "{}"}',field-path=embedding
```

Índices compostos adicionais: o Firestore aponta o link de criação no primeiro
erro de query (lista em `db/schema.md`).

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

**4. Provar os portões** — contra o emulador (sem custo, sem credencial) ou
contra o projeto real:

```bash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8089 python tests/test_gates.py
```

---

## Verificações

Rode antes de qualquer commit. Todas funcionam offline.

```bash
python prompts/compose.py --check      # nenhum dado de negócio nos prompts
python catalog/validate_mapping.py     # planilha ↔ mapeamento ↔ db/schema.py
python kb/indexer.py --self-test       # lógica do indexador
python agent/orchestrator.py --dry-run # roteamento e portão de preço
python tests/test_gates.py             # portões contra Firestore (emulador)
```

**Uma regra aprendida caro:** ao adicionar uma verificação, pergunte o que ela
reporta quando não mediu nada. Se a resposta for "passou", ela é decorativa.

E o corolário: **verificação nunca vista acusando não é verificação.** Vale
para portão, para checador e para teste. O test_gates prova o portão de idade
nos dois sentidos: recusa com aprovação pendente E aceita depois de aprovada.

---

## O catálogo é uma planilha

Programas, ofertas e preços vivem no Google Sheets, não no código. A equipe edita
lá; o sync traz para o Firestore (`programs/{slug}`, ofertas em subcoleção); o
indexador gera os documentos que o agente consulta. Nenhum preço aparece em
prompt ou em código.

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
| Camada de dados | Firestore; portões provados contra o emulador (29 checks) |
| Prompts | 5 modos, sem dado de negócio |
| Catálogo | 13 programas, 113 ofertas, 5 segmentos (sync a aplicar no projeto) |
| Camada de tools | 14 tools sobre Firestore, portões em db/gates.py |
| Orchestrator | dry-run verde |
| Suíte de testes | 17 cenários, judge calibrado em 0.96 |
| **Conversa com lead real** | **ainda não aconteceu** |

Pendências: aplicar seed + sync + índice vetorial no projeto
`ia-sales-agent-urace`, revisar o texto comercial dos 6 programas, IDs de campo
do Kommo, plano Advanced no Kommo (requisito do `widget_request`), e o
Recommendation Engine, que hoje devolve `insufficient_data` sempre.

---

## Kommo — restrições que moldam a integração

- **2 segundos.** O `widget_request` exige HTTP 200 nesse prazo. Um turno leva
  10–60s, então o fluxo é assíncrono: confirma, processa, e devolve pelo
  `return_url`.
- **Chats API não serve.** Cada integração só acessa o próprio canal. Salesbot é
  o único caminho para escrever no chat.
- **Plano Advanced** é necessário para widget customizado e WebSDK.
- Não é possível continuar um bot se outro já está rodando para a mesma entidade.
