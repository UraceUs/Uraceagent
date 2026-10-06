---
tipo: processo
area: Shipping Orders
fonte: humano
atualizado_em: 2026-10-06
tipo_info: PROCESS
responsavel: Eduardo Resende
status: ativo
---

# Processo — compra e envio

Quadro **Shipping Orders** no [[Asana]], alimentado pelo [[Gmail]]
(marcador `Shipping Status`).

## Desde 06/10: quem faz é o Command Center, sozinho
Dono, 06/10: *"a intenção é não ter necessidade de inserção humana, inserção manual"*.

- Todo e-mail de compra no urace@ (pedido, fatura/pagamento pendente, pagamento, preparando,
  enviado, em trânsito, saiu para entrega, atraso, entregue, cancelado, reembolso) vira ou
  atualiza a compra na tela **Compras** do Command Center — achada pelo nº do pedido (assunto
  ou corpo), pela fatura ou pelo rastreio. Fatura de fornecedor pelo QuickBooks entra como
  **conta a pagar** da compra.
- E-mail só com link: o Command Center **abre a página** de rastreio/pedido (sem login, sem
  formulário) e põe na linha do tempo o que ela diz. Página que exige login (Amazon, eBay,
  Alibaba) não é aberta: vale o que o e-mail disse.
- A compra vai sozinha para o **Shipping Orders** (`providers/compras_asana.py`): acha a
  tarefa que já existe, só preenche campo vazio, o status só anda para a frente e a tarefa
  vai para o quadro do status. Cancelled/Refunded/Pending-Review e tarefa concluída: só gente.
- **A IA da triagem não cria tarefa no Shipping Orders.** Se vir pedido que o Command Center
  não pegou (aparece em "Precisa de atenção" ou faltando na tela Compras), avisa — não cria
  outra tarefa, que vira duplicata.
- Verificação completa da caixa: `python3 adminai/sincronizar.py compras-varrer`.

## O que a IA preenchia (até 06/10 — histórico)
Nome da tarefa = **o item comprado**. Campos: fornecedor
([[Fornecedores]]), número do pedido, data, **link** de rastreio,
status e previsão de entrega.

**Dedupe pelo número do pedido** — e-mail de atualização do mesmo pedido
**atualiza** a tarefa, nunca cria outra.

## Status × quadro
Order Created → Shipped → Arrived (+ Payment pending, Refunded,
Cancelled). Campo e coluna andam juntos; empate resolvido pela **última
alteração** no histórico da tarefa.

## Código no campo, link na descrição (P-08, dono 06/10)
O campo **Tracking Number** guarda o **código** (`1Z…`); o **link** que abre vai na
**descrição** da tarefa (`https://www.ups.com/track?...`). Transportadora desconhecida →
**não inventar**, escalar. Link do Gmail expira; link do [[Alibaba]] com token também.
