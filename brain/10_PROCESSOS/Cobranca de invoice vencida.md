---
tipo: processo
tipo_info: PROCESS
fonte: Italo Silveira
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Cobrança de invoice vencida

[[Processos]] · [[QuickBooks]] · [[Invoice e estimate no QuickBooks]] ·
[[Clientes]]

Cobrar quem já venceu — **e só quem já venceu**.

- **A cada 2 dias:** reminder **somente das invoices OVERDUE**
  (vencidas). Parcela a vencer **não** entra — existe parcelamento, e
  cobrar cliente em dia queima a relação.
- **Aprovação POR LOTE** (decisão do dono, 31/08). A IA monta o lote,
  **mostra a lista** (cliente · valor · dias de atraso · link) e
  **espera o "ok"**. Não há autorização permanente: "ok" num lote **não
  vale** para o próximo. Sem "ok", o lote fica em stand-by — a IA não
  fica repetindo o pedido, mas **volta a alertar se o prazo apertar**.
- **Passou de 30 dias em aberto:** o cliente entra na lista de devedores
  do segundo cérebro, com o valor e há quantos dias — a IA precisa ter
  isso na memória, não só no relatório.

> ⚠️ Hoje há **US$ 185.887 em aberto**, sendo 84% em duas invoices de 2025
> ([[QuickBooks]]). E atenção: **invoice em aberto ≠ inadimplência** —
> existe parcelamento (ex.: 4× US$ 1.000).

## Aprovação é por lote

Decisão do dono ([[D-2026-08-31 - Cobranca por lote]]): **não existe
autorização permanente.** A IA monta o lote das overdue, **mostra a
lista** (cliente · valor · dias de atraso · link) e **espera o "ok"**.
"Ok" num lote **não vale** para o próximo.

A ferramenta `qbo_sales_send_invoice_reminder` também exige confirmação a
cada envio — limitação técnica e regra de negócio coincidem. Ver
[[Conector do QuickBooks]].

## Os dois casos que não entram na rotina

[[P-04 - Contas a receber concentradas]] — Juan Pacino e Stephen
Collins somam 84% do valor em aberto, vencidos desde 2025. **É conversa
humana**, não reminder automático.
