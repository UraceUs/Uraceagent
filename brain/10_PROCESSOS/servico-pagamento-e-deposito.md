---
tipo: processo
area: U-RACE / serviços
fonte: humano
ditado_por: Italo Silveira
data: 2026-08-28
---

# Processo — pagamento do serviço e security deposit

Vale para todo serviço do U-RACE (coaching, academy, summer camp,
trackside). São **duas invoices por serviço**, em sequência.

## A sequência

```
1. Serviço agendado
      ↓
2. INVOICE DO SERVIÇO criada (QuickBooks) e enviada ao cliente
      ↓
3. ⚡ PAGAMENTO DA INVOICE DO SERVIÇO CONFIRMADO
      ↓  ← é este o gatilho
4. INVOICE DO SECURITY DEPOSIT (US$ 400) vai para o cliente
      ↓
5. Pagamento do depósito confirmado
      ↓
6. ✅ As DUAS pagas — no mínimo 2 dias antes da data do serviço
```

## As duas regras

**Gatilho:** o security deposit só sai **depois** que a invoice do
serviço estiver **paga**. Não se manda as duas juntas: a segunda é
consequência da primeira.

**Prazo:** as **duas** invoices — serviço e depósito — precisam estar
**pagas com no mínimo 2 dias de antecedência** da data do serviço.
Valores e prazos em `brain/00_SYSTEM/PARAMETROS.md`.

## O que a IA faz

| Quando | Ação |
|---|---|
| Invoice do serviço aparece **paga** no QuickBooks | **envia** a invoice do depósito (US$ 400) ao responsável |
| Faltam **4 dias** para o serviço e o depósito não saiu | **envia assim mesmo** — pago ou não o serviço |
| Serviço agendado com **menos de 4 dias** de antecedência | envia o depósito **no mesmo dia do agendamento** |
| Depósito pago | marca "Security Deposit paid?" e registra na descrição |
| Faltam **2 dias** e falta invoice paga **ou** waiver assinada | **alerta o humano** — o prazo estourou |
| Antes de preparar qualquer depósito | **conferir no QuickBooks se já foi cobrado** desse cliente para esse serviço |

A conferência prévia não é burocracia: em 28/08 descobrimos que o
depósito do Tyron Brouta **tinha sido cobrado e pago** (invoice
`4YZRN1QWN529NQM`, US$ 400, 03/06/2026) e simplesmente não estava
registrado na tarefa. Sem conferir, a IA cobraria de novo um cliente que
já pagou.

## ✅ A IA envia a invoice do depósito — autorizado

Confirmado pelo dono em 28/08. É **exceção única**: vale só para o
depósito, porque é **valor fixo** (US$ 400), destinatário conhecido e
gatilho objetivo. A invoice do **serviço** continua sendo enviada por
humano — ali o valor varia e a regra "A IA NÃO ENVIA A INVOICE" segue
valendo.

## Os dois prazos, que são diferentes

```
       agendamento                        D-4        D-2      DIA DO SERVIÇO
            │                              │          │            │
            │  invoice do serviço paga ⚡   │          │            │
            │      → envia depósito         │          │            │
            └──────────────────────────────>│          │            │
                       ou, no limite:  envia │          │            │
                                   pago ou não│         │            │
                                              │         │            │
                             TUDO PAGO + WAIVER ASSINADA│            │
                                              └────────>│            │
```

- **D-4 = envio** do depósito (independe de a principal estar paga).
- **D-2 = tudo pronto**: invoice do serviço paga, depósito pago e waiver
  assinada. Faltou alguma → alerta.
- Agendou com menos de 4 dias? O envio é **no mesmo dia**.
