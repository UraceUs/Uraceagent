---
type: system
category: dashboard
topic: painel-principal
priority: high
status: active
source: internal
last_updated: 2026-08-25
tags: [painel, indice]
---

# Painel do Sales Brain

> Abra esta nota primeiro. Ela é o índice humano do que o Chase sabe.

## ⚠️ Aguardando revisão (agir aqui)

- [[2026-08-25 - Summer Camp vs Training Camp]] — `review_required` —
  decisão de nomenclatura do Italo
- *(novos candidatos do learning loop diário aparecem em `09_LEARNINGS/`
  com `status: candidate` — promova para `approved` para o agente usar)*

## Conhecimento ativo

**Sistema**
- [[Instrucoes do Agente]] — ponteiro para as instruções canônicas
- [[Regras de Retrieval]] — como o conhecimento chega ao Chase

**Empresa**
- [[Visao Geral URACE]] — posicionamento, quem é quem
- [[Politicas Comerciais]] — taxas da pista, depósito, cancelamento, descontos, pagamento

**Vendas**
- [[Qualificacao]] — classificação A/B/C/D, roteamento, as 2 perguntas
- [[Objecoes]] — playbook: preço, segurança, cônjuge, hardship
- [[Follow-ups]] — as 3 trilhas e como escrever cada toque

**Produtos**
- [[Programas]] — posicionamento dos 4 programas + elegibilidade por idade

**Conhecimento operacional**
- [[Pista e Check-in]] — OKC, passes, horários, dicas

**Aprendizados aprovados**
- [[2026-08-24 - Leads pedem preco antes da classificacao]]

## Como este vault funciona

Regras completas, schema de frontmatter e ciclo de vida
(candidate → approved): [[README|_meta/README]].

Pastas que ainda não existem (08_CASES, 10_PROMPTS, 99_ARCHIVE) são
criadas quando o primeiro conteúdo real delas surgir — pasta vazia não
carrega informação.

## Fontes da verdade que NÃO vivem aqui (de propósito)

| Dado | Onde vive | Como chega ao agente |
|---|---|---|
| Preços | `salesagent/config/ratecard-2026.json` | diretiva `[[price]]` (portão G1) |
| Links de programa | `salesagent/config/program-links.json` | idem |
| Comportamento/voz do Chase | `salesagent/instructions/urace-sales-agent.md` | sync para o workspace do agente |
| Memória por lead | SQLite da ponte + sessões OpenClaw | automático, por conversa |
| Decisões de projeto | `salesagent/CONSOLIDACAO.md` | leitura humana |
