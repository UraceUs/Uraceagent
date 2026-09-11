---
type: system
category: retrieval
topic: regras-de-retrieval
priority: high
status: active
source: internal
last_updated: 2026-08-25
tags: [sistema, retrieval, contexto]
---

# Regras de Retrieval — como o conhecimento chega ao Chase

## As duas vias

1. **Injeção automática por turno**: a ponte busca no índice os trechos
   mais relevantes para a mensagem do lead e os injeta como contexto
   `[SYSTEM]` antes do Chase responder. O lead nunca vê isso.
2. **Diretiva `[[kb query="..."]]`**: o próprio Chase pede conhecimento
   quando percebe que precisa (ex.: objeção que ele não sabe responder).
   A ponte busca e devolve numa segunda rodada — mesmo mecanismo já usado
   pelo `[[price]]`. Como o conteúdo do Brain é em português, o Chase é
   instruído a montar a query em português.

## A ordem das camadas de contexto (montada pela ponte)

1. Instruções fixas (AGENTS.md do workspace — identidade, regras, voz)
2. Histórico da conversa (sessão OpenClaw por lead)
3. Memória do lead (qualificação A/B/C/D, origem, idade, estado — SQLite)
4. Conhecimento relevante do Brain (top 3 trechos, aprovados)
5. A mensagem do lead (a tarefa do turno)

## Orçamentos e filtros (impostos pela ponte, não negociáveis pelo modelo)

- Top **3** documentos por busca, ~1.200 caracteres por trecho, ~3.500 no
  total — nunca o vault inteiro.
- Só `status: approved` ou `active`. Candidatos e em revisão são
  invisíveis.
- Ranqueamento: status → priority → recência → relevância (BM25).
- Toda busca é logada (query, documentos, scores, tempo) na auditoria da
  ponte — kind `brain`.

## O que o retrieval NUNCA entrega

Preço em número, links de página, horários, disponibilidade — dados
voláteis vivem em `config/*.json` e chegam por diretiva com portão
(G1/G8). Se um documento do Brain violar isso, é bug de conteúdo:
corrigir o documento, não abrir exceção no código.
