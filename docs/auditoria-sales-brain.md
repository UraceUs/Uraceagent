# Auditoria Sales Brain — FASE 1 (diagnóstico) + FASE 2 (plano)

> Entregável das fases 1 e 2 da missão `missao-sales-brain-obsidian.md`
> (25/08/2026). Nenhum arquivo de implementação foi criado ou alterado —
> este documento é análise e proposta, aguardando aprovação do Italo antes
> da FASE 3.

---

## FASE 1 — Diagnóstico da arquitetura atual

### 1.1 O repositório tem DUAS gerações de arquitetura

**Geração 1 (legado, raiz do repo)** — a era n8n + Supabase/Postgres,
**abandonada por decisão explícita** ("não volte para Supabase/n8n"), mas
cujo código permanece no repo e contém peças de alto valor:

| Diretório | O que é | Estado |
|---|---|---|
| `agent/` | Orchestrator Python + camada de tools + API | Nunca implantado |
| `db/` | Schema Postgres completo (leads, qualificação, `knowledge_documents`, `knowledge_chunks` com pgvector, funções-portão em SQL) | Nunca implantado |
| `kb/` | **Pipeline RAG completo**: geração de docs a partir do catálogo → chunking por parágrafo → embedding incremental por hash de conteúdo → poda de órfãos. Abstração de providers (Voyage real + Fake determinístico p/ testes), asserção de dimensão contra o schema, self-test sem custo | Nunca implantado, mas **lógica testada e reaproveitável** |
| `prompts/` | **Composição em camadas** (master → context → mode), subconjunto de tools por modo, e um check que **proíbe dado de negócio em prompt** (preço/nome/idade hardcoded falham o build) | Conceito vivo até hoje; arquivos específicos ao stack antigo |
| `catalog/` | Sync Google Sheets → banco | Nunca implantado |
| `tests/` (raiz) | Cenários YAML com metodologia sofisticada: asserções determinísticas (tools chamadas) separadas de asserções julgadas (judge model), taxa de aprovação em N=5 rodadas em vez de booleano | Metodologia reaproveitável |
| `docs/urace-ai-agent-arquitetura.md` | Doc de arquitetura da geração 1 (26 seções, v4) | Referência histórica |

**Geração 2 (produção, `salesagent/` + `admagent/`)** — OpenClaw + ponte,
**no ar desde 24-25/08** (circuito fechado com lead real):

