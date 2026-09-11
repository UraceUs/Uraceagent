# D-2026-09-04 — A IA age a cada mudança e aprende pelo balão de instrução

**Dono, 04/09/2026:** *"Preciso que a IA aja a partir de cada nova
alteração: e-mail recebido, task criada. Criou uma sessão para
quarta-feira? Ela já dispara a invoice e a waiver. Em cada item de
'Precisa de atenção', um balão onde eu coloco a instrução; ela toma a
ação, aprende, salva na própria memória."*

**Como ficou** (`command_center/api/motor.py`):
- **Eventos**: a sincronia (a cada 15 min sozinha, ou no botão) registra
  `task.created` (tarefa de cliente em coluna de dia), `email.received`
  (cliente conhecido), `waiver.bounced`, `waiver.completed`.
- **Regras** (`automation_rules`, liga/desliga em Automação): cada evento
  com regra ligada vira um comando para o agente com o contexto do
  cliente (waivers e serviços no espelho) e a memória.
- **Propor ≠ executar**: o agente responde e declara as ações no
  protocolo `ACAO: ferramenta | alvo | resumo | {json dos argumentos}`.
  A política decide: waiver e invoice exigem **aprovação**; aprovar
  executa pelo sistema com `APLICAR` liberado só naquela chamada.
- **Balão**: a instrução vai para o agente com o item e, se marcado
  "guardar", entra em `ai_learnings` (global, por cliente ou por tipo).
  Toda memória ativa entra em todo comando seguinte.
- **Invoice**: enquanto o QuickBooks está em stand-by (P-11), a IA
  prepara e propõe; não existe envio real até conectar — e mesmo então só
  depois de aprovada (decisão da manhã).

**Limite conhecido:** o agente no OpenClaw roda com `APLICAR=0` (só
simula); é o Command Center que executa o que foi aprovado. Nada muda
nos sistemas sem clique humano.

Relacionado: [[VPS e OpenClaw]], [[Asana]], [[Gmail]], [[DocuSign]].
