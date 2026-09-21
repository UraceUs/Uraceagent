# legacy-v1 — a primeira geração da arquitetura (nunca implantada)

Esta pasta guarda a **geração 1** do projeto: a arquitetura n8n + Supabase/
Postgres desenhada antes da decisão de migrar para OpenClaw + ponte
(decisão do Italo, agosto/2026: "não volte para Supabase/n8n").

**Nada aqui roda em produção.** A produção real vive em `salesagent/`
(ponte + Kommo) e `admagent/` (agente interno). Este código foi preservado
porque contém lógica de valor, parte dela já portada:

| Peça | O que era | Destino |
|---|---|---|
| `kb/indexer.py` + `kb/embed.py` | Pipeline RAG (chunking, embedding incremental por hash, poda de órfãos, provider fake p/ testes) sobre Postgres/pgvector | **Lógica portada** para `brain/indexer.py` (SQLite FTS5) na implantação do Sales Brain |
| `prompts/compose.py` | Composição de prompt em camadas + check "sem dado de negócio em prompt" | Conceito herdado pelas instruções atuais e pela injeção de contexto da ponte |
| `tests/scenarios.yaml` | Metodologia de teste com judge model + taxa de aprovação em N rodadas | Não portada ainda — candidata para evoluir os testes do Chase |
| `db/*.sql` | Schema Postgres com portões como funções SQL | Substituído por `salesagent/bridge/` (portões em Python + SQLite) |
| `agent/` | Orchestrator Python + API | Substituído pela ponte |
| `catalog/` | Sync Google Sheets → banco | Não portado — pendência "sync do rate card" usaria essa base |
| `urace-n8n-workflow.json` | Workflow n8n | Abandonado |

O documento de arquitetura desta geração está em
`docs/urace-ai-agent-arquitetura.md` (mantido como registro histórico).
