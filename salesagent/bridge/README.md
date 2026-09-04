# sales-bridge — ponte Kommo ⇄ OpenClaw (Sales Agent URace)

Serviço local no VPS (Lightsail `OpenClaw-1`). Implementa os portões do
`../rules-to-code.md`: o modelo conversa, este código protege.

```
Kommo (Salesbot/webhook) → /kommo/hook (ACK <2s) → worker → OpenClaw (urace-sales)
        ↑                                                        ↓ tools HTTP
   resposta ao cliente  ←  send_to_lead  ←  gates (preço/idade/estado/escalação)
                                             ↓
                              WhatsApp interno (escalações) → humano → /human/reply
```

## Estado da implementação

- [x] Config (segredos em `~/.urace/`, nunca no repo)
- [x] Cliente Kommo v4 (lead, nota, task, tag, estágio) — testado contra a conta real (account OK)
- [x] Máquina de estados SQLite (AI_ACTIVE → WAITING_HUMAN → HUMAN_HANDOFF → RESUMED → CLOSED) com transições guardadas
- [x] Portões: G1 preço, G2 roteamento, G5 idade, G8 sem-memória, B4 gatilhos de escalação
- [x] Endpoints de tools autenticados (price, qualify, escalate, crm)
- [x] Execução real das diretivas `[[...]]` que o agente anexa à conversa (21/08, `directives.py`) — qualify/crm/escalate/followup(como task)/price (com segunda rodada ao modelo para o link real chegar na mesma resposta)
- [x] Criação do agente `urace-sales` no OpenClaw (sem shell/filesystem) com as instruções de `../instructions/` — e o processo de sincronização (`../tools/sync_agent_instructions.sh`) depois que descobrimos que o workspace do agente não lê o repo ao vivo
- [x] `notify_human`: comando de envio direto ao canal WhatsApp, testado ao vivo
- [x] Credenciais expostas no chat durante a implantação, rotacionadas (21/08)
- [x] `send_to_lead`: caminho real implementado (continuação do Salesbot via `return_url` + `execute_handlers`; fallback: nota no lead). Hook aceita o payload real do widget_request (parser tolerante multi-formato) e loga o bruto (`hook_raw`) para calibração. **Falta o lado do Kommo:** configurar o Salesbot — guia completo em `../docs/kommo-circuit-setup.md`
- [x] Serviço systemd + HTTPS público — instalado e confirmado no VPS (21/08): `sales-bridge` no systemd, Caddy em `urace-bridge.duckdns.org` com certificado válido (Apache ocioso desativado), `/health` respondendo de fora
- [x] Agendador de follow-up (B2, 3 trilhas — 21/08, `scheduler.py`): thread na ponte, tick por minuto. Trilha `initial` (+2h/+24h/+3d/+7d → fecha), `link_sent` (+10min/+24h/+3d/+7d → task humana), `scheduled` (data do lead via `[[followup]]`). Mensagem composta pelo agente com o contexto da sessão; entrega espontânea via `bots/run` no Salesbot (config `FOLLOWUP_BOT_ID` em `bridge.env` — sem ela, fallback nota+tarefa). Resposta do lead cancela a trilha; escalação também (G3)
- [x] Alarme de escalação (C2 — 21/08, no mesmo scheduler): re-alerta no WhatsApp interno a cada 15min (config `ESCALATION_REALERT_MIN`) enquanto o lead estiver em WAITING_HUMAN/HUMAN_HANDOFF, só das 9h às 18h de Orlando; fora do horário, segura até as 9h
- [ ] Sincronização do snapshot do Rate Card com a planilha

## Instalação no VPS (resumo — guia completo na implantação)

```bash
cd ~ && git clone https://github.com/UraceUs/Uraceagent.git
cd Uraceagent/salesagent/bridge
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# segredos: ~/.urace/kommo.env (já existe) e ~/.urace/bridge.env (AGENT_API_KEY=..., HUMAN_WHATSAPP=...)
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8800
```

Serviço systemd, integração Salesbot e testes ponta a ponta: ver documentação
de implantação (Fase 3/4 da missão).

## ⚠️ O agente NÃO lê as instruções do repo em tempo de execução

Descoberto em 21/08: o agente `urace-sales` no OpenClaw lê arquivos próprios
dentro de `~/.openclaw/workspace/urace-sales/` (`AGENTS.md`, `IDENTITY.md`,
`SOUL.md`) — uma **cópia** feita na configuração inicial, sem nenhum vínculo
com o repo. `git pull` atualiza `salesagent/instructions/urace-sales-agent.md`
e `salesagent/identity/*.md` no disco, mas isso **não muda o que o agente
usa** até a cópia ser refeita manualmente.

**Sempre que `salesagent/instructions/urace-sales-agent.md` ou
`salesagent/identity/*.md` mudar, depois do `git pull` rode:**

```bash
bash salesagent/tools/sync_agent_instructions.sh
openclaw gateway restart
```

Sem isso, qualquer teste (inclusive `tests/run_scenarios.py`) está validando
comportamento antigo, não o que está commitado.

## ⚠️ O mesmo problema existe pro agente da escalação (`notify_human`)

Descoberto em 25/08: `notify_human()` chama `openclaw agent --agent main
--channel whatsapp ...` para avisar Italo/Eduardo de uma escalação — mas o
workspace desse agente `main` **nunca recebeu** a identidade do Mark
(`admagent/identity/*.md`). Sem ela, o agente trata a escalação como uma
conversa nova e responde "quem sou eu, quem é você" em vez de repassar o
texto — a escalação nunca chega de forma acionável, e o humano nunca sabe
que precisa responder 'aprovar'/'retomar'.

**Sempre que `admagent/identity/*.md` mudar (e ao menos uma vez, agora):**

```bash
bash salesagent/tools/sync_admin_identity.sh
openclaw gateway restart
```
