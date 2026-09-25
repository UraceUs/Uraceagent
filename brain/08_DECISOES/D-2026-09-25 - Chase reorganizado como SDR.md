---
tipo: decisao
tipo_info: DECISION
data: 2026-09-25
fonte: pedido no chat do Claude Code, 25/09/2026 (conta urace@urace.us) — "reestruture todo o projeto do chase para que se adeque às novas diretivas para o SDR"
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-25 — Chase reorganizado como SDR

[[Decisoes]] · [[Projeto Chase]] · [[D-2026-08-27 - Descontinuar o Chase]]

## O que foi pedido

Reorganizar o código do Chase (`salesagent/`) pelas diretivas do SDR,
definidas na mesma semana: com uma pessoa só no atendimento, o Kommo passa a
separar o que é lead do que não é, e o comercial só olha lead. As diretivas
foram montadas e testadas antes em outro repositório (UraceUs/Chase-ai-BOT,
PR #1) e agora vivem aqui, em Python, dentro da ponte.

## Como ficou

- **Um funil próprio, "Novo funil".** Tem etapas de triagem (recebem tudo) e
  etapas de venda (só lead). Os funis da equipe não são tocados. A tabela das
  etapas está em `salesagent/docs/sdr.md`.
- **Triagem determinística** (`salesagent/sdr/`): código, e-mail de sistema,
  spam e fornecedor ficam fora da venda, com a tag `nao_e_lead`, que a equipe
  já usava à mão. Preço, agenda, conversão, pedido de pessoa e evento do site
  descem para venda.
- **Escalação com prioridade.** Alta chama agora. Média vira tarefa na fila
  do responsável único.
- **Guarda de estilo** no que sai para o lead: sem emoji, sem travessão, sem
  as frases proibidas do Chase.
- **Três níveis** em `SDR_MODO`: `observar`, `organizar` e `atender`.

## Travas

- **O padrão é `observar`:** decide e só registra no log. Não escreve no
  Kommo e não fala com lead. Assim nada aqui contraria
  [[D-2026-08-27 - Descontinuar o Chase]] (leads 100% humanos) nem
  [[D-2026-09-17 - O que a IA pode fazer, revisado pelo dono]] (etapa, tag e
  resposta no Kommo são do dono).
- **A IA não revoga decisão.** Subir para `organizar` ou `atender`, e religar
  o serviço `sales-bridge`, só com a palavra do dono. Quando ele disser, isto
  vira uma nova nota, que superará em parte a D-2026-08-27.
- O material de venda da era Chase segue no arquivo
  ([[D-2026-08-31 - Conhecimento da era Chase fica no arquivo]]). O SDR não
  afirma preço, horário, idade nem política que não tenha fonte confirmada:
  manda o link (G1) ou escala.

## O que ainda depende da palavra do dono

1. Ligar `organizar`, e depois `atender`.
2. Horário de atendimento humano. O valor atual é provisório: quarta a
   domingo, 9h–18h. A pista opera 8h–13h.
3. Qual robô responde no Novo funil: o Salesbot da ponte ou o chat do Command
   Center. O Kommo não roda dois bots no mesmo lead.
4. Quem é o responsável único (`KOMMO_RESPONSAVEL_ID`).
