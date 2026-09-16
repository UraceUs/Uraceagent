---
tipo: decisao
data: 2026-09-16
fonte: dono (ditado)
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-16 — Lembretes recorrentes de invoice, ligados pela mão do gerente

[[QuickBooks]] · [[Conector do QuickBooks]] · [[D-2026-09-04 - Invoice sai depois de aprovada no painel]]

## O pedido

> *"Um botão nos clientes para mandar reminders — diário, semanal ou um período
> personalizado de dias — com o toggle de ligar e desligar. Tanto no perfil do cliente
> quanto no QuickBooks, onde eu seleciono as invoices em aberto que quero nesses reminders,
> de forma recorrente."*

E, na mesma hora: filtros na tela do QuickBooks — por valor, período, cliente, número da
invoice, palavras da invoice, datas específicas.

## Como ficou

- **Um lembrete por invoice** (`invoice_reminders`): cadência `daily` (1 dia), `weekly`
  (7) ou `custom` (N, de 1 a 90); ligado/desligado; `next_on` no dia local de Orlando.
- **Onde se liga:** no QuickBooks (marca as invoices com saldo → *⏰ Lembretes*) e na aba
  *Invoices* do card do cliente. O mesmo modal: frequência, toggle, *Salvar* e
  *Enviar agora ↗*. Na tabela, cada invoice mostra o estado (`semanal · próx. 18/09`, quantas
  vezes já foi) e o toggle.
- **A rotina** `lembrete_invoice` roda às **09:00** (agenda, mesma trilha da triagem do
  Gmail): manda o lembrete de cada invoice com dia chegado **e ainda com saldo**, e marca o
  próximo. **Invoice paga desliga o lembrete sozinha.**
- **O envio** é o `qbo_enviar_invoice` do QuickBooks — reenvia a invoice por e-mail para o
  e-mail de cobrança. Sem `APLICAR=1` é simulação, e a tela avisa.

## A regra de aprovação, nesta situação

Invoice sai da empresa só com aprovação humana (04/09). Aqui **quem liga o lembrete é um
MANAGER, na tela, escolhendo as invoices** — essa é a aprovação. Por isso a rotina não
passa pela IA nem pela fila de Aprovações, e OPERATOR não configura lembrete. Tudo fica na
auditoria: `invoice.reminder.configured`, `.toggled`, `.sent` (ou `.simulated`), `.stopped`.

Isso convive com a decisão de 31/08 ("cobrança é por lote; saldo em aberto não é
inadimplência"): o lembrete só existe onde o dono ligou, invoice por invoice.

## Filtros do QuickBooks

Busca por número, cliente, piloto, e-mail e palavra da invoice (o memo — é o que existe
no espelho como "tag"); status (com saldo · vencidas · em aberto · enviadas · pagas · com
lembrete ligado); valor de/até; período por vencimento ou emissão, com data específica
(de = até). Tudo na URL, então o filtro sobrevive a recarregar. A linha de resumo mostra
quantas e quanto em aberto no filtro, e dali se marcam todas as com saldo.
