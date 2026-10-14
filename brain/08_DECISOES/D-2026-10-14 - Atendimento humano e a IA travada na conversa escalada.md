---
tipo: decisao
tipo_info: DECISION
data: 2026-10-14
fonte: missão no chat do Claude Code (conta urace@urace.us), 14/10/2026 — "Implementar escalonamento humano e inbox WhatsApp da URace"
responsavel: Italo Silveira
status: ativo
---

# D-2026-10-14 — Atendimento humano e a IA travada na conversa escalada

[[Decisoes]] · [[D-2026-09-21 - Chat interno e a ponte com WhatsApp e Google Chat]] · [[D-2026-09-25 - Chase reorganizado como SDR]] · [[D-2026-10-13 - Playbook de resposta no robo SDR]]

## O que foi pedido

Quando uma conversa precisa de gente, a IA aciona um escalonamento estruturado; a equipe é
avisada no WhatsApp da URACE; uma pessoa assume numa caixa de entrada compartilhada e responde
ao cliente pelo WhatsApp; **a IA para de responder enquanto a conversa está com a pessoa** e só
volta por uma devolução explícita. Tudo com histórico, responsável, horários, falhas e
tentativas de entrega. Sem migrar o número de produção e sem automação não oficial do WhatsApp.

## O que foi decidido (e por quê)

1. **A caixa de entrada é o Kommo, com a fila no Command Center.** O número dos clientes já está
   numa conexão oficial da API do WhatsApp **dentro do Kommo** (provado em 11/09, D-2026-09-11).
   Um número só pode estar numa conexão de API por vez: pôr o Chatwoot (ou outra inbox) no mesmo
   número seria migrar o número de produção e derrubar o Kommo, o Salesbot e o funil. A missão
   proíbe isso e manda não instalar uma segunda plataforma quando já existe uma adequada. O
   Command Center ganha o que o Kommo não tem: o caso, a trava da IA, a fila (pendente, em
   atendimento, atrasado, sem responsável, resolvido), os avisos e a devolução à IA.
2. **A trava é do sistema.** Caso aberto escreve a conversa em `~/.urace/sdr_pausas.json` (o
   mesmo arquivo da pausa manual de 13/10) e a ponte confere, **na saída**, antes de toda
   mensagem automática (resposta, follow-up, resgate, entrega pendente). O estado local da
   ponte (WAITING_HUMAN/HUMAN_HANDOFF) trava sozinho também: o painel fora do ar não destrava.
3. **Conversa escalada não recebe mensagem automática nenhuma.** Isto **supera**:
   - o **G3 refinado de 27/08** (a IA respondia, em conversa escalada, a pergunta factual que o
     Brain cobria);
   - a **mensagem de espera e o resgate** em conversa escalada ("lead nunca sem resposta"
     continua valendo até a escalação; a própria escalação leva uma mensagem ao cliente);
   - a **oferta de call em conversa já escalada** da D-2026-10-13. A oferta de call continua
     saindo no turno em que a objeção de preço **escala**; o que deixou de sair é a repetição
     dentro de um caso aberto.
   Motivo: a missão exige que nenhuma resposta automática seja enviada enquanto a conversa está
   em HUMAN_PENDING ou HUMAN_ACTIVE. Se o dono quiser de volta alguma dessas exceções, ela volta
   como regra explícita, testada, no `pausas.ia_pode_enviar`.
4. **Aviso só por canal oficial.** Push no celular (Web Push do painel), o canal "Atendimento
   humano" no chat da equipe e o **WhatsApp Cloud API do número da equipe** (módulo de 30/09,
   ainda não configurado). O aviso antigo da ponte pelo OpenClaw no WhatsApp (pareado por QR — é
   o WhatsApp Web, que a D-2026-09-21 já tinha recusado) deixa de ser o caminho quando o painel
   está configurado na ponte; fica disponível só com `HANDOFF_LEGADO_OPENCLAW=1`, para transição.
5. **A IA nunca diz que avisou sem ter avisado.** A ferramenta devolve `humano_notificado=true`
   só com push aceito por um aparelho ou WhatsApp com id da Meta; chat da equipe e simulação são
   registro, não aviso.

## O que fica com o dono

- Configurar o WhatsApp oficial da equipe (número próprio, token, app secret) e aprovar o
  template `urace_handoff_alert` na Meta — sem isso o aviso sai por push e chat da equipe.
- Ligar a integração na VPS (chave de API do painel para a ponte e o segredo compartilhado) — ver
  o bloco de deploy em `docs/atendimento-humano.md`.
- Desligar de vez o aviso pelo OpenClaw/WhatsApp Web (`HANDOFF_LEGADO_OPENCLAW` fora do
  `bridge.env`), quando o push e o WhatsApp oficial estiverem chegando.
