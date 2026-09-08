# D-2026-09-08 — A IA se corrige antes de chamar humano

**Dono, 08/09/2026**, ao ver 23 itens em "Precisa de atenção" (19 e-mails
históricos de um cliente, 3 tarefas vencidas, 1 falha da própria IA):
*"preciso que a IA seja capaz de se autocorrigir sem precisar colocar tudo
como precisa de atenção."*

**Regra:** "Precisa de atenção" é **só o que a IA tentou e não resolveu**.

**O que ela resolve sozinha agora:**
- **E-mail** que é notificação (DocuSign, RD Station, ingresso, recibo),
  propaganda (`wNews`, bancos, apps) ou **coisa que nós mesmos mandamos**
  → marcado *tratado automaticamente*, com o motivo. Histórico trazido
  pela varredura (fora da inbox) é contexto, não trabalho.
- **E-mail de cliente** só vira item se está **na inbox, tem até 14 dias,
  não é nosso e não é notificação**. Prioridade da triagem decide ALTO ×
  MÉDIO.
- **Tarefa de dia passado ainda aberta** → evento `task.overdue`; a IA lê
  a tarefa e, se o serviço aconteceu, **move para Finished Services
  sozinha** (`asana_mover_para_finished`, SAFE, só para essa coluna). Só
  vira item se ela tentou e não conseguiu, com o que ela disse.
- **Ações SAFE** com argumentos **executam na hora**, sem esperar clique.
- **Falha da própria IA** só aparece se a **última** execução falhou (se
  ela se recuperou depois, silêncio), como MÉDIO e com o erro. O binário
  do OpenClaw é procurado sozinho (PATH, npm, nvm) e falhas transitórias
  ganham uma segunda tentativa.

**O que continua exigindo humano:** waiver e invoice (aprovação), mover
tarefa para qualquer outra coluna (confirmação), apagar e enviar e-mail
(nunca).

Relacionado: [[D-2026-09-04 - IA age a cada mudanca e aprende pelo balao]], [[Triagem de e-mail]], [[Asana]].
