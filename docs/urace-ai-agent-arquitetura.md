# Arquitetura — Agente de IA de Vendas URace × Kommo CRM

> Documento de arquitetura. Nenhum código de implementação de módulo está incluído aqui de propósito — apenas estrutura de dados (DDL), contratos entre módulos e decisões de design. A implementação vem depois, módulo a módulo.

---

## Changelog — v2: Admin Configuration Layer

Esta revisão incorpora uma camada de administração completa: programas, regras de recomendação e todo o conteúdo comercial passam a ser dados administráveis por usuários não técnicos, nunca hardcoded em prompt ou código.

| | |
|---|---|
| **Módulos novos** | Program Catalog Service (4.7) · Recommendation Engine (4.8) · Admin Panel (4.9) |
| **Módulos alterados** | Orchestrator/Prompt System (novas tools, master prompt sem conteúdo de programa) · Base de Conhecimento/RAG (auto-indexada a partir do Catálogo) |
| **Tabelas novas** | `programs`, `program_faq`, `recommendation_rules`, `recommendation_log` |
| **Tabelas alteradas** | `knowledge_documents` (+ `source_type`, `source_ref_id`) · `qualification_data` (`programa_desejado` agora referencia `programs.id`) |
| **Impacto no fluxo** | Novo passo entre "Qualificação" e "CRM Sync": sempre que o agente precisa citar ou recomendar um programa, consulta Catálogo/Recommendation Engine — nunca decide sozinho (seção 3 e 21) |

Detalhamento completo nas seções **19–22** (novas). Pontos alterados ao longo do documento estão marcados com **[v2]**.

---

## Changelog — v3: Decisões fechadas para o MVP

A URace respondeu às decisões em aberto da v2. Com isso, a arquitetura é considerada **fechada para o MVP** — o registro completo (resolvidas + defaults assumidos para o que ainda não foi respondido) está na seção 18. Nenhum módulo novo foi criado nesta revisão; os ajustes abaixo são refinamentos de módulos já existentes, marcados **[Resolvido]** ao longo do documento:

| Decisão | Resumo | Seção |
|---|---|---|
| Canais | Kommo como hub único; WhatsApp, Instagram, FB Messenger, TikTok, E-mail | 10.3 |
| Preços/Catálogo comercial | Google Sheets como fonte de verdade (planilha a compartilhar) | 7.3, 20.3 |
| Horário comercial | Seg–Sex 09–18h, Sáb–Dom 08–12h, `America/New_York` | 13 |
| Fluxo de agendamento | Coleta telefone → confirma disponibilidade → sugere horário (seg–sex, dentro do horário) → cria Task + evento. Fora da janela: nunca confirma sozinho, cria Task de aprovação humana | 3, 4.4 |
| Stack | Claude Agent SDK + MCP, sem preferência de linguagem | 16 |

**A partir desta versão, o documento está congelado como baseline de implementação.** Novas seções de arquitetura só devem ser adicionadas se surgir uma necessidade real durante o desenvolvimento — não proativamente.

---

## Changelog — v4: Catálogo real (Google Sheets) + Recommendation Engine em dois estágios

Revisão motivada por uma necessidade real, não proativa: a leitura do *URACE RATE CARD 2026* mostrou que o portfólio da URace tem uma estrutura que o desenho da v2/v3 não comportava bem.

**O que a planilha revelou:**
- O portfólio tem **7 famílias** (abas): *Mechanic/Chassis/Engine · Services · Academy · Summer Camp · Racing team · Corporate Event · Sales — Chassis and Engine* — que atendem **compradores radicalmente diferentes**. Um lead corporativo e uma mãe perguntando sobre o filho não compartilham quase nenhum campo de qualificação.
- O rate card é todo no nível de **variante** — `(serviço × tipo de evento) → preço` (ex.: *Exclusive Mechanic × Regional/National = $600/day*) — e não no nível de "programa". A tabela `programs` sozinha não representa isso.
- Os preços são **explicitamente indicativos**: *"Rate can vary +/- $50"*, *"o preço do aluguel de motor varia conforme o preparador"*, *"motor reserva = 40% do aluguel"*.
- A planilha é um documento **formatado para humanos** (título, endereço, notas de rodapé, células mescladas, preços como texto), não uma estrutura ingerível de forma estável.

| | |
|---|---|
| **Módulos novos** | Catalog Sync Service (Google Sheets → banco, seção 23) |
| **Módulos alterados** | Recommendation Engine → **dois estágios** (segmento → oferta), seção 21 reescrita · Program Catalog (alimentado pela planilha, não digitado no Admin Panel) · Qualification Engine (perguntas passam a variar por segmento) |
| **Tabelas novas** | `segments`, `program_offers`, `catalog_sync_runs` |
| **Tabelas alteradas** | `programs` (+`segment_id`, rastreio de sync) · `qualification_data` (+`segment_id`, +`segment_fields JSONB`, +`telefone`) · `appointments` (+`pending_human_approval` e campos de solicitação) |

Nova seção: **23** (Ingestão do Catálogo). Pontos alterados marcados com **[v3]** no corpo do documento.

---

## Sumário

