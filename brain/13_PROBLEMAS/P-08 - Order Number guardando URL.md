---
tipo: problema
tipo_info: FACT
data: 2026-08-31
fonte: docs/adminai/mapa-asana-4-projetos.md
responsavel: Italo Silveira
status: ativo
---

# P-08 — Campos de rastreio guardando link em vez de código

> **Direção do dono (18/09):** a IA pode **extrair o código do link** e gravar no campo certo, em vez de alguém copiar à mão.

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

## Decisão do dono — 06/10/2026

- **Código no campo, link na descrição** (opção "a"). Substitui o "sempre link" de 28/08.
- **Corrigir tudo de uma vez, com a lista aprovada antes.**
- Levantamento de 06/10: são 36 campos com link em 31 tarefas do Shipping Orders. Em 14 o código sai com certeza (UPS, DHL, eBay, YunExpress). Os outros 22 são links da Amazon, páginas de loja, Newegg, Etsy e kartshop, que não trazem código: o campo fica vazio e o link vai para a descrição.
- Tarefas concluídas, canceladas ou reembolsadas não são mexidas.
- Regra atualizada em `skills/urace-asana/SKILL.md` e `docs/adminai/app-gmail-triagem.md`.
