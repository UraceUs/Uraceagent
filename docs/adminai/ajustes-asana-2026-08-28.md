# Ajustes executados no Asana — 28/08/2026

Autorizados pelo dono ("pode ajustar" no SUITS; "ajuste o que for preciso
para isso nesse projeto" no Shipping Orders). Estado anterior salvo em
`backups/2026-08-28-antes-do-ajuste.json` — tudo é reversível.

## 1. SUITS — `Order number` (enum quebrado) → `Pedido` (texto)

**Descoberta:** o enum guardava DUAS coisas diferentes — código do pedido
(`#JBXAB`, `#M6IQU`…) e o CANAL por onde o pedido chegou (`wpp Italo` em
9 tarefas, `email` em 2, `emial` em 1). E o projeto **já tinha** um campo
de texto chamado `Pedido` (`1206689200495431`), ocioso: o enum era uma
duplicata quebrada.

**Feito:** 26 tarefas migradas (26/26, zero falhas). Todas são pedidos
históricos de 2023–24, já com status Delivered.
- `Mark Bergs` foi pulada de propósito: o `Pedido` dela já dizia
  "email/square", que é mais completo que o enum ("email").
- `Matt Hayden` teve os dois preservados: `#ZJ3YF (email/site)`.
- `Alexander Jacoby`: o valor era `emial` (erro de digitação); gravei
  `email`. Correção declarada aqui, não silenciosa.
- `Michael`: mantive `KJCBE` exatamente como estava (sem inventar o `#`).

**NÃO feito — falta permissão:** remover o campo `Order number` do
projeto retornou `forbidden / Access denied`. A conta do conector não tem
permissão para alterar as configurações de campo do projeto. E o Asana
não converte enum em texto de jeito nenhum, nem por API nem pela tela.

→ **AÇÃO DO DONO (30 segundos, na tela do Asana):** abrir SUITS →
Personalizar → Campos → `Order number` → Remover do projeto. Os dados já
estão salvos no `Pedido`, então nada se perde. Depois disso o campo certo
para número de pedido passa a ser `Pedido`, que aceita qualquer texto.

## 2. Shipping Orders — links que funcionam

Regra do dono: **sempre link**, para qualquer pessoa abrir e ver. O que
estava quebrado não era o uso de link — era link que não abre. 9 tarefas
corrigidas (9/9):

| O que estava errado | Tarefas | Correção |
|---|---|---|
| Código UPS solto, sem link | CHAINS · Kart Sport #46244 · #46245 · Placas Schiavo · IAME Reedjet KA100 | virou `https://www.ups.com/track?track=yes&trackNums=<código>` |
| URL sem `https://` (não clicava) | Kartsport #46662 | esquema adicionado |
| Link do Gmail (`google.com/url?q=…`) que expira | STORMCRAFT Gaming PC · Pedido bateria 4un | desembrulhado para o link real (Newegg / Amazon) |
| URL de e-mail do Alibaba com tokens de sessão | Alibaba parts | `Order Number` = 309514646501022128 · `Tracking` = link estável `biz.alibaba.com/ta/detail.htm?orderId=…` |

Nenhum valor foi inventado: todos os links saíram dos próprios dados da
tarefa (código de rastreio ou parâmetro dentro da URL original).

**2 casos NÃO corrigidos, com comentário na tarefa pedindo o humano:**
- *Cleanner machines - Vevor*: código `D10017456323377` não bate com
  nenhuma transportadora que eu saiba identificar. Não invento.
- *3 Ice fox cameras - Fedex*: Order Number `03-14946-83381` mas o link
  aponta para `03-1494-683380` (outro número) e é página de PAGAMENTO do
  eBay, não rastreio. O nome diz Fedex e não há rastreio Fedex nenhum.

## 3. Regra nova de operação (definida pelo dono)

> "Se foi marcada como concluída, foi encerrada. O agente de IA precisa,
> a cada nova task, manter todas as atualizações nos comentários."

Consequências para o Admin AI:
- **Concluída = encerrada.** Ponto final, independente do campo Status.
  Os casos de "concluída com status In Production/In Transit" são erro
  humano de não trocar o status — não são pedidos em aberto.
- **O comentário é o diário de bordo.** Toda atualização que a IA fizer
  entra como comentário na tarefa. É isso que responde "por que a IA fez
  isso?" sem precisar de log externo.
- Comentários da IA sempre começam com `[IA ADM]`. Importante: o conector
  autentica como Italo Silveira, então sem esse prefixo pareceria que foi
  o Italo que escreveu.

## 4. Comentários já postados hoje (3)

- `Cleanner machines - Vevor` — transportadora desconhecida, pede humano.
- `3 Ice fox cameras - Fedex` — dados contraditórios, pede humano.
- `4 Pieces Hour Meters…` — seção "Cancelled" vs. campo "Order Created".
