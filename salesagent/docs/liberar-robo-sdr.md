# Liberar o robô SDR para todos os leads (e como voltar atrás)

Decisão D-2026-10-13. O robô hoje só responde card com a tag `teste-sdr` (`SDR_ATENDER_SO_TAG`).
Este roteiro é para tirar essa trava, com a segurança de poder desligar em um minuto.

## Antes de liberar (10 minutos)

1. **Pré-voo.** No VPS: `cd ~/Uraceagent && git pull` e depois o script abaixo, com o mesmo Python que roda a
   ponte. Ele não escreve nada, não manda mensagem e não imprime chave. Corrija toda linha `FALHA`.
   ```
   python3 salesagent/tools/sdr_preflight.py
   ```
2. **Teste no painel.** `ops.urace.us/ops/sdr` → "Testar o robô": "Oi, quanto custa?", "É meu filho, 8 anos",
   "Nunca andou de kart", "Faria se fosse mais barato", "Quero fechar", "Agora não". Confira tom curto, uma
   pergunta por vez, sem nome de ninguém do time e a oferta de call no fim.
3. **Teste no Instagram** com um lead novo com a tag `teste-sdr`: "Oi" e "Quanto custa?" em seguida deve
   gerar **uma** resposta só.

## Liberar

1. No VPS, abra `~/.urace/bridge.env` e **apague a linha** `SDR_ATENDER_SO_TAG=teste-sdr`.
2. `sudo systemctl restart sales-bridge && systemctl is-active sales-bridge`
3. A partir daí o robô responde todo lead do Instagram que estiver nas etapas dele: First Contact, Cold Leads e
   Follow Up 1 (funil Urace) e ENTRADA (funil Comercial). Card em ATENDIMENTO ou em etapa da equipe não recebe.

## Quando uma pessoa assume a conversa (regra de ouro)

O robô **não sabe** quando alguém da equipe escreve no chat. Antes de responder um lead à mão, faça **uma** destas:

- mover o card para **ATENDIMENTO** (o robô para de responder ali), ou
- clicar em **Pausar IA** no chat do Kommo, ou na página Robô SDR → "Conversas com a IA pausada".

Se não fizer, o robô e a pessoa podem responder juntos. Para voltar a automatizar: "Reativar IA".

## Primeira hora depois de liberar

- Painel Robô SDR → "O que o robô decidiu": veja as decisões entrando.
- No VPS: `sudo journalctl -u sales-bridge --since "1 hour ago" --no-pager | grep -iE "error|429|nota|fallback" | tail -30`
  - `429`: o Kommo limitou as chamadas (cada balão é um disparo do bot de entrega). Avise e baixe o nível.
  - `resposta gravada como nota, não entregue`: a entrega falhou naquele lead; uma pessoa responde à mão.
- Tags para filtrar no Kommo: `followup:1-call`, `followup:2-reativacao`, `followup:sem-resposta-24h`,
  `sdr:agora-nao`, `sdr:handoff`.

## Voltar atrás

- **Parar de responder, mantendo a organização dos cards:** painel Robô SDR → nível **Organizar**.
- **Parar tudo:** nível **Observar**.
- **Uma conversa só:** Pausar IA nela.
- **Voltar ao escopo de teste:** recoloque `SDR_ATENDER_SO_TAG=teste-sdr` em `~/.urace/bridge.env` e reinicie a ponte.

## O que o robô faz sozinho (resumo)

- Responde em balões curtos, uma pergunta por vez, sem link na primeira resposta, sem nome de ninguém do time.
- Preço só o da tabela (taxa da pista sempre à parte). Nunca desconto, nunca confirma data.
- Qualificado (idade, experiência, objetivo) ou com objeção ou pronto para fechar ou já competindo: oferece a
  call de 15 min com o nosso time e avisa a equipe.
- "Agora não": agradece, não insiste, tarefa em 7 dias. "Pare de mandar": confirma e fecha o card como perdido.
- Sem resposta: ~1h30 sugere a call, 23 h depois faz um check-in, e para (janela de 24 h da Meta). Nada sai
  entre 21h e 8h de Orlando.
