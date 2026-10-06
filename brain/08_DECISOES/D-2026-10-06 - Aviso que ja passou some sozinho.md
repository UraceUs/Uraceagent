---
tipo: decisao
tipo_info: DECISION
data: 2026-10-06
fonte: [[Administrative AI]]
responsavel: O que o quadro "Precisa de atenção" mostra quando a data já passou.
status: ativo
---

# D-2026-10-06 — Aviso cuja data já passou some sozinho do "Precisa de atenção"

issue #94, 06/10/2026

## O que foi decidido
Dono: *"se algo passou já — venceu no dia 26, 27 — esses aí já oculta automaticamente.
Os futuros ficam ali mostrando."*

- **Some sozinho:** tarefa vencida (coluna de dia que já passou, ainda aberta) e waiver que
  já expirou.
- **Continua em "mostrar ocultos"**, marcado "passou" / "Ocultado automaticamente", sem
  Restaurar (volta sozinho se a data mudar).
- **Não some:** o futuro, e a **invoice vencida**, que é dinheiro a receber e não data que
  passou (D-2026-08-31: "cobrança por lote, mas não some"). Se o dono quiser esconder
  também as invoices, é outra decisão.

## Contexto
Em 06/10 o quadro tinha 7 tarefas de 26–27/09 com "A IA tentou e disse: … sem crédito ou
fora da cota". A IA ficou sem crédito na Anthropic perto de 28/09; o evento de tarefa vencida
roda uma vez por tarefa e, falhado, não é refeito. A IA voltou (eventos de 01–05/10 DONE).
