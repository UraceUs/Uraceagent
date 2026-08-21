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
- [ ] Serviço systemd + HTTPS público (Caddy) — arquivos prontos em `../deploy/`, rodar `install_bridge_service.sh` no VPS e seguir o guia acima
- [ ] Agendador de follow-up de verdade (B2: hoje `[[followup ...]]` só vira uma task no Kommo com o due date, não dispara a mensagem sozinho)
- [ ] Alarme de escalação (C2: re-alerta 10–30min, 9h–18h Orlando)
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
