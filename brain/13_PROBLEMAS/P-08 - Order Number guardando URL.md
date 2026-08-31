---
tipo: problema
tipo_info: FACT
data: 2026-08-31
fonte: docs/adminai/mapa-asana-4-projetos.md
responsavel: Italo Silveira
status: ativo
---

# P-08 — Campos de rastreio guardando link em vez de código

[[Asana]] · [[Compra e envio]] · [[Problemas]]

## O problema
No **Shipping Orders** do [[Asana]], o campo `Order Number` guarda URL gigante do Alibaba e o `Tracking Number` guarda link de portal, em vez do código de rastreio.

## Evidência
Mapa dos 4 projetos do Asana, lido em 28/08/2026.

## Impacto
Quebra qualquer rastreio automático — não dá para consultar transportadora com uma URL.

## O que fazer
Ao tocar numa dessas tarefas, extrair o código e pôr no campo certo, guardando o link na descrição. Não é migração em massa: é higiene ao passar.

## Fonte
docs/adminai/mapa-asana-4-projetos.md
