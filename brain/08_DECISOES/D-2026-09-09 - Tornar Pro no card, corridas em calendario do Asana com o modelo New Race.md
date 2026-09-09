---
tipo: decisao
data: 2026-09-09
fonte: dono (chat)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-09 — "Tornar Pro" no card, corridas em calendário do Asana e o modelo New Race

**Dono, 09/09/2026:** em cada cliente, um botão para **torná-lo Pro**; a
partir daí o card ganha o resto (equipamento etc.). A página solta de
equipamentos **não precisa existir agora** — só dentro do card. Corridas
em **visualização de calendário**, como no Asana, **só as corridas**
(sem treinos). Ao **convidar**, o piloto já fica **dentro daquela
corrida** até a confirmação de que vai ou não. Cada corrida nasce do
**modelo de tarefa de corrida** que já existe no Asana, com as mesmas
subtarefas.

**Como ficou:**
- Card do cliente: botão **☆ Tornar Pro** (gerente ou admin). Pro ganha
  as abas **★ Equipamento** (com o catálogo editável dentro, num bloco
  dobrável) e **★ Corridas** (as corridas em que está e a situação).
  Menu "Equipamentos" saiu; `/equipment` leva para Pro Racing Drivers.
- **Corridas** = calendário mensal da coluna **RACES** do quadro U-RACE:
  uma corrida por tarefa (`races.task_id`), nome e data seguem a tarefa;
  concluída ou fora da coluna sai do calendário (convites ficam). Chip
  mostra `★confirmados+aguardando?`.
- Clique na corrida: pilotos dentro dela com situação (*aguardando
  confirmação / confirmado / não vai / correu*), botões para convidar os
  Pro, prévia de custo pela IA, **subtarefas da tarefa ao vivo** e link
  para o Asana.
- **Nova corrida** instancia o modelo **"New Race [Race + City/Track]"**
  (`1208930444315129`) na coluna RACES — vem com as subtarefas do
  modelo. Nome: `Corrida [Cidade / Pista]`. Sem Asana: recusa, salvo
  "só no painel".
- Convite e mudança de situação viram **comentário na tarefa da
  corrida** (`[Command Center] Convidado: X — aguardando confirmação`),
  pela porta humana `comentar_humano` (não é ferramenta do agente).

Relacionado: [[D-2026-09-09 - Pro Racing Drivers, mensalidade e equipamento no card]], [[Corridas]], [[Asana]].
