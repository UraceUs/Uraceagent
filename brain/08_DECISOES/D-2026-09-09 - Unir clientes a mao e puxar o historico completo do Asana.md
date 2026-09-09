---
tipo: decisao
data: 2026-09-09
fonte: dono (chat)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-09 — Unir clientes à mão e puxar o histórico completo do Asana

**Dono, 09/09/2026:** *"tenho o Brian Santiago duas vezes, escrito de
maneiras variadas; preciso unir esses dois"*. E *"tem muita tarefa que
ainda não foi puxada do Asana — puxe todas as tarefas de treino que a
gente teve, ligue quem é o cliente e o serviço, para que todos os
serviços estejam na mesma pessoa"*; depois varrer as duplicatas para
a união.

**Por que faltava:** a sincronia de 15 min lia no máximo 500 tarefas
por coluna (teto da paginação) e só as colunas dos dias e Finished
Services; treino concluído em coluna de dia e o histórico além das 500
não entravam.

**Como ficou:**
- **⟳ Puxar histórico do Asana** (Clientes; gerente ou admin): lê
  TODAS as colunas menos Matt tasks, concluídas incluídas, sem teto;
  cada tarefa ainda sem cliente é lida por inteiro (notas → piloto e
  responsável) e ligada à pessoa; depois une os duplicados certos
  (mesmo e-mail/telefone/nome exato), recalcula ativo/inativo e conta os
  pares para decidir. Roda em segundo plano com progresso; a sincronia
  normal espera. A de 15 min passou a ler até 2000 por coluna.
- **⧉ Unir com…** no card do cliente e **Unir dois clientes** na lista:
  busca por digitação, sugestões "parece duplicado de" (Brian/Bryan,
  nome contido no outro, piloto de um = responsável do outro), escolha
  de qual card fica; serviços, waivers, e-mails e invoices passam; o
  outro sai (guardado em `client_merges`, auditado). A união automática
  continua estrita — a sugestão larga é só para decisão humana.

Relacionado: [[D-2026-09-04 - O que e cliente, ativo, e um card por pessoa]], [[Asana]].
