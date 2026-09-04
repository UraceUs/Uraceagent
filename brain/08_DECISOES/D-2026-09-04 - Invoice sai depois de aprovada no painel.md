---
tipo: decisao
tipo_info: DECISION
data: 2026-09-04
fonte: Italo Silveira
responsavel: Italo Silveira
status: ativo
---

# Invoice sai depois de aprovada no painel

## O que foi decidido

A IA **pode enviar a invoice depois que um humano aprovar** no
Command Center. Política da ação `enviar invoice`: **REQUIRES APPROVAL**.
Nunca automática, nunca sem registro de quem aprovou.

## O que isso substitui

A regra de 28/08 — *"a IA NÃO ENVIA a invoice; humano envia pelo
QuickBooks"* — valia num mundo sem tela de aprovação. Com o painel, a
aprovação vira um clique auditado, e o envio passa a ser da IA **depois**
desse clique. O que não muda: a IA continua sem enviar nada por conta
própria. Ver [[PARAMETROS]].

## Como o sistema garante

- A ação existe na política como `REQUIRES_APPROVAL`; o backend recusa
  execução sem um registro em `approvals` com `approved_by`.
- Cada envio grava em `audit_logs`: o quê, por quê, sistema, valor, quem
  aprovou.
- `APLICAR=0` no VPS continua valendo para as rotinas: a aprovação no
  painel é o caminho, não um atalho.

## Quem decidiu

Italo Silveira, 04/09/2026: *"pode enviar a invoice depois de aprovada"*.

## Relacionado

[[Invoice e estimate no QuickBooks]] · [[QuickBooks]] · [[Decisoes]] ·
[[Escalonamento]] · [[2026-09-04]]
