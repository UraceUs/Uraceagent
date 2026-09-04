---
tipo: processo
area: Shipping Orders
fonte: humano
atualizado_em: 2026-08-28
tipo_info: PROCESS
responsavel: Eduardo Resende
status: ativo
---

# Processo — compra e envio

Quadro **Shipping Orders** no [[Asana]], alimentado pelo [[Gmail]]
(marcador `Shipping Status`).

## O que a IA preenche
Nome da tarefa = **o item comprado**. Campos: fornecedor
([[Fornecedores]]), número do pedido, data, **link** de rastreio,
status e previsão de entrega.

**Dedupe pelo número do pedido** — e-mail de atualização do mesmo pedido
**atualiza** a tarefa, nunca cria outra.

## Status × quadro
Order Created → Shipped → Arrived (+ Payment pending, Refunded,
Cancelled). Campo e coluna andam juntos; empate resolvido pela **última
alteração** no histórico da tarefa.

## Sempre link, nunca código solto
Código UPS (`1Z…`) vira `https://www.ups.com/track?...`. Transportadora
desconhecida → **não inventar**, escalar. Link do Gmail expira; link do
[[Alibaba]] com token também.
