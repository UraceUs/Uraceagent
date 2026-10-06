---
tipo: decisao
tipo_info: DECISION
data: 2026-10-06
fonte: [[Administrative AI]]
responsavel: Quem exclui peça do estoque e o que "excluir" faz.
status: ativo
---

# D-2026-10-06 — Excluir peça do estoque pela lixeira do card

issue #98, 06/10/2026

## O que foi decidido
Dono: *"dá a permissão para mecânico, gerente, acesso livre, que eles consigam excluir aquela
peça ali das prateleiras. Um íconezinho de lixeira… deseja realmente excluir essa peça? E aí,
só o sim ou não."*

- **Quem:** mecânico, gerente e acesso livre (papel OPERATOR para cima).
- **Como:** lixeira no card → "Deseja realmente excluir esta peça?" → **Não** / **Sim, excluir**.
- **O que faz:** a peça sai das prateleiras (`active=0`). **Nada se apaga**: movimentos,
  cobranças e auditoria (`stock.item.remove`) continuam apontando para ela, e o razão segue
  batendo. Regra do dono que continua valendo: não destruir dados.
- **Não sai:** peça de cliente guardada com a gente. Primeiro devolve ou entrega; depois exclui.
- **Código de barras** de peça excluída volta a ler como código novo no Balcão e pode ser
  cadastrado de novo noutra peça.
