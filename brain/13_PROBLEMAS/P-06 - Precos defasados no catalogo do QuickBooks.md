---
tipo: problema
tipo_info: FACT
data: 2026-08-31
fonte: qbo_catalog_search_products + Rate Card, 31/08/2026
responsavel: Italo Silveira
status: ativo
---

# P-06 — Catálogo do QuickBooks com preço defasado

> **Direção do dono (18/09):** atualizar o catálogo **pela Rate Card** no que existir lá; para item sem Rate Card, usar o valor das **últimas invoices** do mesmo serviço. Como são 896 itens, a atualização vai por lista revisada antes de aplicar.

[[QuickBooks]] · [[Rate Card]] · [[Problemas]]

## O problema
O catálogo do [[QuickBooks]] tem **896 itens**, dos quais só ~25 faturam de verdade, e os preços estão desatualizados em relação à [[Rate Card]].

## Evidência
Sondagem do catálogo + comparação com a planilha, 31/08/2026.

## Impacto
Faturar pelo catálogo cobra o valor errado. Foi o que motivou a ordem de precedência de preço.

## O que fazer
A [[Rate Card]] manda ([[D-2026-08-31 - Rate Card acima do catalogo do QuickBooks]]). Atualização em massa só por CSV, com "sobrescrever por match exato de nome" marcado — sem isso o QBO **duplica** o item.

## Fonte
qbo_catalog_search_products + Rate Card, 31/08/2026