1. [Princípios de design](#1-princípios-de-design)
2. [Componentes do sistema](#2-componentes-do-sistema)
3. [Fluxo completo (com caminhos de erro)](#3-fluxo-completo-com-caminhos-de-erro)
4. [Módulos e contratos entre eles](#4-módulos-e-contratos-entre-eles)
5. [Estrutura de memória](#5-estrutura-de-memória)
6. [Prompt System](#6-prompt-system)
7. [Base de conhecimento (RAG)](#7-base-de-conhecimento-rag)
8. [Lead Scoring](#8-lead-scoring)
9. [Modelo de dados](#9-modelo-de-dados)
10. [Integrações](#10-integrações)
11. [Segurança e guardrails](#11-segurança-e-guardrails)
12. [Logs e auditoria](#12-logs-e-auditoria)
13. [Configuração](#13-configuração)
14. [Métricas](#14-métricas)
15. [Riscos e problemas potenciais](#15-riscos-e-problemas-potenciais)
16. [Stack sugerido](#16-stack-sugerido)
17. [Roadmap de implementação](#17-roadmap-de-implementação)
18. [Decisões em aberto](#18-decisões-em-aberto)
19. [Camada de Administração: Catálogo, Conhecimento e Configuração](#19-camada-de-administração-catálogo-conhecimento-e-configuração)
20. [Catálogo de Programas](#20-catálogo-de-programas)
21. [Recommendation Engine](#21-recommendation-engine)
22. [Painel Administrativo (Admin Panel)](#22-painel-administrativo-admin-panel)
23. [Ingestão do Catálogo via Google Sheets](#23-ingestão-do-catálogo-via-google-sheets)

---

## 1. Princípios de design

Cinco decisões estruturais guiam todo o resto do documento:

1. **Extração ≠ Decisão.** O LLM (Claude) nunca decide sozinho "esse lead é Hot". Ele **extrai** dados estruturados da conversa (idade, orçamento, urgência etc.) via *tool use*; um **motor de regras determinístico** calcula o score a partir desses dados. Isso torna o score auditável, reprodutível e configurável sem tocar em prompt.
2. **Grounding obrigatório.** Qualquer afirmação factual (preço, horário, disponibilidade, programa) tem que vir de uma fonte de verdade consultada em tempo real (RAG ou campo estruturado do Kommo) — nunca da memória paramétrica do modelo. Se a busca não retornar nada com confiança suficiente, o agente escala ou informa que vai confirmar.
3. **Kommo como hub de canais, não como CRM passivo.** [Confirmado] Os canais conectados ao Kommo da URace são WhatsApp, Instagram, Facebook Messenger, TikTok e E-mail — todos unificados numa única inbox (via *Chats API* + *Salesbot*). Em vez de integrar o agente diretamente com a Meta Cloud API, o agente conversa com **uma única interface** (a API/webhooks do Kommo) e deixa o Kommo lidar com o transporte específico de cada canal. Isso reduz drasticamente a superfície de integração — ver seção 10.3.
4. **Memória em duas camadas.** Curto prazo (mensagens brutas da conversa ativa) e longo prazo (resumo estruturado e cumulativo por lead). Nunca replay do histórico inteiro — ver seção 5.
5. **Tudo que é regra de negócio é configuração, não código.** Pesos de score, horários de atendimento, intervalos de follow-up, textos de mensagem, palavras-gatilho de escalonamento — tudo em uma tabela/arquivo de configuração versionado, recarregável sem deploy.
6. **[v2] Catálogo > Prompt.** Programas, regras de recomendação e conteúdo comercial nunca vivem no prompt do agente — vivem em tabelas administráveis (Catálogo e Configuração, seção 19) que o agente apenas consulta via tool call. Isso é o que torna o sistema resiliente a uma mudança completa de portfólio sem qualquer alteração de lógica ou prompt.

---

## 2. Componentes do sistema

```
┌───────────────────────────────────────────────────────────────────────────┐
│                              CHANNEL LAYER                                 │
│   WhatsApp · Instagram · FB Messenger · TikTok · E-mail                    │
│         (nativamente unificados dentro do Kommo — ver seção 10.3)          │
└───────────────────────────────────────┬───────────────────────────────────┘
                                         │ webhook (lead/mensagem)
                                         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         GATEWAY / WEBHOOK RECEIVER                        │
│  Valida assinatura, normaliza payload Kommo → InboundEvent interno,        │
│  detecta duplicidade/idempotência, publica na fila                         │
└───────────────────────────────────────┬───────────────────────────────────┘
                                         ▼
                                   [ FILA / QUEUE ]
                                         │
                                         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR (núcleo do agente)                    │
│  Router de estado da conversa · monta contexto · chama Claude com tools   │
└──────┬──────────┬───────────┬───────────────┬────────────┬───────────────┘
       │          │           │               │            │
       ▼          ▼           ▼               ▼            ▼
 ┌──────────┐┌──────────┐┌──────────────┐┌───────────┐┌──────────────┐
 │ Memory   ││Knowledge ││ Qualification││  Scoring  ││  Escalation  │
 │ Service  ││ Base/RAG ││    Engine    ││  Engine   ││   Service    │
 └──────────┘└──────────┘└──────────────┘└───────────┘└──────────────┘
       │                                                     │
       ▼                                                     ▼
┌──────────────────┐                                 ┌──────────────────┐
│   CRM SYNC (Kommo)│◄───────────────────────────────┤  NOTIFICAÇÕES   │
│ campos, tags,      │                                 │  (equipe humana) │
│ pipeline, tasks     │                                 └──────────────────┘
└─────────┬──────────┘
          │
          ▼
┌──────────────────┐        ┌─────────────────────┐
│  SCHEDULER        │───────►│  Google Calendar    │
│ (disponibilidade)  │        └─────────────────────┘
└───────────────────┘

        ┌──────────────────────────┐   ┌───────────────────────┐
        │  FOLLOW-UP WORKER (cron)  │   │  LOGGING / AUDIT       │
        │  dispara re-engajamento   │   │  (todas as decisões)   │
        └──────────────────────────┘   └───────────────────────┘

        ┌──────────────────────────┐   ┌───────────────────────┐
        │  CONFIG SERVICE           │   │  METRICS / ANALYTICS   │
        └──────────────────────────┘   └───────────────────────┘
```

**[v2] Camada de Administração** — como Admin Panel, Catálogo, Conhecimento e Configuração se relacionam (detalhe completo na seção 19):

```
┌────────────────────────────────────────────────────────────────────────┐
│                    ADMIN PANEL (uso não técnico)                        │
│  Programas · Regras de recomendação · FAQ · Horários · Templates ·      │
│  Lead Scoring · Follow-ups · Escalonamento · Pipeline Mapping ·         │
│  Campos do Kommo                                                        │
└───────┬─────────────────────────┬──────────────────────┬────────────────┘
        │ escreve                 │ escreve               │ escreve
        ▼                         ▼                       ▼
┌────────────────────┐   ┌──────────────────┐   ┌────────────────────┐
│ PROGRAM CATALOG      │──►│ KNOWLEDGE BASE    │   │ CONFIG SERVICE       │
│ (fonte de verdade)   │auto│ (RAG) — auto-     │   │ pesos · horários ·   │
│ programs, program_faq│index│ indexada + docs   │   │ templates · regras   │
└──────────┬──────────┘   │ manuais           │   │ de recomendação      │
           │               └──────────────────┘   └────────────────────┘
           ▼
┌──────────────────────┐
│ RECOMMENDATION ENGINE  │  lê programs + recommendation_rules;
│ (regras determinísticas)│  nunca decide fora do que está configurado
└──────────┬────────────┘
           │ tool call
           ▼
     ORCHESTRATOR (agente conversacional — nunca escreve nessas tabelas)
```

| Componente | Responsabilidade |
|---|---|
| **Gateway/Webhook Receiver** | Recebe eventos do Kommo (lead novo, mensagem recebida, campo alterado), valida, normaliza e enfileira. Garante idempotência. |
| **Fila (queue)** | Desacopla recepção de processamento; absorve picos; permite retry. |
| **Orchestrator** | Cérebro do fluxo. Decide o "modo" da conversa, monta o prompt, chama o Claude com as tools certas, interpreta a resposta e dispara ações. |
| **Memory Service** | Lê/grava mensagens, gera e mantém o resumo cumulativo por lead. |
| **Knowledge Base / RAG** | Indexa e recupera trechos de conteúdo comercial para responder perguntas abertas. **[v2]** Alimentada automaticamente pelo Program Catalog (descrição/FAQ de cada programa) + documentos genéricos mantidos manualmente (localização, políticas, promoções) — seção 19.2. |
| **Program Catalog Service** *(novo — v2)* | Fonte única de verdade sobre os programas da URace (estrutura, elegibilidade, prioridade). Único lugar onde um programa é criado/editado/desativado — seção 20. |
| **Recommendation Engine** *(novo — v2)* | Avalia o perfil do lead contra regras de recomendação configuráveis e retorna programa recomendado + alternativas + justificativa. O agente nunca recomenda por conta própria — seção 21. |
| **Qualification Engine** | Extrai dados estruturados de qualificação da conversa via tool calling. |
| **Scoring Engine** | Regra determinística que transforma dados estruturados em score + classificação + motivo. |
| **CRM Sync (Kommo)** | Único ponto de escrita no Kommo: campos customizados, tags, etapa do pipeline, tasks. |
| **Scheduler** | Consulta disponibilidade (equipe + Google Calendar) e cria evento + task. |
| **Follow-up Worker** | Job agendado que verifica leads sem resposta e dispara reengajamento conforme regras configuráveis. |
| **Escalation Service** | Detecta gatilhos de transferência humana e notifica a equipe. |
| **Logging/Audit** | Registra toda decisão e ação tomada, com o motivo. |
| **Config Service** | Fonte única de verdade para regras de negócio (não código). |
| **Metrics/Analytics** | Agrega eventos para os indicadores da seção 14. |
| **Admin Panel** *(novo — v2)* | Interface para usuários não técnicos administrarem Programas, Regras de Recomendação, FAQ, Horários, Templates, Lead Scoring, Follow-ups, Escalonamento, Pipeline Mapping e Campos do Kommo — sem tocar em código. Toda escrita é validada e registrada em `audit_logs` — seção 22. |

---

## 3. Fluxo completo (com caminhos de erro)

Expandindo o fluxo original, incluindo os desvios que uma arquitetura de produção precisa tratar:

```
Evento chega do Kommo (webhook)
        │
        ▼
Gateway valida e normaliza ──► payload inválido/duplicado? ──► descarta + loga
        │
        ▼
Orchestrator carrega contexto do lead:
  • Perfil (Memory Service)
  • Resumo cumulativo + qualification_data já conhecida
  • Últimas N mensagens brutas
  • Flag human_takeover? ──► SIM ──► IA não responde, só loga e sai
        │ NÃO
        ▼
Debounce (aguarda ~8-10s por novas mensagens do mesmo lead,
  para não responder frase por frase caso o lead digite em partes)
        │
        ▼
Orchestrator decide o "modo" da conversa (router):
  Saudação / FAQ / Qualificação / Agendamento / Follow-up / Encerrado
        │
        ▼
Monta prompt (master + modo + contexto + resultado de RAG se aplicável)
        │
        ▼
Chama Claude com tools habilitadas para o modo atual
        │
        ├─► Claude pede busca na KB ──► RAG Service ──► chunks + score de similaridade
        │        │
        │        └─► nenhum chunk acima do threshold? ──► resposta cautelosa +
        │                                                  flag "possível gap de conhecimento"
        │
        ├─► Claude precisa citar/recomendar um programa ──► Program Catalog /
        │        Recommendation Engine ──► retorno estruturado (programa, confiança,
        │        justificativa, alternativas) — Claude NUNCA recomenda por conta própria
        │
        ├─► Claude extrai dados de qualificação ──► grava em qualification_data
        │
        └─► Claude gera a mensagem de resposta ao lead
        │
        ▼
Scoring Engine recalcula o score (regra determinística, não o LLM)
        │
        ▼
CRM Sync atualiza Kommo: campos, tags, observações, lead_score
        │
        ▼
Pipeline: lead deveria mudar de etapa? ──► move + loga motivo
        │
        ▼
Score = Hot E critérios de agendamento atingidos?
        │
   ┌────┴─────┐
   │ SIM       │ NÃO
   ▼           ▼
Scheduler   Segue conversando / aguarda follow-up
   │
   ▼
Tem telefone do lead? ──► NÃO ──► coleta o telefone antes de prosseguir
   │ SIM
   ▼
Confirma disponibilidade do lead e sugere horários — preferencialmente
  de segunda a sexta, dentro do horário comercial configurado (seção 13)
   │
   ├─► Lead aceita um horário DENTRO da disponibilidade configurada
   │        │
   │        ▼
   │   Cria Task no Kommo + Evento no Google Calendar (timezone do lead resolvido)
   │        │
   │        ▼
   │   Envia confirmação ao lead (mensagem de template, no canal de origem)
   │
   └─► Lead pede um horário FORA da disponibilidade configurada
            │
            ▼
       NÃO confirma automaticamente ──► cria Task de aprovação humana +
            registra a solicitação em `audit_logs` + informa ao lead que
            a equipe vai confirmar a disponibilidade
   │
   ▼
Notifica equipe (Kommo notification / Slack / e-mail — configurável)
   │
   ▼
Log de auditoria da ação completa (o quê, por quê, com que confiança)

--- em paralelo, todo o tempo ---

Gatilho de escalonamento disparado a qualquer momento
  (palavra-chave, baixa confiança, pedido explícito, reclamação,
   pagamento/desconto, tópico fora da KB)
        │
        ▼
Escalation Service marca human_takeover=true, notifica humano,
  IA para de responder automaticamente até liberação manual

--- assíncrono, via cron ---

Follow-up Worker varre leads "aguardando resposta" há X tempo
        │
        ▼
Está dentro da janela de tentativas configurada?
   │ SIM ──► dispara mensagem de follow-up (respeitando janela de 24h
   │          de mensagens de template no WhatsApp Business, se aplicável)
   │ NÃO ──► encerra automaticamente, marca lead como "sem resposta",
              loga motivo, opcionalmente devolve para funil de marketing
```

---

## 4. Módulos e contratos entre eles

Os módulos do sistema, com o contrato (input/output) entre eles — isso é o que permite implementá-los **separadamente**, cada um testável de forma isolada. Os seis módulos originais (4.1–4.6) mantêm o contrato inalterado; a v2 adiciona os módulos 4.7–4.9, que formam a Camada de Administração (detalhada na seção 19).

### 4.1 Atendimento (Orchestrator + Channel Gateway)
- **Input:** evento normalizado `InboundMessage { lead_id, channel, text, timestamp, contact_ref }`
- **Output:** `OutboundMessage { lead_id, channel, text }` + eventos internos para os demais módulos
- **Depende de:** Memory Service, RAG, Config Service

### 4.2 Qualificação (Qualification Engine)
- **Input:** transcript da conversa atual + `qualification_data` já conhecida (parcial)
- **Output:** `QualificationUpdate { campo, valor, fonte_trecho, confiança }` — nunca sobrescreve um campo já confirmado com confiança baixa
- **Conjunto obrigatório [v5]:** para quem é · idade do piloto · de onde é · contato · objetivo no kart. É o que destrava preço (25-A.4) e agendamento (25.2)
- **Uma pergunta por mensagem.** Nunca duas. O conjunto acima é coletado ao longo da conversa, não num bloco
- **Regra importante:** um campo só é gravado como "confirmado" se extraído explicitamente do texto do lead. Inferências devem ser marcadas como `inferred=true` e pesam menos no score.

### 4.3 CRM (CRM Sync Service)
- **Input:** eventos `FieldUpdate`, `TagAdd`, `StageChange`, `NoteAppend`, `ScoreUpdate`
- **Output:** confirmação de escrita no Kommo + log
- **Regra importante:** é o **único** módulo com permissão de escrita no Kommo. Nenhum outro módulo chama a API do Kommo diretamente — evita condição de corrida e centraliza retry/idempotência.

### 4.4 Agendamento (Scheduler)
- **Input:** `ScheduleRequest { lead_id, telefone, preferência_de_data, timezone }`
- **Output:** `Appointment { kommo_task_id, google_event_id, horário_confirmado }` — quando o horário está dentro da disponibilidade configurada — ou `PendingApproval { kommo_task_id, motivo }` — quando o lead pede um horário fora da disponibilidade configurada
- **Regra importante:** coleta o telefone do lead antes de prosseguir, se ainda não existir. Sugestões priorizam segunda a sexta, dentro do horário comercial (seção 13). Horário fora da disponibilidade configurada **nunca** é confirmado automaticamente — vira Task de aprovação humana, com a solicitação registrada em `audit_logs` e o lead informado de que a equipe vai confirmar.
- **Depende de:** Google Calendar API, regras de horário comercial (Config Service)

### 4.5 Follow-up (Follow-up Worker)
- **Input:** cron trigger + `leads` com `status = awaiting_response`
- **Output:** `OutboundMessage` (mensagem de follow-up) ou `LeadClosed { motivo: no_response }`
- **Depende de:** Config Service (intervalos, número máximo de tentativas)

### 4.6 Escalonamento (Escalation Service)
- **Input:** gatilho (keyword, baixa confiança reportada pelo Orchestrator, tag `human_takeover_requested`)
- **Output:** `EscalationEvent { lead_id, motivo, prioridade }` → notificação à equipe + `human_takeover=true` no lead
- **Regra importante:** uma vez escalado, a IA só volta a responder automaticamente se um humano explicitamente liberar o lead (nunca reassume sozinha).

### 4.7 Catálogo de Programas (Program Catalog Service) — **novo, v2**
- **Input:** `get_program(id | slug)`, `search_programs(filters | keywords)` — somente leitura para o Orchestrator; escrita só via Admin Panel
- **Output:** `Program { name, description, objective, target_audience, age_min, age_max, recommended_level, prerequisites, benefits, differentiators, faq[], status, recommendation_priority, keywords, display_order }`
- **Regra importante:** é a única fonte de verdade sobre programas. Ao salvar, dispara reindexação automática na Base de Conhecimento (seção 19.2). Programas nunca são apagados fisicamente enquanto houver histórico vinculado (`status=inactive` no lugar) — detalhe completo na seção 20.

### 4.8 Recommendation Engine — **novo, v2**
- **Input:** `LeadProfile` (idade, experiência, objetivo, orçamento, disponibilidade, idioma, país + `qualification_data`)
- **Output:** `RecommendationResult { recommended_program_id, confidence, justification, alternatives[] }`
- **Regra importante:** avalia `recommendation_rules` (dado, não prompt) contra o perfil; nunca é o LLM decidindo. Detalhamento completo na seção 21.

### 4.9 Admin Panel — **novo, v2**
- **Input:** ações de CRUD de um usuário não técnico autenticado
- **Output:** grava em `programs`, `program_faq`, `recommendation_rules`, `knowledge_documents` ou `configurations`, conforme a tela; toda gravação é validada e logada em `audit_logs`
- **Regra importante:** é a única superfície de escrita para regra de negócio — nenhuma dessas tabelas deve ser editada diretamente em produção fora dele, para preservar validação e auditoria. Detalhamento completo na seção 22.

---

## 5. Estrutura de memória

### 5.1 Camada de curto prazo (conversa ativa)
- As últimas mensagens da conversa corrente ficam disponíveis **verbatim** (ex.: últimas ~20 mensagens ou ~4–6k tokens, o que vier primeiro).
- Armazenadas em `messages`, com cache quente em Redis por `lead_id` enquanto a conversa está "ativa" (sem gap de inatividade maior que o timeout configurado, ex.: 45 min).

### 5.2 Camada de longo prazo (entre conversas / entre sessões)
Em vez de reprocessar o histórico completo a cada nova mensagem (custo cresce linearmente com o tempo de vida do lead), mantemos:

- **`qualification_data`**: campos estruturados já extraídos (idade, orçamento, programa, urgência etc.) — sempre a versão mais atual, não histórico bruto.
- **`lead_master_summary`**: um único texto cumulativo por lead, atualizado incrementalmente. Quando uma sessão de conversa é encerrada (timeout de inatividade), um job assíncrono roda:
  1. Gera um resumo da sessão que acabou de terminar (tópicos, decisões, objeções, sentimento).
  2. Funde esse resumo com o `lead_master_summary` existente via chamada ao LLM ("aqui está o resumo anterior do lead + o que aconteceu na última conversa; produza um resumo atualizado, mantendo apenas o que ainda é relevante").
  3. Substitui o `lead_master_summary` (não concatena — isso é o que mantém o tamanho **limitado**, independente de quantas conversas o lead já teve).

Isso resolve diretamente os dois requisitos:
- **Contexto entre várias conversas:** `qualification_data` + `lead_master_summary` são carregados no início de toda nova sessão, sem precisar releituras de mensagens antigas.
- **Redução de custo de tokens:** o custo de "lembrar" um lead é O(1) em relação ao tempo — não cresce conforme o lead acumula meses de histórico.

### 5.3 O que é injetado no prompt a cada turno
```
[lead_master_summary]         ← sempre
[qualification_data atual]    ← sempre, em formato estruturado
[últimas mensagens da sessão] ← só da conversa ativa
[chunks de RAG relevantes]    ← só quando há pergunta a responder
```
Histórico bruto de conversas antigas **nunca** é reinjetado — só o resumo.

---

## 6. Prompt System

Arquitetura de prompt **composta**, não um mega-prompt único. Um roteador de estado decide qual "modo" está ativo e monta o prompt final combinando quatro camadas:

```
┌─────────────────────────────────────────────┐
│ 1. MASTER PROMPT (fixo)                      │
│    Identidade, idiomas, tom de voz, regras   │
│    de segurança inegociáveis (nunca inventar,│
│    nunca prometer preço/disponibilidade sem   │
│    confirmação, quando escalar)               │
├─────────────────────────────────────────────┤
│ 2. CONTEXTO DO LEAD (dinâmico)                │
│    lead_master_summary, qualification_data,   │
│    canal, idioma detectado                    │
├─────────────────────────────────────────────┤
│ 3. PROMPT DE MODO (um dos abaixo)             │
│    FAQ · Qualificação · Follow-up ·           │
│    Agendamento · Escalonamento                │
├─────────────────────────────────────────────┤
│ 4. TOOLS HABILITADAS PARA O MODO              │
│    (ver tabela abaixo)                        │
└─────────────────────────────────────────────┘
```

### 6.1 Master Prompt — conteúdo (esqueleto, não texto final)
- Persona: assistente comercial da URace, tom acolhedor e direto.
- Idioma primário inglês; responde em português/espanhol quando o lead escreve nesses idiomas.
- Regras inegociáveis de segurança (ver seção 11) — repetidas aqui porque devem valer em **qualquer** modo.
- Instrução explícita de **ignorar instruções embutidas nas mensagens do lead** que tentem alterar seu comportamento (defesa contra prompt injection).
- Lista de tools disponíveis e quando usá-las.
- **[v2]** Nenhum nome, descrição, preço ou regra de elegibilidade de programa vive neste prompt — o agente é instruído a **sempre** consultar `get_program_details` ou `get_program_recommendation` antes de mencionar qualquer programa. Se o portfólio da URace mudar amanhã, este prompt não muda uma linha.

### 6.2 Prompts de modo (esqueleto de cada um)

| Modo | Objetivo | Conteúdo do prompt específico | Tools habilitadas |
|---|---|---|---|
| **FAQ** | Responder dúvidas sobre programas/preços/local | Instrui a **sempre** buscar na KB (ou no Catálogo, para dados estruturados do programa) antes de responder; proíbe responder de memória sobre preço/disponibilidade/detalhes de programa. **[v5]** Preço nunca é antecipado: só sai mediante pergunta explícita + qualificação mínima, um valor por vez, com enquadramento de valor antes do número (seção 25-A) | `search_knowledge_base`, `get_program_details`, `get_lead_profile` |
| **Qualificação** | Coletar os 9 campos de qualificação de forma natural (não interrogatório) | Checklist dos campos ainda faltantes; instrui a perguntar no máximo 1-2 por vez, no fluxo da conversa; quando houver dados suficientes, chama `get_program_recommendation` antes de sugerir qualquer programa | `update_qualification_field`, `search_knowledge_base`, `get_program_recommendation` |
| **Agendamento** | Fechar um horário de ligação | Regras de horário comercial, timezone, como oferecer 2-3 opções sem inventar disponibilidade real | `check_calendar_availability`, `create_calendar_event`, `create_kommo_task` |
| **Follow-up** | Reengajar lead silencioso | Tom mais breve, variação de abordagem por tentativa (1ª tentativa ≠ 3ª tentativa), instrução de encerrar educadamente na última tentativa | `send_message`, `close_lead` |
| **Escalonamento** | Transição suave para humano | Instrui a avisar o lead que um especialista vai continuar, sem parecer uma falha do sistema | `escalate_to_human`, `add_note` |

### 6.3 Tools (function calling) do Orchestrator — visão geral
`search_knowledge_base(query)` · `get_lead_profile(lead_id)` · `get_program_details(program_id_or_slug)` *(consulta o Program Catalog Service)* · `get_program_recommendation(lead_profile)` *(chama o Recommendation Engine, não o LLM decide)* · `update_qualification_field(field, value, confidence)` · `calculate_lead_score(lead_id)` *(chama o Scoring Engine, não o LLM decide)* · `update_kommo_field(field, value)` · `add_tag(tag)` · `move_pipeline_stage(stage)` · `check_calendar_availability(range, timezone)` · `create_calendar_event(...)` · `create_kommo_task(...)` · `escalate_to_human(reason, priority)` · `log_decision(action, reasoning)`

---

## 7. Base de conhecimento (RAG)

### 7.1 Estrutura
- Documentos organizados por categoria (`kart_school`, `summer_camp`, `coaching`, `race_support`, `rental_karts`, `produtos`, `eventos`, `horarios`, `valores`, `localizacao`, `faq_geral`).
- **[v2]** Documentos de categoria de programa não são mais digitados manualmente: são **gerados automaticamente** a partir dos campos `description`, `objective`, `benefits`, `differentiators` e `program_faq` de cada registro em `programs`, sempre que o programa é criado/editado no Admin Panel (`knowledge_documents.source_type='auto_generated'`). Documentos sem correspondência num programa (localização, políticas gerais, promoções, eventos) continuam sendo autorados manualmente (`source_type='manual'`) — ver seção 19.2.
- Cada documento é dividido em chunks semânticos (~300–500 tokens) no momento de salvar/atualizar.
- Chunks são vetorizados (embeddings) e armazenados junto com metadados (categoria, documento de origem, idioma, última atualização e, quando aplicável, o `program_id` de origem).

### 7.2 Fluxo de consulta
1. Orchestrator (via tool `search_knowledge_base`) envia a pergunta do lead.
2. Busca por similaridade retorna top-k chunks.
3. Chunks abaixo de um threshold de similaridade configurável são descartados — se **nenhum** chunk passar do threshold, o agente **não responde com base em suposição**: informa que vai confirmar e, dependendo da configuração, dispara escalonamento silencioso (notifica equipe que a KB pode ter um gap).
4. Chunks retornados entram no prompt com sua fonte, para o modelo poder responder de forma rastreável.

### 7.3 Atualização simples da base
- **[v2]** A edição acontece no **Admin Panel** (seção 22) — telas dedicadas por tipo de conteúdo (Programas, FAQ, Políticas, Promoções, Eventos), todas sem tocar em código. Documentos ligados a um programa (descrição, FAQ específico) são editados na própria tela do programa e se reindexam automaticamente; documentos genéricos (localização, políticas) têm tela própria de texto livre.
- Ao salvar, um job reprocessa: re-chunking + re-embedding apenas do documento alterado (não da base inteira).
- Versionamento: o documento anterior continua servindo buscas até o novo terminar de ser indexado (evita janela sem resposta).
- **[Resolvido — decisão em aberto #2] Preços e catálogo comercial vêm do Google Sheets.** A URace definiu uma planilha do Google Sheets como fonte oficial de preços, programas, serviços e valores comerciais variáveis (a planilha real será compartilhada depois). Em vez de um `pricing_catalog` manual, um **job de sincronização** (Google Sheets API, leitura periódica) atualiza os campos correspondentes em `programs` — o mapeamento exato de colunas da planilha para campos do Catálogo (seção 20.1) é finalizado quando a planilha for compartilhada. Esse job passa a ser a fonte primária para os campos que vierem da planilha; o Admin Panel continua sendo o caminho de edição para o que não vier dela (ex.: FAQ, diferenciais, se a planilha não cobrir esse conteúdo).

---

## 8. Lead Scoring

### 8.1 Por que regra determinística, não "vibe" do LLM
Para ser objetivo, configurável e auditável (requisito explícito do projeto), o score **não** é "o que o Claude achar". O Claude extrai os fatos; uma função de pontuação (que vive na Config Service, editável sem deploy) calcula o número.

### 8.2 Critérios e pesos (proposta inicial — ajustável em config)

| Critério | Peso máx. | Como é avaliado |
|---|---|---|
| Urgência / prazo pretendido | 25 | "essa semana" = máximo; "só pesquisando, sem data" = mínimo |
| Orçamento compatível | 20 | Orçamento mencionado ≥ faixa de preço do programa de interesse |
| Programa/interesse definido | 15 | Lead já escolheu um programa específico vs. interesse vago |
| Perfil do piloto compatível | 15 | Idade/experiência batem com os requisitos do programa desejado |
| Engajamento na conversa | 15 | Responde rápido, faz perguntas específicas, mensagens elaboradas |
| Disponibilidade para agendar | 10 | Aceita ou propõe ativamente um horário de ligação |
| **Total** | **100** | |

> **[v2]** `programa_desejado` deixou de ser texto livre — agora referencia `programs.id` no Catálogo (seção 20). O critério "Programa/interesse definido" só é considerado resolvido quando esse vínculo existe, não quando o lead apenas menciona um nome solto.

### 8.3 Classificação

| Score | Classificação | Ação |
|---|---|---|
| ≥ 70 | 🔥 Hot Lead | Aciona fluxo de agendamento |
| 40–69 | 🟠 Warm Lead | Continua qualificando / nutrição mais próxima |
| < 40 | 🔵 Cold Lead | Segue em follow-up de baixa frequência |

### 8.4 Explicabilidade
Cada cálculo de score grava em `lead_scores.criteria_breakdown` o valor atribuído a cada critério **e o trecho da conversa que originou aquele valor** — isso é o que permite responder "por que esse lead foi classificado como Warm" sem depender de reconstruir a lógica manualmente.

### 8.5 Nota de configurabilidade
Pesos, thresholds e as regras de "o que conta como urgência alta/média/baixa" ficam em `configurations` (categoria `scoring_rules`), não hardcoded — a equipe da URace pode recalibrar sem intervenção de engenharia. **[v2]** Essa recalibração ganha uma tela dedicada no Admin Panel (seção 22), com campos numéricos por critério — sem editar JSON à mão.

---

## 9. Modelo de dados

Proposta em PostgreSQL (assumindo `pgvector` para embeddings — ver seção 16 sobre essa escolha). Este é o núcleo; campos de auditoria (`created_at`, `updated_at`) omitidos por brevidade onde óbvio.

```sql
-- ==========================================================
-- LEADS E CONTATOS
-- ==========================================================
CREATE TABLE leads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kommo_lead_id       BIGINT UNIQUE NOT NULL,
    name                TEXT,
    preferred_language  TEXT DEFAULT 'en',
    primary_channel     TEXT,                      -- whatsapp/instagram/messenger/email/web_form
    lead_source         TEXT,                       -- origem para métricas
    current_stage       TEXT,
    status              TEXT DEFAULT 'active',       -- active/awaiting_response/qualified/scheduled/closed/escalated
    human_takeover      BOOLEAN DEFAULT FALSE,
    lead_master_summary TEXT,                        -- resumo cumulativo (seção 5.2)
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE contacts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id       UUID REFERENCES leads(id),
    channel       TEXT NOT NULL,
    external_id   TEXT NOT NULL,                    -- telefone, @instagram, e-mail etc.
    UNIQUE (channel, external_id)
);

-- ==========================================================
-- CONVERSAS E MEMÓRIA
-- ==========================================================
CREATE TABLE conversations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id       UUID REFERENCES leads(id),
    channel       TEXT NOT NULL,
    started_at    TIMESTAMPTZ DEFAULT now(),
    ended_at      TIMESTAMPTZ,
    session_summary TEXT                             -- resumo desta sessão específica
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id),
    sender_type     TEXT NOT NULL,                   -- lead / ai / human_agent
    content         TEXT NOT NULL,
    tokens          INT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- QUALIFICAÇÃO E SCORE
-- ==========================================================
CREATE TABLE qualification_data (
    lead_id                    UUID PRIMARY KEY REFERENCES leads(id),
    segment_id                 UUID REFERENCES segments(id),   -- [v3] define QUAIS campos abaixo fazem sentido
    segment_confidence         TEXT,                            -- [v3] low/medium/high
    segment_fields             JSONB,                           -- [v3] campos específicos do segmento
                                                                 -- (ex. corporate: headcount, empresa, data do evento)
    telefone                   TEXT,                            -- [v3] pré-requisito para agendar (seção 24)
    interesse                  TEXT,
    programa_desejado          UUID REFERENCES programs(id),  -- [v2] antes era TEXT livre; agora referencia o Catálogo
    programa_desejado_raw_text TEXT,                           -- [v2] o que o lead disse, para auditoria/fallback
    experiencia_kart           TEXT,
    idade_piloto      INT,
    categoria         TEXT,
    objetivo          TEXT,
    orcamento         NUMERIC,
    data_pretendida   DATE,
    urgencia          TEXT,                          -- alta/media/baixa
    updated_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE lead_scores (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id            UUID REFERENCES leads(id),
    score_total        INT NOT NULL,
    classification     TEXT NOT NULL,                -- hot/warm/cold
    criteria_breakdown JSONB NOT NULL,                -- {criterio: {pontos, trecho_origem}}
    calculated_at      TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- BASE DE CONHECIMENTO (RAG)
-- ==========================================================
CREATE TABLE knowledge_documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title         TEXT NOT NULL,
    category      TEXT NOT NULL,
    content       TEXT NOT NULL,
    language      TEXT DEFAULT 'en',
    status        TEXT DEFAULT 'active',                -- active/draft/archived
    version       INT DEFAULT 1,
    source_type   TEXT DEFAULT 'manual',                -- manual/auto_generated              [v2]
    source_ref_id UUID,                                  -- ex.: programs.id quando auto_generated [v2]
    updated_by    TEXT,
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE knowledge_chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID REFERENCES knowledge_documents(id),
    chunk_text    TEXT NOT NULL,
    embedding     VECTOR(1536),                       -- dimensão depende do modelo de embedding
    metadata      JSONB
);

-- ==========================================================
-- SEGMENTOS  [v3 — NOVO]
-- Agrupa o portfólio por TIPO DE COMPRADOR, não por produto.
-- É o que permite perguntas de qualificação diferentes por segmento.
-- ==========================================================
CREATE TABLE segments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug              TEXT UNIQUE NOT NULL,     -- corporate/youth/learner/competitor/buyer/racing_team
    name              TEXT NOT NULL,
    description       TEXT,
    required_fields   JSONB NOT NULL,            -- campos de qualificação exigidos NESTE segmento
    optional_fields   JSONB,
    display_order     INT DEFAULT 0,
    status            TEXT DEFAULT 'active'
);

-- ==========================================================
-- CATÁLOGO DE PROGRAMAS  [v2 — NOVO / v3 — ALTERADO]
-- ==========================================================
CREATE TABLE programs (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                     TEXT NOT NULL,
    slug                     TEXT UNIQUE NOT NULL,       -- referência estável usada por regras/config
    segment_id               UUID REFERENCES segments(id),  -- [v3] a que tipo de comprador atende
    category                 TEXT NOT NULL,              -- academy/summer_camp/race_support/racing_team/
                                                          -- corporate_event/rental/sales
    description              TEXT,
    objective                TEXT,
    target_audience          TEXT,
    age_min                  INT,
    age_max                  INT,
    recommended_level        TEXT,                        -- iniciante/intermediário/avançado
    prerequisites            TEXT,
    benefits                 TEXT,
    differentiators          TEXT,
    keywords                 TEXT[],                       -- usado por RAG e por matching de intenção
    display_order            INT DEFAULT 0,
    recommendation_priority  INT DEFAULT 0,                -- peso base somado pelo Recommendation Engine
    status                   TEXT DEFAULT 'active',         -- active/inactive
    source_sheet_tab          TEXT,                          -- [v3] aba de origem na planilha
    synced_at                  TIMESTAMPTZ,                    -- [v3] último sync bem-sucedido
    created_at                TIMESTAMPTZ DEFAULT now(),
    updated_at                TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- OFERTAS / VARIANTES DE PREÇO  [v3 — NOVO]
-- O rate card real da URace é todo neste nível: (serviço × tipo de evento) → preço.
-- Ex.: "Exclusive Mechanic" × "Regional and National events" = $600/day
-- ==========================================================
CREATE TABLE program_offers (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id           UUID REFERENCES programs(id) ON DELETE CASCADE,
    offer_name           TEXT NOT NULL,            -- "Exclusive Mechanic", "Engine Rental-100CC"
    context              TEXT,                      -- "Club event - Orlando", "National Events", "Practice"
    description          TEXT,
    price_amount         NUMERIC,                    -- valor numérico normalizado (600)
    price_currency       TEXT DEFAULT 'USD',
    price_unit           TEXT,                        -- day / event / 4_days / person / package
    price_is_indicative  BOOLEAN DEFAULT TRUE,         -- rate card diz "rate can vary +/- $50"
    price_variance_note  TEXT,                          -- texto exato da ressalva, para o agente reproduzir
    conditions_note      TEXT,                           -- ex.: "spare engine add-on = 40% do valor do motor"
    status               TEXT DEFAULT 'active',
    source_sheet_tab     TEXT,
    source_sheet_row     INT,                             -- rastreabilidade linha-a-linha com a planilha
    synced_at            TIMESTAMPTZ
);

-- ==========================================================
-- AUDITORIA DE SINCRONIZAÇÃO DA PLANILHA  [v3 — NOVO]
-- ==========================================================
CREATE TABLE catalog_sync_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    triggered_by    TEXT NOT NULL,               -- schedule / manual
    started_at      TIMESTAMPTZ DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT,                          -- success / partial / failed
    rows_read       INT,
    rows_applied    INT,
    rows_rejected   INT,
    diff_summary    JSONB,                          -- o que mudou (criado/atualizado/desativado)
    errors          JSONB                            -- linha + motivo de cada rejeição
);

CREATE TABLE program_faq (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id    UUID REFERENCES programs(id) ON DELETE CASCADE,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    display_order INT DEFAULT 0,
    status        TEXT DEFAULT 'active'
);

-- ==========================================================
-- RECOMMENDATION ENGINE  [v2 — NOVO]
-- ==========================================================
CREATE TABLE recommendation_rules (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  TEXT NOT NULL,
    rule_type             TEXT NOT NULL,                  -- match / boost / exclude
    conditions            JSONB NOT NULL,                 -- árvore de condições: {field, operator, value, and/or}
    target_program_id     UUID REFERENCES programs(id),    -- alvo direto (nullable)
    target_category       TEXT,                             -- alternativa a target_program_id (aplica a uma categoria)
    score_impact          INT NOT NULL,                      -- pontos somados/subtraídos ao candidato
    explanation_template  TEXT,                               -- texto-base da justificativa (dado, não gerado pelo LLM)
    priority_order        INT DEFAULT 0,                       -- ordem de avaliação / desempate
    status                TEXT DEFAULT 'active',
    created_by             TEXT,
    updated_at               TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE recommendation_log (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id                  UUID REFERENCES leads(id),
    input_profile            JSONB NOT NULL,                 -- snapshot do perfil usado na avaliação
    recommended_program_id   UUID REFERENCES programs(id),
    confidence                NUMERIC,
    rules_fired                 JSONB,                          -- regras que contribuíram + pontos de cada uma
    alternatives                  JSONB,
    evaluated_at                    TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- AGENDAMENTO
-- ==========================================================
CREATE TABLE appointments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id             UUID REFERENCES leads(id),
    kommo_task_id       BIGINT,
    google_event_id     TEXT,
    scheduled_at        TIMESTAMPTZ,                    -- [v3] nulo enquanto pendente de aprovação
    timezone            TEXT,
    status              TEXT DEFAULT 'scheduled',        -- scheduled/confirmed/attended/no_show/cancelled/
                                                          -- pending_human_approval  [v3]
    requested_slot      TIMESTAMPTZ,                      -- [v3] horário que o lead pediu (pode ser fora do expediente)
    requested_slot_note TEXT,                              -- [v3] o que o lead disse, em texto
    approval_task_id    BIGINT,                             -- [v3] Task no Kommo criada para aprovação humana
    phone_collected     TEXT,                                -- [v3] telefone usado para a ligação
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- FOLLOW-UP
-- ==========================================================
CREATE TABLE follow_ups (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id        UUID REFERENCES leads(id),
    attempt_number INT NOT NULL,
    scheduled_at   TIMESTAMPTZ NOT NULL,
    sent_at        TIMESTAMPTZ,
    status         TEXT DEFAULT 'pending'              -- pending/sent/skipped/failed
);

-- ==========================================================
-- ESCALONAMENTO
-- ==========================================================
CREATE TABLE escalations (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id        UUID REFERENCES leads(id),
    reason         TEXT NOT NULL,                      -- keyword/low_confidence/explicit_request/complaint/payment/discount/kb_gap
    triggered_by   TEXT NOT NULL,                       -- ai/rule/lead_request
    priority       TEXT DEFAULT 'normal',
    escalated_at   TIMESTAMPTZ DEFAULT now(),
    resolved_at    TIMESTAMPTZ,
    resolution_notes TEXT
);

-- ==========================================================
-- LOGS / AUDITORIA
-- ==========================================================
CREATE TABLE audit_logs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id      UUID REFERENCES leads(id),
    actor        TEXT NOT NULL,                        -- ai/system/human
    action       TEXT NOT NULL,                         -- message_sent/field_updated/tag_added/
                                                          -- stage_moved/score_calculated/escalation_triggered/
                                                          -- appointment_created/followup_sent
    details      JSONB,
    confidence   NUMERIC,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- ==========================================================
-- CONFIGURAÇÃO
-- ==========================================================
CREATE TABLE configurations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category    TEXT NOT NULL,                          -- business_hours/follow_up/scoring_rules/
                                                          -- escalation_keywords/message_templates/pipeline_mapping
    key         TEXT NOT NULL,
    value       JSONB NOT NULL,
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (category, key)
);

-- ==========================================================
-- OBJEÇÕES (para métricas)
-- ==========================================================
CREATE TABLE objections_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id      UUID REFERENCES leads(id),
    category     TEXT NOT NULL,                          -- preço/localização/horário/confiança/outro
    excerpt      TEXT,
    detected_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## 10. Integrações

### 10.1 Kommo CRM
Confirmado via documentação oficial (`developers.kommo.com`):
- **API REST v4**, ex. `POST /api/v4/leads/complex` para criar leads com contato/empresa e `custom_fields_values` já preenchidos.
- **Webhooks** configuráveis por evento (`lead added`, `lead edited`, `lead status changed`, `responsible user changed` etc.), entregues como payload contendo `id`, `status_id`, `pipeline_id`, `custom_fields` (id/nome/valor) e o `account` de origem — é a partir daqui que o Gateway normaliza o evento.
- **Digital Pipeline**: permite configurar regras de automação por etapa direto no Kommo — útil como camada complementar (ex.: notificar time de vendas quando o agente move um lead para "Qualificado"), mas a lógica de decisão de qualificação/score continua no nosso Orchestrator, não no Kommo.
- **Campos customizados** precisam ser criados previamente na conta Kommo (interesse, programa, experiência, idade do piloto, orçamento, urgência, lead score, motivo da classificação) e mapeados por `field_id` na tabela `configurations` (categoria `pipeline_mapping`) — assim, se o ID de um campo mudar, é só atualizar config, não código.
- **[v2] Sincronização do campo "Programa" no Kommo:** se esse campo for uma lista fechada (select) no Kommo, toda criação/desativação de programa no Admin Panel exigiria também atualizar as opções desse campo via API — complexidade extra e mais um ponto de divergência possível. Alternativa mais simples e recomendada: usar um campo de **texto livre** no Kommo (preenchido pelo CRM Sync com o nome do programa vindo do Catálogo) e deixar a lista fechada de programas existir só em `programs` — evita manter duas fontes de verdade sincronizadas.

### 10.2 Google Calendar
- `freebusy.query` (ou `events.list`) para checar disponibilidade da equipe antes de propor horário.
- `events.insert` para criar o evento, com o timezone resolvido a partir do canal/telefone do lead (ou perguntado explicitamente quando ambíguo).
- Confirmação ao lead só é enviada **depois** que o evento é criado com sucesso (nunca antes) — evita prometer um horário que falhou ao ser criado.

### 10.3 Canais — confirmados (Fase 1) e futuros
**[Resolvido — decisão em aberto #1]** Os canais hoje conectados ao Kommo da URace são: **WhatsApp, Instagram, Facebook Messenger, TikTok e E-mail.** Toda a comunicação da Fase 1 passa exclusivamente pelo Kommo como hub — não há integração direta com a API de nenhum desses canais nesta primeira versão. Formulários de site/landing pages **não estão conectados ainda**; permanecem como canal futuro (ver abaixo).

Ponto importante de arquitetura: o Kommo **já unifica nativamente** esses canais (incluindo WhatsApp Business via Meta Cloud API, sendo Meta Partner oficial) numa única inbox, com o **Salesbot** como camada de automação e uma **Chats API** própria para quem quiser conectar um canal novo que o Kommo ainda não suporte nativamente.

**Recomendação:** o agente não precisa (nem deve, inicialmente) integrar diretamente com a Meta Cloud API, Instagram Graph API etc. Ele fala apenas com o Kommo (webhooks de entrada + API de saída), e o Kommo cuida do transporte por canal. Isso significa:
- Um único `Channel Adapter` real na primeira fase: **Kommo**.
- Formulários de site/landing pages: quando conectados no futuro, também viram leads diretamente no Kommo (via web forms nativos ou webhook simples) e caem no mesmo fluxo — nenhuma mudança de arquitetura necessária para isso.
- Um adaptador de canal dedicado só se torna necessário no futuro se a URace quiser um canal que o Kommo não suporte nativamente (aí sim usa-se a Chats API do Kommo para "ensinar" o novo canal a aparecer na inbox unificada).

Ainda assim, a camada `InboundMessage`/`OutboundMessage` internamente é desenhada de forma agnóstica de canal (o `channel` é só um atributo do evento) — então, se um dia for necessário sair do Kommo como hub único, a mudança fica isolada no Gateway, sem tocar no Orchestrator, Scoring, RAG etc.

---

## 11. Segurança e guardrails

| Regra | Como é garantida |
|---|---|
| Nunca inventar informação | Toda resposta factual exige grounding via RAG ou campo estruturado; sem chunk relevante → resposta cautelosa, não resposta inventada |
| **[v2]** Nunca recomendar/descrever um programa fora do Catálogo | `get_program_details`/`get_program_recommendation` são as únicas fontes permitidas para citar um programa; master prompt proíbe explicitamente mencionar nome, preço ou elegibilidade de programa sem ter chamado a tool correspondente nesse turno |
| **[v5]** Nunca antecipar preço | Preço só sai mediante pergunta explícita do lead + qualificação mínima completa; um valor por vez, nunca a tabela. Ofertas com `agent_can_quote=FALSE` jamais são citadas (seção 25-A) |
| Não prometer preço/disponibilidade sem confirmação | Preço/disponibilidade tratados como dado estruturado (não texto solto), e agendamento só confirma **depois** de escrita bem-sucedida no Calendar |
| Escalar quando a confiança for baixa | Toda chamada de RAG carrega um score de similaridade; abaixo do threshold configurado, o Orchestrator marca `low_confidence` e pode escalar silenciosamente |
| Nunca aplicar desconto/tratar pagamento | Palavras-gatilho (`desconto`, `pagamento`, `reembolso`, `cancelamento` etc., configuráveis) forçam escalonamento imediato, sem passar pelo LLM decidir se responde |
| Reclamações | Classificador simples de sentimento negativo + palavras-gatilho → escalonamento com prioridade alta |
| Resistência a prompt injection | Master prompt instrui explicitamente a tratar o texto do lead como dado, nunca como instrução de sistema; tools sensíveis (desconto, exclusão de dado) simplesmente não existem no toolset do agente |
| Privacidade / LGPD | Minimização de dados coletados; log de consentimento (especialmente relevante para follow-up via WhatsApp, que tem regras próprias de opt-in/janela de 24h para mensagens fora de template); rota para exclusão de dados de um lead a pedido |

---

## 12. Logs e auditoria

Toda ação relevante grava uma linha em `audit_logs` com:
- **actor** (ai/system/human)
- **action** (tipo do evento)
- **details** (payload específico — para `score_calculated`, inclui o `criteria_breakdown` completo)
- **confidence** (quando aplicável — ex. score de similaridade do RAG usado para gerar a resposta)

Isso permite responder, para qualquer lead, três perguntas de auditoria:
1. *Por que esse lead foi classificado como Hot/Warm/Cold?* → `lead_scores.criteria_breakdown` + `audit_logs` filtrados por `action=score_calculated`.
2. *Por que o agente disse isso ao lead?* → mensagem + chunks de RAG usados (guardados em `messages.metadata`).
3. *Por que esse lead foi escalado?* → `escalations.reason` + o log imediatamente anterior que disparou o gatilho.

---

## 13. Configuração

Tudo isso vive em `configurations` (ou um arquivo YAML versionado, se preferirem gestão via Git em vez de painel), organizado por categoria:

| Categoria | Exemplos de conteúdo |
|---|---|
| `business_hours` | Dias/horários de atendimento por canal, timezone da operação |
| `follow_up` | Intervalos entre tentativas (ex. 1h / 24h / 72h), número máximo de tentativas, texto-base por tentativa |
| `scoring_rules` | Pesos por critério, thresholds de Hot/Warm/Cold |
| `escalation_keywords` | Lista de palavras/temas que forçam handoff humano |
| `message_templates` | Textos-base (saudação, confirmação de agendamento, encerramento) em EN/PT/ES |
| `pipeline_mapping` | De/para entre nomes internos de campo e `field_id`/`pipeline_id`/`status_id` do Kommo |

**[Resolvido — decisão em aberto #3]** Valor definido para `business_hours`:
```json
{
  "weekdays": { "days": ["mon","tue","wed","thu","fri"], "open": "09:00", "close": "18:00" },
  "weekend":  { "days": ["sat","sun"], "open": "08:00", "close": "12:00" },
  "timezone": "America/New_York"
}
```
"Horário de Orlando" corresponde ao fuso `America/New_York` (observa horário de verão dos EUA automaticamente). O Scheduler (seção 4.4) nunca propõe ou confirma um horário fora dessa janela sem passar pelo fluxo de aprovação humana.

Objetivo: qualquer ajuste de regra de negócio (ex.: "aumentar o peso do orçamento no score" ou "mudar o horário comercial de sábado") é uma edição de dado, não um deploy.

---

## 14. Métricas

| Métrica | Como é calculada | Fonte |
|---|---|---|
| Tempo médio de primeira resposta | `avg(primeira mensagem do ai − criação do lead)` | `messages` + `leads.created_at` |
| Taxa de qualificação | leads com `qualification_data` completa (ou score calculado) ÷ total de leads que interagiram | `qualification_data`, `leads` |
| Taxa de conversão para reunião | leads com `appointments` ÷ leads qualificados | `appointments`, `lead_scores` |
| Quantidade de reuniões agendadas | `count(appointments)` no período | `appointments` |
| Taxa de comparecimento | `appointments.status = attended` ÷ total de `appointments` no período | `appointments` (status atualizado manualmente ou via confirmação no Calendar) |
| Taxa de conversão por origem | agrupar `appointments`/`qualified leads` por `leads.lead_source` | `leads`, `appointments` |
| Principais objeções | agregação de `objections_log` por `category`, ordenado por frequência | `objections_log` |

Todas essas métricas podem ser servidas por uma camada simples de BI (Metabase, ou um dashboard interno) direto em cima do Postgres — não é necessário um data warehouse separado no volume inicial de leads.

---

## 15. Riscos e problemas potenciais

| Risco | Mitigação proposta |
|---|---|
| Mensagens fragmentadas do lead (várias mensagens seguidas) geram respostas picadas | Debounce de ~8-10s antes de processar, agrupando mensagens da mesma janela |
| Humano edita o lead manualmente no Kommo enquanto a IA está no meio de uma resposta | Flag `human_takeover`; qualquer edição manual detectada via webhook pausa a IA até liberação explícita |
| Alucinação de preço/disponibilidade | Grounding obrigatório (RAG + dado estruturado) + fallback cauteloso, seção 11 |
| Falha/instabilidade da API do Kommo ou rate limit | Fila com retry exponencial, idempotência por `kommo_lead_id` + `event_id` |
| Lead duplicado entre canais (mesma pessoa manda WhatsApp e preenche formulário) | Resolução de identidade por telefone/e-mail normalizado antes de criar novo `lead` |
| Fuso horário incorreto no agendamento | Timezone resolvido explicitamente (telefone/país do canal) e confirmado na mensagem de confirmação |
| Custo de LLM cresce com volume | Resumo cumulativo (seção 5) evita reprocessar histórico completo; modelo mais leve para tarefas de extração simples, modelo mais forte só para a geração conversacional |
| Regras do WhatsApp Business (janela de 24h para mensagens livres, necessidade de template fora dela) | Follow-up Worker precisa saber diferenciar mensagem livre vs. template aprovado, conforme canal |
| Deriva de qualidade do agente ao longo do tempo (prompt drift, mudança de comportamento) | Conjunto de casos de teste (eval set) de conversas reais anonimizadas, rodado antes de qualquer alteração de prompt entrar em produção |
| Dado pessoal sensível (LGPD) | Minimização de coleta, log de consentimento, rota de exclusão de dados |
| Falso "Hot Lead" por lead apenas educado/engajado sem intenção real | Critério de urgência e orçamento pesam mais que engajamento puro na fórmula (seção 8.2) |
| **[v2]** Regras de recomendação conflitantes (duas regras `match` apontam para programas diferentes no mesmo perfil) | Desempate determinístico: maior `score_impact` acumulado vence; empate usa `programs.recommendation_priority`, depois `display_order`. Tudo registrado em `recommendation_log.rules_fired` para auditoria |
| **[v2]** Usuário não técnico configura algo inconsistente no Admin Panel (ex. idade mínima > máxima, regra sem condição) | Validação de schema no momento de salvar + simulador antes de publicar regras de recomendação (seção 22.3) |
| **[v2]** Mudança no Admin Panel não refletir imediatamente numa conversa em andamento | Cache do Catalog/Config Service com TTL curto ou invalidação por evento ao salvar — decisão técnica a fechar na implementação (seção 18) |
| **[v2]** Duplicação de conteúdo entre Catálogo e Base de Conhecimento, gerando divergência | Mitigado por design: conteúdo de programa na KB é sempre auto-gerado a partir do Catálogo (seção 7.1), nunca digitado duas vezes |
| **[v2]** Controle de acesso ao Admin Panel (quem pode editar o quê) | Perfis de permissão (Admin/Editor/Leitura); toda alteração é atribuída a um usuário em `audit_logs.actor` |

---

## 16. Stack sugerido

**[Resolvido — decisão em aberto #5]** Sem preferência de linguagem por parte da URace; prioridade é simplicidade, estabilidade, rapidez de entrega e manutenção fácil, com preferência por rodar dentro do ecossistema do Claude quando isso não comprometer a arquitetura. Com esse critério, a recomendação é:

- **Orquestração/Agente:** **Claude Agent SDK** (Python ou TypeScript — ambos oficialmente suportados; a escolha entre os dois pode ficar por conta de quem for implementar). É literalmente "o ecossistema do Claude": entrega de graça o loop do agente, gestão de contexto/sessão, permissionamento fino de tools e suporte nativo a MCP (Model Context Protocol) — reduz boa parte do código que o Orchestrator (seção 4.1) e o Prompt System (seção 6) precisariam implementar à mão, o que atende diretamente ao critério de rapidez/simplicidade.
- **Integração com Kommo:** via **MCP**. Já existem servidores MCP de terceiros para Kommo (ex. hospedados via Composio, ou implementações open-source no GitHub) — vale avaliar se cobrem com precisão os endpoints que a arquitetura precisa (webhooks + custom fields + tasks + pipeline, seção 10.1). Se a cobertura não for exata, construir um MCP server fino próprio, expondo só as tools já definidas nos contratos dos módulos (seção 4) — mais simples e mais alinhado ao contrato do CRM Sync do que adaptar um servidor genérico de terceiros. Essa avaliação é um passo natural da implementação da Fase 3 (Gateway + webhook do Kommo), não uma decisão a fechar agora.
- **Integração com Google Calendar:** Google Calendar API diretamente (cliente oficial Google, disponível em Python/TypeScript).
- **Sincronização com Google Sheets:** Google Sheets API (leitura, conta de serviço) — mecanismo simples, sem necessidade de infraestrutura extra.
- **Banco principal:** PostgreSQL.
- **Vetores (RAG):** `pgvector` como extensão do próprio Postgres — evita operar um serviço a mais.
- **Fila/cache:** Redis (fila leve + cache de sessão).
- **Follow-up worker:** cron job simples.
- **Dashboard de métricas:** Metabase (ou equivalente) direto sobre o Postgres.
- **Hospedagem/deploy:** não definida pela URace — para o MVP, recomenda-se manter tudo rodando como poucos processos (o Agent SDK + um worker de fila), sem quebrar em microsserviços fisicamente separados; os contratos entre módulos (seção 4) já bastam para permitir separar depois, se o volume justificar.

---

## 17. Roadmap de implementação

Ordem sugerida — cada fase é testável isoladamente antes de acoplar à próxima:

1. **Fundação de dados:** schema do banco (seção 9) + Config Service.
2. **[v2] Catálogo de Programas + Admin Panel (mínimo viável):** telas de CRUD de Programas e FAQ, mais o job de sincronização com o Google Sheets de preços (seção 7.3) assim que a planilha for compartilhada — antes de qualquer IA, para já popular o portfólio real da URace.
3. **Gateway + webhook do Kommo:** normalização de eventos, sem IA ainda (só logar/gravar lead).
4. **Memory Service:** curto e longo prazo, sem IA ainda (populado manualmente para teste).
5. **Base de Conhecimento / RAG:** ingestão automática a partir do Catálogo + documentos manuais (políticas, localização, promoções) + busca funcionando isoladamente.
6. **[v2] Recommendation Engine:** telas de regras no Admin Panel + motor de avaliação, testável com perfis de lead simulados, sem IA ainda.
7. **Prompt System + Orchestrator (modo FAQ apenas):** primeira versão que responde dúvidas com grounding (KB + Catálogo), sem qualificar ainda.
8. **Qualification Engine + Scoring Engine:** extração estruturada e cálculo de score, testável com conversas simuladas.
9. **CRM Sync:** escrita real no Kommo (campos, tags, pipeline).
10. **Scheduler + Google Calendar.**
11. **Follow-up Worker.**
12. **Escalation Service** (na prática, os gatilhos de escalonamento devem ser testados desde a fase 7 — mas o serviço dedicado e as notificações à equipe fecham aqui).
13. **Logging/Audit + Métricas/Dashboard.**
14. **[v2] Admin Panel — telas restantes:** Lead Scoring, Follow-ups, Escalonamento, Pipeline Mapping, Templates, Horários (as telas de Programas/FAQ/Regras já saíram nas fases 2 e 6).

---

## 18. Decisões em aberto

**Estado: fechado para o MVP.** As respostas abaixo foram fornecidas pela URace em 28/07/2026 e já estão incorporadas nas seções indicadas. Os itens ainda sem resposta explícita ganharam um default pragmático (não bloqueiam a implementação) e podem ser revisitados depois, sem exigir mudança de arquitetura.

| # | Decisão | Status | Resposta / onde está incorporada |
|---|---|---|---|
| 1 | Canais | ✅ Resolvida | Kommo como hub único. Conectados: WhatsApp, Instagram, Facebook Messenger, TikTok, E-mail. Sem integração direta com APIs de canal na Fase 1 — seção 10.3 |
| 2 | Fonte de verdade de preços | ✅ Resolvida | Google Sheets (preços, programas, serviços, valores comerciais); planilha real a ser compartilhada — seções 7.3, 20.3 |
| 3 | Horário de atendimento humano | ✅ Resolvida | Seg–Sex 09:00–18:00, Sáb–Dom 08:00–12:00, horário de Orlando (`America/New_York`) — seção 13. Fluxo de agendamento detalhado nas seções 3 e 4.4 |
| 4 | Pesos do lead score (seção 8.2) | ⏳ Ainda aberta | Default: seguem como proposta inicial no lançamento; time comercial recalibra depois pelo Admin Panel (seção 22), sem engenharia |
| 5 | Definição de "comparecimento confirmado" | ⏳ Ainda aberta | Default: atualização manual de `appointments.status` pelo vendedor após a ligação |
| 6 | Stack de infraestrutura | ✅ Resolvida | Claude Agent SDK + MCP, sem preferência de linguagem — seção 16 |
| 7 | **[v2]** Autenticação do Admin Panel | ⏳ Ainda aberta | Default: login simples com 2 perfis (Admin/Editor), sem SSO com o Kommo na Fase 1 |
| 8 | **[v2]** Aprovação de regras de recomendação | ⏳ Ainda aberta | Default: mudanças entram em vigor ao salvar; o simulador (seção 22.3) é a salvaguarda da Fase 1 |
| 9 | **[v2]** Resolução de programa por texto livre | ⏳ Ainda aberta | Default: matching por `programs.keywords`/`name`; sem confiança suficiente, o agente pergunta em vez de assumir |

### Novos itens abertos após a leitura da planilha real (v4)

| # | Questão | Status |
|---|---|---|
| 10 | **Aba normalizada na planilha** | ✅ **Resolvida.** Adotado o template de 3 abas (`_segments`, `_programs`, `_offers`) — arquivo `urace-catalogo-template.xlsx`, seção 23.3.1 |
| 11 | **Campos ausentes** (idade, nível, objetivo, pré-requisitos, keywords, segmento) | ✅ **Resolvida.** Entram como colunas na planilha, preenchidas pela equipe progressivamente. O sistema opera com catálogo incompleto por design — seção 23.3 |
| 12 | **Mapeamento aba → segmento** | ✅ **Resolvida.** 5 segmentos definidos a partir do MODO OPERANTE: `corporate`, `youth`, `learner`, `competitor`, `owner_operator` — pré-carregados na aba `_segments` |
| 13 | **Conteúdo das demais 6 abas** | ✅ **Resolvida.** 113 ofertas normalizadas das 6 abas com preço. A aba *Sales - Chassis and Engine* estava sem valores no rate card |
| 14 | **Calendário da equipe:** um calendário único de vendas ou um por vendedor? | ⏳ Aberta. Muda a lógica de `freebusy` no Scheduler |

### 🔴 Conflitos entre documentos — bloqueiam o go-live (v5)

Ao cruzar rate card, CSV de catálogo, MODO OPERANTE, Playbook Comercial e a apostila técnica, apareceram 7 divergências que **não podem ser resolvidas por arquitetura** — exigem decisão da URace. Estão detalhadas na aba `CONFLITOS` do template, com espaço para a resposta. Os dois mais críticos:

| # | Conflito | Por que é crítico |
|---|---|---|
| 1 | **Idade mínima.** Rate card vende Baby Kart a partir de **4 anos**; a apostila técnica diz que *"a pista permite acima de 5 anos somente"* | É segurança e é promessa comercial. O agente não pode confirmar presença de uma criança de 4 anos se a pista não aceita. Precisa da idade real antes de qualquer atendimento automático |
| 5 | **Objetivo do agendamento.** O briefing do projeto define "lead qualificado → agendar ligação"; o MODO OPERANTE (4.1) diz *"não ofereça ligação para iniciante — a call é só para quem já corre"* | Muda o objetivo final do agente. Se o MODO OPERANTE prevalece, o iniciante é fechado **por chat** (reserva de sessão na pista) e a ligação existe só no caminho de handoff ao Italo — o Scheduler passa a servir ao handoff, não à conversão principal |

Os demais (2: Summer Camp para local · 3: Lead & Follow é para iniciante ou avançado · 4: preço de $500 que não existe no rate card · 6: Kart School vs URace Academy · 7: Baby Kart 4-7 vs 5-8 anos) estão na aba `CONFLITOS`.

Vale notar que nenhum deles é erro de quem escreveu os documentos — são ambiguidades que só aparecem quando alguém tenta transformar as regras em código. É esperado que apareçam nesta fase.

Os itens marcados "⏳ Ainda aberta" não impedem o início da implementação — são ajustes de configuração ou de UX, tratáveis durante o desenvolvimento conforme definido pela URace. Os itens 12 e 13 afetam apenas a **cobertura** da recomendação automática (quantos programas o motor consegue sugerir), não o funcionamento do sistema: com eles em aberto, o agente segue respondendo, qualificando e agendando normalmente.

---

## 19. Camada de Administração: Catálogo, Conhecimento e Configuração

O pedido original de separar "Conhecimento" e "Configuração" está certo, mas na prática programas (e futuramente outros produtos/serviços) não se encaixam limpamente em nenhum dos dois — eles têm campos estruturados usados por regras determinísticas (idade, prioridade, status) **e** conteúdo em linguagem natural usado para responder perguntas (descrição, benefícios, FAQ). Por isso a arquitetura v2 tem **três** camadas, não duas:

| Camada | O que é | Exemplos | Onde vive | Quem edita | Como o agente usa |
|---|---|---|---|---|---|
| **Catálogo** | Entidades estruturadas do negócio — fatos sobre o portfólio | Programas (e futuros produtos/serviços) | `programs`, `program_faq` | Admin Panel → Program Catalog Service | Consulta via tool (`get_program_details`, `search_programs`) e via Recommendation Engine; também **alimenta** a Base de Conhecimento |
| **Conhecimento** | Conteúdo em linguagem natural para responder perguntas abertas | Descrição/benefícios/FAQ de programa (auto-gerados), FAQ geral, políticas, localização, promoções, eventos | `knowledge_documents`, `knowledge_chunks` | Admin Panel (parte auto-gerada do Catálogo, parte manual) | Consulta via RAG (`search_knowledge_base`) |
| **Configuração** | Regras de funcionamento do sistema | Pesos de score, horários, mensagens automáticas, regras de recomendação, gatilhos de follow-up/escalonamento, mapeamento de campos do Kommo | `configurations`, `recommendation_rules` | Admin Panel → Config Service | Consultada por motores determinísticos (Scoring Engine, Recommendation Engine, Follow-up Worker, Escalation Service) — nunca diretamente pelo LLM |

**Regra de ouro:** nada disso entra no prompt do agente. O prompt contém só *instruções de como se comportar e como consultar* — nunca *o que responder*. Isso é o que garante os requisitos de arquitetura escalável e extensível do pedido original: adicionar um programa novo é uma linha em `programs`; adicionar uma regra de recomendação nova é uma linha em `recommendation_rules`. Nenhum dos dois exige tocar no Orchestrator, no prompt, ou fazer deploy.

### 19.1 Por que `recommendation_rules` é uma tabela própria, e não mais uma categoria dentro de `configurations`
As demais regras de configuração (horários, pesos de score, templates) são, no fundo, um valor único por chave — cabem bem num `JSONB` genérico. Regras de recomendação são diferentes: precisam de integridade referencial (`target_program_id` apontando para um programa real), precisam ser avaliadas uma a uma pelo motor, e se beneficiam de validação estruturada por regra (seção 22). Forçar isso dentro de um blob JSON genérico tornaria o editor do Admin Panel arriscado de construir — por isso ganham tabela e tela próprias, mas continuam conceitualmente parte da camada de Configuração.

### 19.2 Auto-indexação: do Catálogo para o Conhecimento
Sempre que um programa é criado ou editado no Admin Panel:
1. Program Catalog Service grava/atualiza o registro em `programs` (e `program_faq`, se aplicável).
2. Um job dispara automaticamente: gera (ou atualiza) um `knowledge_document` com `source_type='auto_generated'` e `source_ref_id=programs.id`, montado a partir de `description`, `objective`, `benefits` e `differentiators`; e um documento (ou conjunto de chunks) por FAQ do programa.
3. Re-chunking + re-embedding rodam só sobre o que mudou — mesma lógica já descrita na seção 7.3.

Resultado prático: a equipe da URace edita a informação **uma única vez** (na tela do programa); ela aparece tanto nas respostas de FAQ quanto no Recommendation Engine, sem risco de as duas fontes divergirem.

### 19.3 Impacto em `qualification_data.programa_desejado`
Esse campo deixa de ser texto livre e passa a referenciar `programs.id`. Quando o lead descreve o que quer em linguagem natural, a Qualification Engine tenta resolver contra `programs.keywords`/`name` (o texto original fica preservado em `programa_desejado_raw_text` para auditoria, caso a resolução falhe ou fique ambígua). Ver decisão em aberto #9 sobre se essa resolução deve ser silenciosa ou confirmada explicitamente com o lead.

---

## 20. Catálogo de Programas

### 20.1 De campo pedido para coluna de banco

| Campo pedido pela URace | Coluna em `programs` | Observação |
|---|---|---|
| Nome | `name` | |
| Descrição | `description` | vira Conhecimento (auto-indexado) |
| Objetivo | `objective` | vira Conhecimento |
| Público-alvo | `target_audience` | |
| Faixa etária (quando aplicável) | `age_min`, `age_max` | nulos quando não se aplica |
| Nível recomendado | `recommended_level` | |
| Pré-requisitos | `prerequisites` | |
| Benefícios | `benefits` | vira Conhecimento |
| Principais diferenciais | `differentiators` | vira Conhecimento |
| FAQ específico | tabela `program_faq` | N perguntas por programa; cada uma vira/compõe um documento de Conhecimento |
| Status (ativo/inativo) | `status` | programa `inactive` nunca é sugerido pelo Recommendation Engine nem retornado em busca |
| Prioridade de recomendação | `recommendation_priority` | peso base somado pelo Recommendation Engine e usado em desempate |
| Palavras-chave | `keywords` | usado tanto pelo RAG (retrieval) quanto para resolver menções em texto livre (seção 19.3) |
| Ordem de exibição | `display_order` | usado quando o agente lista mais de um programa numa resposta |

### 20.2 CRUD e integridade
- Criar/editar: sem restrições além de validação de schema (seção 22).
- Desativar: `status='inactive'` — programa some das respostas e recomendações, mas **nunca é apagado fisicamente** enquanto houver `qualification_data`, `recommendation_log` ou `appointments` históricos referenciando-o (preserva integridade referencial e histórico de auditoria).
- Remover de verdade: só permitido se não houver nenhuma referência histórica — ação rara, tratada como exceção, não como fluxo padrão do Admin Panel.

### 20.3 Contrato
- **Leitura (usada pelo Orchestrator):** `get_program(id | slug)`, `search_programs(filters | keywords)`
- **Escrita:** Admin Panel (edição manual, seção 22) **+** job de sincronização a partir do Google Sheets para os campos comerciais/preço (seção 7.3) — o agente conversacional nunca tem permissão de escrita no Catálogo, por nenhum dos dois caminhos.

---

## 21. Recommendation Engine

> **[v3] Seção reescrita** após a leitura do *URACE RATE CARD 2026*. O portfólio real da URace não é uma lista homogênea de "programas" — são 7 famílias que atendem **compradores completamente diferentes**. Isso obriga um desenho em dois estágios.

### 21.1 O que o portfólio real revelou

As abas da planilha são: *Mechanic/Chassis/Engine · Services · Academy · Summer Camp · Racing team · Corporate Event · Sales - Chassis and Engine*.

Repare no problema: um lead de **Corporate Event** (empresa querendo um evento para 40 pessoas) e um lead de **Summer Camp** (mãe perguntando sobre o filho de 9 anos) não compartilham praticamente nenhum campo de qualificação. Perguntar "qual a idade do piloto?" para um comprador corporativo é absurdo — e perguntar "quantos participantes?" para a mãe também.

Um motor de estágio único (o desenho da v2) funcionaria, mas cada regra teria que reencodar "isto é um lead corporativo?" repetidamente, e a qualificação continuaria fazendo as mesmas perguntas para todo mundo. Por isso:

**Estágio 1 — Classificação de Segmento:** que *tipo de comprador* é este?
**Estágio 2 — Ranking de Ofertas:** dentro do segmento, qual oferta serve melhor?

O ganho não é só de organização: o **segmento define quais perguntas a Qualification Engine deve fazer** (`segments.required_fields`). O agente para de fazer perguntas irrelevantes, e o lead sente uma conversa que faz sentido.

### 21.2 Estágio 1 — Classificação de Segmento

Segmentos propostos (todos configuráveis, na tabela `segments`):

| Segmento | Quem é | Campos de qualificação exigidos |
|---|---|---|
| `corporate` | Empresa buscando evento/team building | empresa, nº de participantes, data pretendida, orçamento total |
| `youth` | Pai/mãe buscando atividade para criança/adolescente | idade do piloto, experiência, período pretendido, objetivo (lazer × competição) |
| `learner` | Adulto/iniciante querendo aprender ou evoluir | idade, experiência, objetivo, disponibilidade |
| `competitor` | Já compete, precisa de suporte em evento | categoria/classe, motor/chassi, qual evento e datas, tipo de suporte |
| `racing_team` | Quer entrar num programa competitivo completo | categoria, experiência, temporada pretendida, orçamento |
| `buyer` | Quer comprar chassi/motor | o que procura (chassi/motor), categoria, novo × usado, orçamento |

Como o segmento é determinado, em ordem de prioridade:
1. **Sinal explícito do lead** ("somos uma empresa", "meu filho de 9 anos", "corro na Rotax Mini") — a Qualification Engine extrai isso e o classificador confirma por regra determinística sobre os sinais extraídos.
2. **Origem do lead** — campanha, formulário ou anúncio de origem pode já indicar o segmento (mapeável em `configurations`).
3. **Pergunta direta** — se ainda ambíguo após 2 turnos, o agente pergunta de forma natural ("é para você ou para alguém da família?" / "é um evento para empresa?").

Enquanto `segment_confidence` for `low`, o agente **não recomenda nada** — segue coletando. Recomendar cedo demais no segmento errado é pior que não recomendar.

### 21.2-b [v5] Resultado `handoff`: metade do catálogo não é recomendável pelo agente

O documento **MODO OPERANTE (Parte 4)** define a regra mais importante da operação, e ela não é uma regra de recomendação — é de **roteamento**:

> Piloto que **já corre** (compete, tem categoria, cita tempos) → passa para o Italo. Piloto **iniciante ou recreativo** (indoor, K1, kart de aluguel) → fica com o agente.

Cruzando isso com o catálogo real, o efeito é grande: **6 dos 12 serviços nunca são recomendados pelo agente** — Race Team Support, Arrive & Drive, DIY Program, Mechanic Services, Engine Rental e Chassis Rental atendem exclusivamente `Competitive Drivers`, ou seja, exatamente o perfil que a regra manda encaminhar ao dono.

Isso obriga um terceiro valor de saída no motor, além de "recomendar" e "não tenho dados":

| `agent_action` | Comportamento |
|---|---|
| `recommend` | Agente recomenda e conduz a venda (Academy, Summer Camp, Lead & Follow, Corporate, Kart Rental) |
| `handoff_to_owner` | Agente **não recomenda nem precifica**: reconhece o perfil, coleta o telefone e gera o briefing para o Italo (seção 9 do MODO OPERANTE) |
| `faq_only` | Agente responde dúvidas, mas não oferta ativamente (Workshop Services) |

O campo vive no Catálogo (coluna `agent_action` na aba `_programs`), não no prompt — então a URace pode mover um serviço de `handoff` para `recommend` sem tocar em código, conforme ganhar confiança no agente.

**Consequência para o Estágio 1:** classificar o segmento deixa de ser só uma escolha de perguntas e passa a decidir *quem atende o lead*. Errar `competitor` como `learner` faz o agente tentar vender para alguém que deveria estar falando com o dono — por isso o MODO OPERANTE (4.2) insiste na desambiguação explícita: *"compete de verdade ou é mais por diversão?"*. Essa pergunta vira obrigatória no fluxo quando o sinal é ambíguo.

### 21.3 Estágio 2 — Ranking de Ofertas

Dentro do segmento identificado, dois níveis de filtro, nesta ordem:

**a) Elegibilidade dura — vem do Catálogo, não de regra.**
Se o programa tem `age_min=7` e o piloto tem 5 anos, ele é eliminado automaticamente. Idem `recommended_level`, `prerequisites` e `status='inactive'`. Isso é importante: **eliminação por elegibilidade não exige que ninguém escreva uma regra** — sai de graça dos campos que a equipe já preenche no Catálogo. Reduz muito o número de regras que a URace precisa manter.

**b) Preferência — aí sim vêm as `recommendation_rules`.**

| Tipo | Para que serve | Exemplo real |
|---|---|---|
| `match` | Recomendação direta forte | *SE segmento=youth + idade 8–12 + objetivo=competição + experiência=iniciante → Academy* |
| `boost` | Ajusta prioridade sem decidir | *SE país ≠ US → priorizar pacotes que incluem suporte completo (piloto de fora tende a precisar de estrutura no local)* |
| `exclude` | Remove candidato mesmo com pontos | *SE data pretendida fora da janela do Summer Camp → excluir Summer Camp* |

Exemplo de `match` armazenado em `recommendation_rules.conditions`:
```json
{
  "and": [
    { "field": "segment",     "operator": "equals",  "value": "youth" },
    { "field": "idade",       "operator": "between", "value": [8, 12] },
    { "field": "objetivo",    "operator": "equals",  "value": "competicao" },
    { "field": "experiencia", "operator": "equals",  "value": "iniciante" }
  ]
}
```
`target_program_id` = Academy · `score_impact = 50` · `explanation_template = "Indicado para pilotos de {age_min} a {age_max} anos que estão começando com foco em competição."`

Exemplo de `boost` (o caso "fora dos EUA" do pedido original):
```json
{ "and": [ { "field": "pais", "operator": "not_equals", "value": "US" } ] }
```
`target_category` = `race_support` · `score_impact = 15` · `explanation_template = "Estrutura completa no local, pensada para pilotos que viajam de fora."`

### 21.4 Algoritmo completo (determinístico)

1. Resolve o segmento (estágio 1). Se `confidence=low` → retorna `insufficient_data`, sem recomendar.
2. Carrega programas `active` **do segmento**.
3. Aplica elegibilidade dura (21.3a). Programas eliminados registram o motivo.
4. Inicializa cada candidato com seu `recommendation_priority` (peso base do Catálogo).
5. Avalia as `recommendation_rules` ativas em ordem de `priority_order`; soma/subtrai `score_impact` por alvo (`target_program_id` ou `target_category`).
6. Ordena por score final. Desempate: maior `recommendation_priority`, depois `display_order`.
7. `recommended_program_id` = topo · `alternatives` = próximos 1–2 dentro de margem configurável.
8. Seleciona as **ofertas** (`program_offers`) do programa vencedor que batem com o contexto do lead (ex.: `context='National Events'` se ele citou um evento nacional).
9. Calcula `confidence` (21.5).
10. Monta `justification` concatenando os `explanation_template` das regras que mais pesaram — **texto vindo de dado, não inventado pelo LLM**. O modelo apenas naturaliza a frase na resposta.
11. Grava tudo em `recommendation_log` antes de retornar: perfil usado, regras que dispararam, candidatos eliminados e por quê.

> **Catálogo incompleto (v4):** campo vazio no Catálogo significa **"não avalie esse critério"**, jamais um valor assumido. Programa sem `segment_slug` fica fora do estágio 1; programa sem `age_min`/`age_max` não é filtrado por idade; programa sem `description` não é descrito pelo agente. Detalhe em 23.3 — é o que permite o motor entrar no ar com a planilha preenchida pela metade.

### 21.5 Confiança — e o que fazer com cada nível

| Nível | Quando | Comportamento do agente |
|---|---|---|
| `high` | Uma regra `match` decidiu e a margem para o 2º é grande | Recomenda diretamente |
| `medium` | Só `boost`s acumulados, ou margem estreita | Apresenta como sugestão e oferece a alternativa ("dois caminhos fazem sentido pra você…") |
| `low` | Quase empate, ou faltam campos obrigatórios do segmento | **Não recomenda**; volta a qualificar ou escala |

Esse é o ponto que fecha o requisito "o agente nunca deve inventar recomendações": o caminho de baixa confiança tem um comportamento definido, então o modelo nunca fica na situação de "não sei, vou chutar algo plausível".

### 21.6 Preço na recomendação — cuidado específico da URace

O rate card traz ressalvas explícitas: *"Rate can vary +/- $50"*, *"o preço do aluguel de motor pode variar dependendo do preparador"*, *"motor reserva é 40% do valor do aluguel"*. Ou seja: **os preços da URace são indicativos por natureza**, não tabelados.

Por isso `program_offers` carrega `price_is_indicative` e `price_variance_note`, e o agente é instruído a apresentar sempre como faixa/referência sujeita a confirmação — nunca como valor fechado. Isso não é conservadorismo genérico: é o que a própria planilha da URace diz. Um agente que responde "são $600" a um lead que depois recebe $650 cria um problema comercial real.

Add-ons condicionais (motor reserva, dias extras) **não são calculados pelo agente**. Ele informa a existência e a regra ("o motor reserva é cobrado como um adicional"), e o fechamento do valor fica com a equipe.

### 21.7 Contrato

```
Input:  LeadProfile {
          segment?, idade, experiencia, objetivo, orcamento, disponibilidade,
          idioma, pais, categoria, evento_alvo, + segment_fields
        }

Output: RecommendationResult {
          segment,
          segment_confidence,
          recommended_program_id,
          matched_offers: [{ offer_id, price_amount, price_unit,
                             price_is_indicative, price_variance_note }],
          confidence: low | medium | high,
          justification: string,
          alternatives: [{ program_id, score }],
          excluded: [{ program_id, reason }]     // auditoria
        }
```

Quando `confidence=low` ou faltam campos obrigatórios do segmento, o retorno é
`{ status: "insufficient_data", missing_fields: [...] }` — e o agente usa isso para saber **qual pergunta fazer em seguida**. O motor de recomendação, na prática, também dirige a qualificação.

### 21.8 Três exemplos com o portfólio real

| Lead diz | Segmento | Caminho no motor |
|---|---|---|
| *"Meu filho tem 9 anos, nunca andou de kart, quer experimentar"* | `youth` | Elegibilidade filtra por idade → Academy e Summer Camp elegíveis → regra de sazonalidade decide (Summer Camp só se a data pretendida cai na janela) → confiança média, agente apresenta os dois |
| *"I race Rotax Mini, need a mechanic for the next national event"* | `competitor` | Programas de Race Support → oferta filtrada por `context='National Events'` → Exclusive Mechanic (indicativo $600/day, com ressalva de variação) + opção de aluguel de motor |
| *"Somos uma empresa de 40 pessoas, queremos um evento em Orlando"* | `corporate` | Nenhuma pergunta sobre idade/experiência é feita → campos do segmento: nº de participantes, data, orçamento → Corporate Event → alta confiança |

### 21.9 Garantia contra invenção
Estrutural, não apenas instrução de prompt: recomendar ou descrever um programa não é capacidade livre do LLM — é uma tool (`get_program_recommendation` / `get_program_details`) que devolve exclusivamente o que o motor calculou a partir do Catálogo e das regras. O master prompt (6.1) reforça proibindo mencionar programa ou preço sem chamada da tool no mesmo turno; e o caminho `insufficient_data` garante que "não tenho dados suficientes" seja uma resposta *prevista*, não uma falha.

### 21.10 Simulador
Igual ao descrito em 22.3, mas agora com dois estágios visíveis: o admin monta um perfil de teste e vê **o segmento classificado**, os candidatos eliminados por elegibilidade (com motivo), o ranking com os pontos de cada regra e a justificativa final. É a ferramenta que permite a alguém não técnico validar uma regra antes de publicar.

---

## 22. Painel Administrativo (Admin Panel)

### 22.1 Escopo e tabelas por trás de cada tela

| Área do Admin Panel | Tabela(s) por trás | Validações mínimas na gravação |
|---|---|---|
| Programas | `programs`, `program_faq` | `slug` único; `age_min ≤ age_max`; `status` obrigatório |
| Categorias | `programs.category` (lista controlada em `configurations`) | categoria não pode ser removida se houver programa ativo usando-a |
| Regras de recomendação | `recommendation_rules` | ao menos 1 condição; `target_program_id` ou `target_category` preenchido; simulação recomendada antes de publicar (22.3) |
| FAQ (geral) | `knowledge_documents` (`category='faq_geral'`) | — |
| Horários | `configurations` (`business_hours`) | intervalos coerentes (abertura < fechamento) |
| Templates de mensagens | `configurations` (`message_templates`) | placeholders obrigatórios presentes (ex. `{nome_lead}`) |
| Lead Scoring | `configurations` (`scoring_rules`) | soma dos pesos = 100 (ou aviso se não bater) |
| Follow-ups | `configurations` (`follow_up`) | número de tentativas ≥ 1; intervalos crescentes |
| Critérios de escalonamento | `configurations` (`escalation_keywords`) | — |
| Pipeline Mapping | `configurations` (`pipeline_mapping`) | `field_id`/`status_id`/`pipeline_id` no formato esperado pela API do Kommo |
| Campos do Kommo | `configurations` (`pipeline_mapping`) | idem |

### 22.2 Controle de acesso
Perfis de permissão (ex. Admin / Editor / Leitura) — quem pode só ver, quem pode editar conteúdo (Programas, FAQ) e quem pode editar regras mais sensíveis (Scoring, Recomendação, Pipeline Mapping). Toda alteração é atribuída a um usuário específico em `audit_logs.actor`, reaproveitando a infraestrutura de auditoria que já existe (seção 12) — não é preciso criar uma tabela de log separada para o Admin Panel.

### 22.3 Simulação antes de publicar (regras de recomendação)
Por serem a área mais sensível a erro de configuração (uma regra mal escrita pode direcionar todos os leads para o programa errado), a tela de regras de recomendação inclui um **simulador**: o usuário monta um perfil de teste (idade, objetivo, experiência etc.) e vê imediatamente qual programa seria recomendado e por quê, antes de a regra entrar em produção. Isso não é só uma conveniência de UX — é o que torna seguro delegar essa configuração a alguém não técnico.

### 22.4 Publicação
Mudanças em Programas, Horários, Templates e Lead Scoring entram em vigor imediatamente após salvar (são dados, não lógica nova). Regras de recomendação, por serem mais sensíveis, podem seguir um fluxo rascunho → simulação → publicação (decisão em aberto #8 — se isso é obrigatório desde o início ou uma evolução).

---

## 23. Ingestão do Catálogo via Google Sheets

### 23.1 Papel da planilha na arquitetura
Decisão da URace: a planilha é a fonte de verdade de preços, programas, serviços e informações comerciais variáveis. Na prática isso significa que **a planilha é o Admin Panel do Catálogo** — a equipe já sabe usá-la, não precisa de treinamento, e o requisito "atualizar sem alterar código" é atendido de imediato.

Consequência positiva: o escopo do Admin Panel (seção 22) **encolhe** — ele passa a cobrir só Configuração (scoring, follow-ups, escalonamento, templates, regras de recomendação, pipeline mapping), enquanto o Catálogo vive na planilha. Menos software para construir no MVP.

Consequência a administrar: a planilha é fonte de verdade, mas **não é o banco operacional**. O agente nunca consulta a planilha durante uma conversa — ele consulta `programs`/`program_offers`, que são sincronizados a partir dela. Isso protege a latência da conversa e a estabilidade do agente contra a planilha estar sendo editada naquele instante.

```
Google Sheets  ──(sync agendado + botão "Sincronizar agora")──►  Staging + validação
                                                                        │
                                                    ┌───────────────────┴──────────────┐
                                                    │ linhas válidas          linhas   │
                                                    ▼                        inválidas ▼
                                          programs / program_offers      relatório de erros
                                                    │                     (não derruba o resto)
                                                    ▼
                                        reindexação da Base de Conhecimento (19.2)
```

### 23.2 Problema real: o rate card atual não é ingerível de forma estável

O *URACE RATE CARD 2026* é um documento comercial bonito e formatado para humanos. Isso é ótimo para enviar a um cliente — e ruim para um parser:

| O que existe hoje | Por que quebra a ingestão |
|---|---|
| Título e endereço nas linhas 1–2, cabeçalho na linha 3 | O cabeçalho não está na primeira linha; qualquer inserção de linha desloca tudo |
| Preços como texto: `$350/day`, `300/day` (sem `$`), `$1200/ 4 days`, `$1,250/event` | Formatos inconsistentes; exigem parsing frágil de string |
| Notas de rodapé em célula mesclada (linha 29) e marcadores `**` nos nomes | Regras de negócio importantes ficam presas em texto livre |
| `Shared Mechanic` (linha 4) vs `Share Mechanic` (linha 7) | Provável mesmo serviço com dois nomes → viram dois registros distintos no banco |
| Colunas sem cabeçalho (a coluna de preço, coluna E, não tem título) | Impossível mapear por nome de coluna |

**Recomendação:** manter o rate card como está (é o documento comercial da empresa) e adicionar **abas normalizadas** que o sync lê — por exemplo `_programs` e `_offers` — com cabeçalho fixo na primeira linha e uma coluna por campo. A equipe continua editando no Sheets (requisito atendido), mas o sync lê um formato-contrato em vez de adivinhar layout.

A alternativa (parser específico por aba, tolerante ao layout atual) é viável, mas cria uma dependência frágil: qualquer reformatação estética feita por alguém da equipe quebra a ingestão silenciosamente. Se essa alternativa for escolhida, o sync **precisa** falhar de forma visível e alertar, nunca sincronizar dados parciais em silêncio.

### 23.3 Preenchimento progressivo: o catálogo nasce incompleto (por decisão)

O rate card traz **serviço, contexto, descrição e preço**. O Recommendation Engine (seção 21) também precisa de faixa etária, nível recomendado, objetivo, pré-requisitos, palavras-chave e segmento — campos que hoje não existem em lugar nenhum.

**Decisão da URace:** esses campos entram como colunas novas na planilha e serão preenchidos pela equipe **depois**, aos poucos. Tudo num lugar só, sem tela extra para manter.

Isso transforma um problema de dados num **requisito de arquitetura**: o sistema precisa operar corretamente com o catálogo pela metade, desde o primeiro dia, sem quebrar e — mais importante — **sem preencher lacuna com suposição**. A regra é degradação segura: campo vazio significa "não avalie esse critério", nunca "assuma um valor razoável".

| Campo vazio | Comportamento do sistema |
|---|---|
| `age_min` / `age_max` | Programa **não é filtrado por idade** — permanece elegível para qualquer lead. Nunca inferir faixa a partir do nome do programa |
| `segment_slug` | Programa **fica fora da recomendação automática**. Continua respondendo a perguntas diretas via RAG/Catálogo, mas o motor não o sugere |
| `recommended_level` | Não é filtrado por experiência |
| `keywords` | Reconhecimento por texto livre fica mais fraco; o agente pergunta em vez de adivinhar |
| `description` / `benefits` | O agente **não descreve o programa** — informa que vai confirmar e escala. Nunca gera uma descrição plausível |
| `price_amount` | Nunca estima preço. Escala (regra da seção 11) |

Consequência prática no rollout: com a planilha só normalizada (preços) e os campos de recomendação ainda vazios, o agente já entrega valor — responde preço, tira dúvidas, qualifica e agenda. Conforme a equipe preenche segmento, idade e nível, a recomendação automática vai ligando programa por programa. **Não existe um "big bang" onde tudo precisa estar pronto para o sistema funcionar.**

Para isso não virar uma lacuna silenciosa, duas salvaguardas:
- **Painel de completude:** o Admin Panel mostra, por programa, quais campos faltam e o que isso está bloqueando (ex.: *"Summer Camp: sem `age_min` — não pode ser filtrado por idade"*). Torna visível o custo de deixar em branco.
- **Métrica de cobertura:** percentual de programas aptos a entrar na recomendação automática, acompanhado junto às métricas da seção 14.

### 23.3.1 Template da planilha

O arquivo `urace-catalogo-template.xlsx` acompanha este documento com as três abas já montadas (`_segments`, `_programs`, `_offers`), cabeçalhos definidos, legenda de preenchimento e **as 25 linhas do rate card já normalizadas** (aba *Mechanic/Chassis/Engine*, linhas 4–28). As colunas de recomendação estão criadas e vazias, marcadas em amarelo.

Duas inconsistências encontradas na normalização, sinalizadas na própria planilha para a equipe confirmar:
- `Shared Mechanic` (linha 4) vs `Share Mechanic` (linha 7) — provavelmente o mesmo serviço com dois nomes.
- Linha 24 (`300/day`) sem o símbolo `$`, ao contrário de todas as outras.

As ofertas das outras 6 abas (*Services, Academy, Summer Camp, Racing team, Corporate Event, Sales*) ainda precisam ser adicionadas ao template — é o que os materiais de apoio do projeto vão permitir completar.

### 23.4 Mecânica do sync

- **Leitura:** Google Sheets API com service account em modo leitura (a planilha já está compartilhada como "view only").
- **Gatilho:** agendado (ex.: a cada 15 min) + botão manual "Sincronizar agora" no Admin Panel, para quando a equipe quiser refletir uma mudança imediatamente.
- **Validação antes de aplicar:** cada linha passa por checagem de schema (preço numérico, unidade reconhecida, `age_min ≤ age_max`, segmento existente). Linha inválida é **rejeitada individualmente** e reportada — nunca derruba o catálogo inteiro por causa de uma célula malformada.
- **Diff e aplicação:** upsert por chave estável (`slug` do programa / `source_sheet_row` da oferta). Item que sumiu da planilha vira `status='inactive'`, **nunca é apagado** — preserva integridade com `qualification_data`, `recommendation_log` e `appointments` históricos (regra da seção 20.2).
- **Pós-sync:** dispara a reindexação da Base de Conhecimento apenas para o que mudou (seção 19.2).
- **Auditoria:** cada execução grava em `catalog_sync_runs` (lidas / aplicadas / rejeitadas + diff + erros). Se um lead receber uma informação errada, dá para rastrear qual versão do catálogo estava ativa naquele momento.
- **Falha de leitura:** se a planilha estiver inacessível, o sistema continua operando com o último catálogo válido em banco e alerta a equipe — o agente nunca fica sem catálogo.

### 23.5 Preço: como o agente deve falar

Regra derivada diretamente do que a URace escreveu na própria planilha:
- Preço é apresentado como **referência sujeita a confirmação**, acompanhado da ressalva do rate card quando existir (`price_variance_note`).
- Cálculos condicionais (motor reserva a 40%, dias adicionais, pacotes) **não são feitos pelo agente** — ele informa que o adicional existe e a equipe fecha o valor.
- Se a oferta pedida não existir no catálogo sincronizado, o agente **não estima**: escala (seção 11).

---

## 24. Portão de aprovação humana por idade e porte

Regra confirmada pela URace: **atendimento a partir de 4 anos; a pista permite 5+; abaixo disso e em casos limítrofes, a liberação depende do tamanho da criança e da experiência — sempre avaliada por um humano.**

Isso não é uma exceção a tratar no prompt: é um **portão estrutural**, e ele reaproveita o mesmo mecanismo já criado para agendamento fora do expediente (`pending_human_approval`, seção 9).

### 24.1 Comportamento
Quando `idade_piloto < programs.human_approval_below_age` (ou a idade está próxima do limite), o agente:

1. **Não confirma e não recusa.** Nenhum dos dois é decisão dele.
2. Pergunta a experiência da criança — informação que o avaliador humano precisa.
3. Registra a solicitação e cria uma **Task de aprovação no Kommo**, com idade, experiência e o que o responsável disse.
4. Informa ao lead, com naturalidade, que a equipe confirma a liberação — porque depende do porte da criança, avaliado caso a caso.
5. Só após aprovação humana o fluxo de reserva/agendamento continua.

### 24.2 Por que o campo é `human_approval_below_age`, e não um `age_min` rígido
Um `age_min = 5` faria o agente **recusar** uma criança de 4 anos — o que contraria a operação (a URace atende a partir de 4). Um `age_min = 4` faria o agente **confirmar** livremente — o que contraria a pista. Nenhum dos dois representa a realidade, que é: *"depende, e quem decide é uma pessoa"*.

O campo separado permite exatamente isso: `age_min = 4` (atende), `human_approval_below_age = 5` (abaixo disso, humano decide). É configurável por programa na planilha, então se a regra da pista mudar, é uma célula.

### 24.3 Nunca inverter o portão
A tentação natural do modelo, diante de um pai animado, é dizer "sim, pode trazer". O master prompt precisa ser explícito: **abaixo do limite, "a equipe confirma" é a única resposta possível** — não existe caminho em que o agente libere sozinho. Isso é segurança de criança, não política comercial.

---

## 25. Fechamento: ligação com o Italo × fechamento por chat

Regra final da URace — **não é o score que decide, é o perfil de compromisso**:

```
Lead qualificado
      │
      ▼
É de Orlando (local) E quer compromisso recorrente
(treinar várias vezes por mês, mensalidade, contrato)?
      │
   ┌──┴───┐
  SIM     NÃO (quer só um dia / baixo compromisso)
   │       │
   ▼       ▼
AGENDA    FECHA POR CHAT
LIGAÇÃO   (1-Day, Lead & Follow, camp avulso)
   │       │
   ▼       ▼
Passa para o Italo        Gera Task para um humano
(briefing, seção 9         concluir o fechamento
 do MODO OPERANTE)         (pagamento/reserva)
```

Dois pontos que valem destaque:

**A ligação não é o objetivo universal.** Ela existe para o lead local de alto compromisso — que é conversa do dono. Para quem quer um dia, insistir em ligação adiciona atrito num negócio que fecha por chat. Isso reconcilia o briefing original com o MODO OPERANTE 4.1: ambos estavam certos, para casos diferentes.

**Nenhum fechamento é 100% automático.** Mesmo no caminho de chat, o agente conduz até o ponto de pagamento e **gera Task para um humano concluir**. Isso já estava previsto no MODO OPERANTE 8.2 ("só com aprovação humana no passo de dinheiro") e agora é regra de arquitetura: o agente nunca processa pagamento sozinho.

### 25.1 Janela de agendamento (quando há ligação)
O horário tem que estar **simultaneamente** dentro de:
- o horário de atendimento da equipe (Seg–Sex 09:00–18:00 · Sáb–Dom 08:00–12:00, `America/New_York`), com preferência por Seg–Sex; **e**
- a janela em que o **lead** consegue atender — que o agente pergunta, não presume.

Interseção vazia → não força horário: registra a preferência e cai em `pending_human_approval`.

### 25.2 Dados obrigatórios antes de agendar

| Campo | Observação |
|---|---|
| Nome do responsável | quando o piloto é menor |
| Nome do piloto | |
| Idade do piloto | dispara o portão da seção 24 quando aplicável |
| Onde moram | **decide o roteamento acima** (local × traveler) |
| Telefone | pode vir do canal (WhatsApp) ou precisa ser pedido (Instagram, TikTok, Messenger, e-mail) |
| Janela de disponibilidade para a ligação | seção 25.1 |

Faltando qualquer um, o agente **continua qualificando** em vez de agendar — mesmo mecanismo `insufficient_data` do Recommendation Engine (21.7).

### 25.3 Divergências a corrigir nos documentos de operação
Três textos ficaram desatualizados frente às decisões tomadas. Como esses documentos treinam **pessoas**, não só o agente, vale corrigi-los para não haver duas regras em vigor:

| Documento | O que corrigir |
|---|---|
| Playbook, Seção 0 | *"Summer Camp: direcionar EXCLUSIVAMENTE para travelers"* → o camp é para qualquer cliente que perguntar; traveler é preferência, não exclusão |
| Playbook, Seção 5 | *"ofereça para first timers only, por $500"* → esse valor não existe no rate card; o agente fecha somente a $769 |
| MODO OPERANTE, 4.1 | *"não ofereça ligação para iniciante"* → precisa refletir o critério real (local + compromisso recorrente), não o nível de experiência |

---

## 25-A. Política de preço: quando revelar, e qual valor

Regra da URace, em duas camadas que atuam juntas.

### 25-A.1 Camada 1 — O agente não oferece preço; ele responde preço

Por padrão o agente **não menciona valores**. Não abre com preço, não anexa preço a uma explicação, e nunca despeja a tabela. O preço só aparece quando o lead **pergunta e está genuinamente interessado** — e aí precedido de enquadramento de valor, como o Playbook (Seções 4 e 12) já orienta o time humano a fazer.

Isso é o oposto do comportamento natural de um assistente, que tende a ser "útil" antecipando informação. Precisa ser regra explícita no master prompt, porque despejar preço cedo é exatamente o anti-padrão que o MODO OPERANTE (1.3) identifica como o que mais queima lead: *"lead faz uma pergunta simples → agente responde com três blocos de programas e preços → lead nunca mais responde."*

**O portão para revelar preço:**

| Condição | Detalhe |
|---|---|
| 1. O lead pediu explicitamente | Não vale "pareceu interessado" — tem que ter perguntado |
| 2. A qualificação mínima está feita | Experiência + origem (local × traveler), as duas obrigatórias do MODO OPERANTE 3.1 |
| 3. Um valor por vez | Só o item perguntado. Nunca a tabela, nunca "e também temos…" |
| 4. Enquadramento antes do número | Valor primeiro, preço depois — não o contrário |
| 5. Ressalva das track fees | Nunca "all-inclusive": driver pass e pit pass são pagos direto ao OKC |

**Um cuidado importante:** se o lead abre perguntando o preço, o agente **não pode se recusar a responder**. Ele faz as duas perguntas de qualificação e **em seguida responde** — segurar o preço como moeda de troca irrita e derruba a conversa. O MODO OPERANTE 3.1 é claro: qualifica primeiro, mas responde.

### 25-A.2 Camada 2 — Nem todo preço que existe é cotável

Segunda regra, independente da primeira: o agente fecha Lead & Follow **somente a $769**. Os valores de last minute ($395 para 1 piloto, $245 por piloto para 2) existem de verdade, mas são exclusivos do **operador na pista** — como o próprio rate card diz (*"last-minute deals can only be offered by the operator at the track"*).

Isso é a coluna `agent_can_quote` na aba `_offers`:

| Valor | Significado |
|---|---|
| `TRUE` | O agente **pode** apresentar este valor — quando o portão de 25-A.1 for satisfeito |
| `FALSE` | O valor existe no catálogo (o agente o conhece e não se confunde), mas **nunca sai da boca dele** |

Por que não apagar essas ofertas do catálogo: se o lead disser *"me falaram de $395"*, o agente precisa **entender** do que se trata para não contradizer a equipe nem tratar o cliente como enganado — mas segue sem poder oferecer aquele valor. Omitir criaria ponto cego; marcar resolve os dois lados.

### 25-A.3 Preço nunca é memorizado
Todo valor é lido do catálogo sincronizado no momento da resposta — nunca do prompt, nunca da memória do modelo. A URace ajusta o preço na planilha e o agente passa a usar o novo valor no próximo sync, sem deploy e sem retreino. É o que torna a regra "preço é dado, não código" real na prática.

### 25-A.4 O que destrava o preço: a qualificação completa

Definido pela URace. **Não há limiar de score** — o que libera o preço é ter feito a qualificação, que é sempre obrigatória:

| Pergunta | Por que existe |
|---|---|
| É para você ou para outra pessoa? | Define se fala com o piloto ou com o responsável |
| Idade do piloto | Elegibilidade e portão de aprovação (seção 24) |
| De onde a pessoa é | Local × traveler — decide recomendação e roteamento (seção 25) |
| Contato | Pedido quando impacta o atendimento |
| Qual o objetivo no kart | Diversão × desenvolvimento — decide 1-Day × Academy |

Feito isso, se o lead pergunta o preço, o agente responde. Sem score mínimo, sem etapa extra.

**O enquadramento que a URace usa para isso: é um namoro, não um formulário.** As perguntas existem para cativar e entender o que a pessoa realmente quer — e só então recomendar o serviço certo. Isso tem consequência direta no prompt: as cinco perguntas **não podem virar um questionário disparado de uma vez**. Uma por mensagem, no fluxo da conversa, como o MODO OPERANTE (regra 1b e 3.3) já determina. Um lead que responde cinco perguntas seguidas se sente processado; um lead que conversa se abre — e a diferença entre as duas coisas é exatamente o que separa este agente de um chatbot de formulário.

Consequência prática: a qualificação **não é um pedágio antes do atendimento**, é o atendimento. O agente responde as dúvidas do lead enquanto pergunta, nunca segurando informação como moeda de troca.

---

## 26. Enriquecimento de perfil — desenho best-effort

Decisão da URace: tentar o enriquecimento a partir do nome e do link de perfil que o Kommo já traz, com retorno padrão **"impossível de analisar"** quando não der.

### 26.1 Nome pelo canal — direto
O Kommo entrega nome/handle do contato no webhook, por canal. Entra em `leads.name` sem integração adicional. Duas regras que o MODO OPERANTE já traz e valem aqui: se o perfil só tem apelido, iniciais ou nome de empresa, o agente **pede o primeiro nome** em vez de usar o handle (regra 7); e **não deduzir idioma pelo nome** — "Juliana" escrevendo em inglês é atendida em inglês (regra 6).

### 26.2 Pesquisa de perfil — o que realmente é possível

| Fonte | Viabilidade real |
|---|---|
| Handle/link que o Kommo já entrega | ✅ Disponível |
| Perfil público de empresa (segmento `corporate`) | ✅ Viável e confiável — informação pública de negócio |
| Página de Instagram/TikTok do lead | ⚠️ Majoritariamente inacessível de forma programática (login-wall) e sujeito aos termos de uso das plataformas |
| Busca do nome na web aberta | ⚠️ Funciona, mas **erra de pessoa com frequência** — nomes comuns retornam homônimos |

Por isso o retorno padrão do módulo é `not_possible`. Não é um caso de erro: na maior parte das vezes será o resultado correto e honesto.

```
ProfileEnrichmentResult {
  status: "analyzed" | "not_possible",
  confidence: low | medium | high,
  signals: [...],          // só sinais objetivos e verificáveis
  source: "...",           // de onde veio cada sinal
  note: "impossível de analisar"   // quando status = not_possible
}
```

### 26.3 Três salvaguardas que precisam estar no desenho

**1. Nunca rebaixa atendimento.** O resultado pode *elevar* prioridade de um lead, nunca reduzir. Um lead sem perfil encontrável é atendido exatamente igual a um lead com perfil rico. Isso não é só uma questão de justiça — é a proteção comercial contra o erro caro: pai que investe $3.000/mês em Academy frequentemente tem perfil discreto ou inexistente.

**2. Enriquece o briefing humano, não decide sozinho.** O resultado entra no briefing do Italo (seção 9 do MODO OPERANTE) como contexto para uma pessoa avaliar — não vira um número que o agente usa para mudar o tom da conversa.

**3. Só sinais objetivos.** Cargo, empresa, cidade — dados profissionais públicos. Nunca inferência a partir de foto, aparência, sobrenome, bairro ou estilo de vida: além de impreciso, é o caminho que acidentalmente transforma característica pessoal em critério de atendimento.

### 26.4 O sinal mais forte continua vindo da conversa
Vale registrar, porque é onde está o retorno real: os melhores indicadores de capacidade de investimento aparecem no diálogo, não no perfil — perguntar por mensalidade ou contrato em vez do dia avulso, viajar de outro estado para treinar, já ter kart próprio, perguntar sobre campeonato, e não reagir ao valor quando o preço é apresentado.

Esses sinais são precisos, auditáveis em `criteria_breakdown`, configuráveis pela equipe e não dependem de integração nenhuma. O enriquecimento externo é complemento; o Lead Score da conversa é o motor principal.

---

*Estado atual: os 8 conflitos entre documentos estão resolvidos e o catálogo está estruturado (13 programas, 113 ofertas). O caminho está livre para desenhar as regras concretas de recomendação de 1-Day, Academy, Summer Camp e Lead & Follow — os quatro programas em que o agente atua sozinho. Pendente apenas: preencher benefícios e diferenciais na planilha, e a definição de calendário único × por vendedor (item 14).*
