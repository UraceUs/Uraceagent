# URace AI Sales Agent — modelo de dados (Firestore)

> Este documento substitui o DDL Postgres (001/003/005). A especificação
> **executável** — a que o código e os checkers leem — é `db/schema.py`.
> Este arquivo explica as decisões; aquele arquivo as impõe.

## O que mudou com a migração, dito sem eufemismo

No Postgres, o portão de idade era um trigger: **o banco recusava** a reserva,
viesse ela de onde viesse. O Firestore não tem triggers síncronos que recusam
escrita — os triggers do Firestore rodam *depois* que o documento existe.

A consequência arquitetural: **os portões agora vivem em `db/gates.py`, dentro
de transações Firestore, e todo caminho de escrita passa por eles.** O único
processo com credencial de escrita é o serviço do agente (FastAPI + Admin SDK);
o n8n não fala com o banco — fala com o serviço. Isso preserva a propriedade
que importa (o modelo nunca recebe um número que não pode dizer, e nenhum
caminho de reserva ignora a aprovação humana), com uma honestidade a registrar:
um humano com a service account consegue escrever direto, o que no Postgres o
trigger impediria. O perímetro agora é a credencial, não o schema.

## Coleções

| Coleção | Doc ID | Substitui |
|---|---|---|
| `leads/{autoId}` | auto | `leads` + `qualification_data` (mapa `qualification` embutido — 1:1, atômico com o lead) |
| `contacts/{channel__externalId}` | **determinístico** | `contacts` — o ID composto É a constraint `UNIQUE(channel, external_id)`: `create()` falha se já existe |
| `conversations/{autoId}` | auto | `conversations` |
| `conversations/{id}/messages/{autoId}` | auto | `messages` |
| `segments/{slug}` | slug | `segments` |
| `programs/{slug}` | slug | `programs` — slug como ID é a `UNIQUE(slug)` |
| `programs/{slug}/offers/{offer_id}` | offer_id | `program_offers` |
| `programs/{slug}/faq/{autoId}` | auto | `program_faq` |
| `human_approvals/{autoId}` | auto | `human_approvals` |
| `appointments/{autoId}` | auto | `appointments` — **só nasce via `gates.create_appointment`** |
| `escalations/{autoId}` | auto | `escalations` |
| `follow_ups/{leadId__attempt}` | determinístico | `follow_ups` — ID composto é a `UNIQUE(lead_id, attempt_number)` |
| `lead_scores/{autoId}` | auto | `lead_scores` |
| `audit_logs/{autoId}` | auto | `audit_logs` |
| `objections_log/{autoId}` | auto | `objections_log` |
| `catalog_sync_runs/{autoId}` | auto | `catalog_sync_runs` |
| `configurations/{category}` | categoria | `configurations` — um doc por categoria, campos = keys |
| `knowledge_documents/{autoId}` | auto | `knowledge_documents` |
| `knowledge_chunks/{autoId}` | auto | `knowledge_chunks` — campo `embedding` é `Vector` nativo |

## Onde cada garantia do Postgres foi parar

| Garantia Postgres | Equivalente Firestore |
|---|---|
| `agent_program()` não devolve preço (função SQL) | `gates.shape_offers()` — o JSON entregue ao modelo simplesmente não contém o número |
| trigger `block_booking_without_age_clearance` | `gates.create_appointment()` — transação lê a aprovação mais recente e **recusa** antes de escrever |
| `agent_escalate` (takeover + cancela follow-ups) | `gates.escalate()` — transação: lead.human_takeover, escalations, follow_ups pendentes → cancelled |
| CHECK / enums / DOMAIN `channel_type` | `db/schema.py` (`ENUMS`) — validado na escrita por `schema.validate()` e conferido por `catalog/validate_mapping.py` |
| FK (`offers.program_id → programs`) | checagem cross-tab do sync (já existia: `check_references`) + IDs de subcoleção |
| `UNIQUE (channel, external_id)` | doc ID determinístico `{channel}__{external_id}` |
| `VECTOR(1024)` + HNSW | campo `Vector(1024)` + índice vetorial do Firestore (ver abaixo) |
| `CONSTRAINT scheduled_has_time` | validação em `gates.create_appointment` |

## Índices

**Nenhum índice composto é requisito.** As queries dos caminhos críticos usam
apenas igualdades (que o Firestore resolve com índices single-field
automáticos) e ordenam em código — decisão deliberada: o portão de segurança
infantil e a primeira mensagem de produção não podem depender de um índice
que alguém esqueceu de criar. Se alguma query nova precisar de um composto, o
erro do Firestore traz o link de criação.

Vetorial (obrigatório antes do primeiro `find_nearest` — o RAG não funciona
sem ele; requer papel Cloud Datastore Index Admin ou o console):

```bash
gcloud firestore indexes composite create \
  --collection-group=knowledge_chunks \
  --query-scope=COLLECTION \
  --field-config=vector-config='{"dimension":"1024","flat": "{}"}',field-path=embedding
```

A dimensão (1024 = Voyage default) fica registrada em `configurations/kb`
no primeiro index e é conferida a cada run — mesma razão do antigo
`assert_matches_schema`: errar dimensão tem que falhar ANTES de escrever.

## Convenções

- Timestamps: `SERVER_TIMESTAMP` na escrita (`created_at`, `updated_at`).
- Campo vazio continua significando "não avalie" — `None`/ausente, nunca `""`.
- Soft delete: `status: "inactive"`, nunca delete — histórico referencia.
- `leads.human_takeover`: só um humano limpa. O agente nunca escreve `False`.
