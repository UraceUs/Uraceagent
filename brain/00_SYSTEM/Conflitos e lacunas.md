---
tipo: sistema
tipo_info: CONTEXT
fonte: sondas ao vivo + decisões do dono
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Conflitos e lacunas

[[URACE]] · [[Tipos de informação]] · [[Protocolo de aprendizado]] ·
[[Escalonamento]]

> **A lista do que a IA NÃO sabe, e do que ela sabe de dois jeitos
> diferentes.** É a nota que ela consulta antes de afirmar coisa em cima
> de assunto delicado. Registro vivo — entra e sai item.

Regra: quando duas fontes discordam, **as duas ficam registradas**. A IA
não escolhe lado. Ver [[Protocolo de aprendizado]], passo 6.

---

## ⚠️ Conflitos abertos — `needs_human_confirmation`

Nenhum. Os dois que existiam foram fechados em 18/09 — ver a tabela abaixo.

## ❓ Lacunas — `UNKNOWN`

### U-02 · Fornecedor do e-mail `whitesoldier205@gmail.com`
Recebeu um pedido "SUIT - Frankie Iadevaia". Não se sabe se é o Manzoor,
o WheelDeal ou outro. → [[PARAMETROS]] · [[Fornecedores]]

*(As outras lacunas foram fechadas em 18/09 — tabela abaixo.)*

## 🔒 Fechado — o que já foi resolvido

- **U-07 · dispensa de waiver** — fechada em 04/09: **cliente VIP dispensa waiver**. Lista em [[PARAMETROS]]; primeiro caso [[Rafael Pionti]]. Também fechado no mesmo dia: **RACES não entra na varredura de waiver**.

Fica aqui como memória: **estes assuntos não precisam ser reabertos.**

| # | Era | Resolvido em | Como ficou |
|---|---|---|---|
| F-01 | Waiver "vale por temporada"? | 31/08 | **1 ano da assinatura** — é o que o e-mail promete ao cliente |
| F-02 | Existe modelo de e-mail de invoice? | 31/08 | **Não existe porque não é preciso** — o [[QuickBooks]] envia |
| F-03 | Texto do Adult Waiver está errado | 31/08 | **Decisão: fica como está.** Não é bug esquecido |
| F-04 | Depósito é por pacote ou por cliente? | 28/08 | **Por cliente**, enquanto retido — conferir se foi devolvido |
| F-05 | Reminder de cobrança: autorização permanente? | 31/08 | **Não** — aprovação por lote |
| F-06 | Templates vazios do [[DocuSign]] | 31/08 | Não serão usados **nem apagados** → escolher template por ID |
| C-01 | Rate Card × QuickBooks: 4 células | 18/09 | **A Rate Card manda, sempre** — e ela é mantida atualizada no Drive: "sempre consultar lá" (dono) |
| C-02 | Terça é dia de serviço? | 18/09 | **É dia de serviço, sim.** A coluna TUESDAY do Asana vale; o horário público de quarta a domingo não é a regra interna |
| U-01 | `sendReminder` do DocuSign | 18/09 | **A IA não cutuca o cliente** — avisa só o dono, como já fazia |
| U-03 | Devolução do security deposit | 18/09 | **A IA prepara, o dono devolve.** Ele informa peças e serviços a subtrair do valor |
| U-04 | Política de desconto | 18/09 | **Existe em casos raros, com o motivo explicado** — e a decisão continua sendo do dono, caso a caso |
| U-05 | Data do serviço a partir da invoice paga | 18/09 | **A data já está na tarefa do Asana** — não há o que deduzir |
| U-06 | Papel do [[Lucas Azaro]] | 18/09 | **Marketing / vendas (closer) / comercial** |
| U-08 | O que é "Offsight" | 18/09 | **Não existe: pode esquecer.** Sai do spec e do ADR |

---

## Como usar esta nota

- **Antes de afirmar** algo sobre um assunto listado aqui: ler primeiro.
- **Ao resolver** um item: mover para a tabela "Fechado", com a data e o
  como ficou. **Não apagar** — o histórico é o que impede reabrir.
- **Ao descobrir** conflito novo: registrar as duas versões com suas
  fontes, marcar as notas envolvidas `needs_human_confirmation` e
  escalar. Ver [[Escalonamento]].
