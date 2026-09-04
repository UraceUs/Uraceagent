---
tipo: problema
tipo_info: FACT
data: 2026-08-31
fonte: docs/adminai/diagnostico-servicos-agosto-2026.md
responsavel: Italo Silveira
status: ativo
---

# P-05 — O security deposit quase não é cobrado

[[Security deposit]] · [[QuickBooks]] · [[Problemas]]

## O problema
Em **31 serviços recentes, o depósito aparece em 1**.

## Evidência
Diagnóstico dos serviços de agosto/2026, cruzado com o [[QuickBooks]].

## Impacto
O depósito existe justamente para cobrir dano. Não cobrado, a URACE fica exposta — e a subtarefa "Security Deposit sent?" fica mentindo no quadro.

## O que fazer
É um dos motivos de a IA ter sido autorizada a **enviar a invoice do depósito** sozinha ([[D-2026-08-28 - IA envia a invoice do deposito]]). Cobrar sempre conferindo a regra de [[Pagamento e security deposit]]: **um por cliente, enquanto retido**.

## Fonte
docs/adminai/diagnostico-servicos-agosto-2026.md