| Peça | Implementação |
|---|---|
| Agente Chase | OpenClaw `urace-sales`, sem tools/shell; conversa + protocolo `[[diretivas]]`; sessão isolada por lead (`kommo-{lead_id}`) |
| Agente Mark | OpenClaw `main`, WhatsApp interno (Italo + Eduardo), relay de escalação |
| Ponte | FastAPI (`salesagent/bridge/`): portões (`gates.py`), máquina de estados + auditoria SQLite (`state.py`), execução de diretivas (`directives.py`), texto p/ cliente (`textproc.py`), agendador de follow-up + re-alertas (`scheduler.py`) |
| CRM | Kommo (funil dedicado, Salesbot #9, widget custom v2, gatilho em 13 estágios) |
| Infra | Lightsail; systemd (`sales-bridge`, `openclaw-gateway`, `caddy`); HTTPS via DuckDNS |
| Testes | `salesagent/tests/run_scenarios.py`, 19 cenários contra o agente real, checagens regex + checklist de diretivas |

### 1.2 Mapeamento contra o que a missão pede

| Conceito da missão | Já existe? | Onde / observação |
|---|---|---|
| **Knowledge base** | **Sim, em fragmentos Markdown+JSON versionados** | `salesagent/instructions/urace-sales-agent.md` (comportamento), `salesagent/config/*.json` (rate card, links, pipeline — dados fora do prompt), `salesagent/discovery/*.md` (8 fontes extraídas), `CONSOLIDACAO.md` (decisões C1–C12) |
| **Como o Chase acessa conhecimento hoje** | Prompt estático | O `.md` de instruções vira `AGENTS.md` no workspace do agente via `sync_agent_instructions.sh` — **arquivo inteiro, sem retrieval**. Dados voláteis chegam por diretiva (`[[price]]` → ponte → JSON). Funciona no tamanho atual (~20KB); não escala |
| **Memory (por lead)** | **Sim** | SQLite `conversations` (qualificação, estado, follow-up) + sessão OpenClaw por lead (histórico da conversa). Já separada do knowledge fisicamente |
| **Learning** | Parcial, manual | Log de auditoria captura tudo (inbound/outbound/portões/escalações); aprendizados viram texto em `CONSOLIDACAO.md`/`discovery/` por curadoria manual no chat. **Não há fila, nem níveis de confiança, nem loop** |
| **RAG/embeddings** | **Sim, mas do stack abandonado** | `kb/` (pgvector/Postgres). Lógica excelente, alvo errado |
| **Vector DB** | Não (no stack atual) | SQLite atual não tem vetores |
| **Retrieval** | Não | Inexistente na geração 2 |
| **Obsidian** | Não | Nada específico — mas **todo o conhecimento já é Markdown em git**, que é exatamente o formato nativo de um vault |
| **Prompts** | Sim | Instruções versionadas + princípio "sem dado de negócio no prompt" herdado da geração 1 e mantido |
| **CRM/leads/conversations** | Sim | Kommo + SQLite + sessões OpenClaw |
| **.env.example / secrets** | Parcial | `.env.example` existe mas descreve a geração 1 (Supabase/Voyage). Segredos reais corretamente fora do repo (`~/.urace/`) |
| **Testes** | Sim (2 gerações) | Runner atual (regex) + metodologia judge da geração 1 (não portada) |

### 1.3 Problemas encontrados

1. **`.env.example` e `README.md` descrevem a geração abandonada** — um dev
   novo seguiria instruções de Supabase/n8n que não existem mais.
2. **Conhecimento monolítico**: tudo que o Chase "sabe" viaja num prompt
   único. Adicionar conhecimento = crescer o prompt para todos os turnos.
   Sem retrieval, o custo cresce linearmente e o foco do modelo cai.
3. **Sem loop de aprendizado**: os aprendizados desta implantação (ex.:
   objeções reais, perguntas frequentes dos leads) morrem no log de
   auditoria se ninguém curar manualmente.
4. **Duas gerações misturadas na raiz** confundem qualquer análise (esta
   auditoria incluída) — precisa de demarcação clara, sem apagar nada.
5. **Interface humana do conhecimento é o GitHub cru** — funciona para
   dev, não para operação comercial (Italo/Eduardo revisarem conhecimento,
   aprovarem aprendizados).

### 1.4 O que se reaproveita (não recriar)

- **Do stack atual (intocado)**: ponte inteira, portões, estados, diretivas,
  agendador, testes, deploy — o Brain **acopla** nisso, não substitui.
- **Da geração 1 (portar a lógica, trocar o alvo)**:
  - `kb/indexer.py`: chunking por parágrafo, hash incremental, poda de
    órfãos, self-test → portar de Postgres para SQLite.
  - `kb/embed.py`: abstração de provider (Fake p/ testes) → portar como
    está, se/quando embeddings entrarem.
  - `prompts/compose.py`: o conceito de camadas + o check "sem dado de
    negócio em prompt" → vira o montador de contexto do retrieval.
  - `tests/scenarios.yaml`: metodologia de judge + taxa de aprovação →
    fase futura dos testes do Brain.
- **Conteúdo existente**: instructions, discovery, CONSOLIDACAO e configs
  são o conteúdo inicial do vault — **migram com history, não se reescreve**.

---

## FASE 2 — Proposta de arquitetura e plano

### 2.1 Decisões de arquitetura propostas

**D1 — O vault É o repositório (Git como sync).** Obsidian abre pasta de
Markdown; o repo já é isso. Um diretório novo `brain/` no repo vira o
vault. Italo abre `brain/` no Obsidian no notebook; `git pull/push` (ou
plugin Obsidian Git, com botão de sync) move conhecimento entre humano e
servidor — mesmo trilho que o deploy já usa. **Zero dependência do
aplicativo Obsidian em produção** (exigência §8): o servidor lê arquivos,
não a API do Obsidian.

**D2 — Retrieval mínimo que funciona: FTS5 + frontmatter, embeddings
depois.** SQLite FTS5 (full-text nativo, zero dependência nova) + filtros
por frontmatter (type/status/priority) cobre o corpus atual (dezenas de
docs curtos, domínio estreito). A lógica incremental do `kb/indexer.py`
(hash por chunk, poda de órfãos) é portada para esse índice. A abstração
de provider fica pronta para plugar embeddings (sqlite-vec + Voyage/fake)
**só se** a busca léxica se provar insuficiente — critério objetivo, não
preferência (exigência §7: "a solução mais simples que funcione").

**D3 — Chase consome o Brain por diretiva + injeção de contexto.** Duas
vias, ambas pela ponte (mantendo o Chase sem tools):
- `[[kb query="..." type=...]]` — o Chase pede conhecimento; a ponte busca
  e devolve como `[SYSTEM]` na segunda rodada (mesmo padrão já validado do
  `[[price]]`).
- Injeção automática: a ponte roda o retrieval sobre a mensagem do lead e
  prefixa os top-N trechos relevantes como contexto do turno — na ordem de
  camadas da missão §11 (instruções fixas → memória do lead → conhecimento
  relevante → tarefa).

**D4 — Learning loop com aprovação humana via frontmatter.** Um extrator
periódico lê o log de auditoria e as conversas, propõe candidatos (nova
objeção, pergunta sem resposta, padrão de recusa) e grava em
`brain/09_LEARNINGS/` com `status: candidate`. Italo/Eduardo revisam **no
Obsidian** (dashboard de pendências) e mudam para `status: approved`. Só
`approved/active` entram no índice de retrieval — o agente **nunca**
promove conhecimento sozinho (exigência §9).

**D5 — Estrutura do vault adaptada ao que existe** (não a genérica da
missão — o projeto já tem organização melhor em vários pontos):

```
brain/
├── 00_SYSTEM/        ← ponteiros para instructions/ + regras de retrieval
├── 01_COMPANY/       ← empresa, políticas (a partir de discovery/)
├── 02_SALES/         ← qualificação, objeções, fechamentos (de instructions + fonte 8)
├── 06_PRODUCTS/      ← programas, elegibilidade (espelha config/*.json + prosa)
├── 07_KNOWLEDGE/     ← FAQs, pista, check-in
├── 09_LEARNINGS/     ← saída do learning loop (candidate → approved)
├── _dashboards/      ← índices Markdown (pendentes de revisão, ativos, desatualizados)
└── _meta/            ← schema do frontmatter + como usar (docs §6)
```
Memória de cliente (03_CUSTOMERS/04_LEADS/05_CONVERSATIONS da missão) fica
**fora do vault**: já vive no SQLite/Kommo e a missão §10 manda não
misturar memory com knowledge. O vault guarda conhecimento; dashboards
podem citar agregados, nunca dados por lead (privacidade, §19).

**D6 — Demarcar a geração 1 sem apagar**: mover `agent/ db/ kb/ prompts/
catalog/ tests/ postman/` da raiz para `legacy-v1/` com um README de uma
página explicando o que é e o que foi portado. `.env.example` e `README.md`
reescritos para a arquitetura real.

### 2.2 Etapas de implementação (FASE 3, após aprovação)

| Etapa | Entrega | Risco |
|---|---|---|
| **E1** | `brain/` criado com conteúdo migrado + frontmatter padronizado + `_meta/` documentando o schema | Zero (só arquivos novos) |
| **E2** | `brain/indexer.py`: FTS5 incremental (porta da lógica do `kb/`), com self-test | Zero (não acoplado ainda) |
| **E3** | Retrieval na ponte: endpoint interno + diretiva `[[kb]]` + injeção de contexto no `run_agent()` | Médio — testar com os 19 cenários antes de ativar |
| **E4** | Learning loop v1: extrator audit→candidates + dashboards do vault | Baixo (só escreve `candidate`) |
| **E5** | Housekeeping: `legacy-v1/`, README novo, `.env.example` real, guia do Obsidian p/ Italo | Zero |
| **E6** | Testes (parsing, retrieval, ranking, conflitos, docs inexistentes) + observabilidade (query/hits/score no audit log) | — |

Ordem pensada para o circuito em produção **nunca depender de etapa
inacabada**: E1–E2 não tocam a ponte; E3 entra atrás de flag de config
(`BRAIN_RETRIEVAL=on/off`) com rollback de uma linha, como fizemos no
`SALESBOT_DISPLAY`.

### 2.3 O que NÃO fazer (e por quê)

- **Não** usar Obsidian Local REST API/plugin como dependência do agente —
  quebraria produção em servidor (§8). Obsidian = interface humana; índice
  = interface da IA.
- **Não** começar por embeddings/vector DB — custo e complexidade sem
  evidência de necessidade no corpus atual (§7, §18). A porta fica aberta
  pela abstração de provider.
- **Não** migrar o conteúdo reescrevendo — migrar com `git mv` preservando
  histórico, frontmatter adicionado por cima.
- **Não** deixar o agente escrever no vault — só o extrator grava, e só
  `status: candidate` (§9).

### 2.4 Decisões pendentes do Italo antes da FASE 3

1. **Aprovar o plano acima** (ou ajustar estrutura/prioridades).
2. `brain/` em **inglês ou português**? (conteúdo atual é misto; o agente
   opera em EN/PT/ES — sugestão: conteúdo em inglês, nomes de pasta como
   estão, revisão humana bilíngue.)
3. Obsidian no notebook do Italo: **repo completo ou só `brain/`?**
   (sugestão: abrir o repo inteiro como vault e fixar `brain/` — zero
   setup extra; plugin Obsidian Git opcional para sync com um clique.)
4. Cadência do learning loop: extração **diária** (sugestão) ou semanal?
