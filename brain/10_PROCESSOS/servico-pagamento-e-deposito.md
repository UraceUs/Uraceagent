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
| Invoice do serviço aparece paga no QuickBooks | prepara a invoice do depósito (US$ 400) para o responsável e avisa que está pronta |
| Depósito pago | marca a subtarefa "Security Deposit paid?" e registra na descrição |
| Serviço a ≤2 dias com alguma invoice em aberto | **alerta o humano** — é o prazo estourando |
| Antes de preparar qualquer depósito | **conferir no QuickBooks se já foi cobrado** desse cliente para esse serviço |

A conferência prévia não é burocracia: em 28/08 descobrimos que o
depósito do Tyron Brouta **tinha sido cobrado e pago** (invoice
`4YZRN1QWN529NQM`, US$ 400, 03/06/2026) e simplesmente não estava
registrado na tarefa. Sem conferir, a IA cobraria de novo um cliente que
já pagou.

## ⚠️ Quem envia a invoice — pendente

A regra original do dono, em maiúsculas, é **"A IA NÃO ENVIA A INVOICE"**
(prepara, preenche, revisa; enviar é humano). Este processo diz que o
depósito "já pode ser enviado" assim que a primeira for paga.

Até o dono confirmar o contrário, a IA **prepara e avisa** — o envio é
humano, como nas invoices em geral. Se ele autorizar o envio automático
do depósito (valor fixo, destinatário conhecido, gatilho objetivo), vira
exceção declarada nos PARÂMETROS, igual às duas exceções de e-mail.
