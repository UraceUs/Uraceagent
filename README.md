# URACE — Agente de Vendas (Chase) + Sales Brain

Agente comercial da URACE: atende leads no Kommo, qualifica pela
classificação A/B/C/D, recomenda o programa certo, agenda follow-ups — e
passa para uma pessoa quando é o caso. Em produção desde 24/08/2026
(circuito completo validado com lead real via Instagram).

## O princípio que governa tudo

**As garantias vivem abaixo do modelo, não no prompt.** As regras que não
podem falhar são código na ponte, não pedidos ao modelo:

| Regra | Onde é imposta |
|---|---|
| Preço nunca em número no chat — sempre o link | `gates.get_price()` não devolve número (G1) |
| Competidor vai pro Italo, sempre | `experience=competes` força escalação (G2) |
| Conversa escalada não volta a vender | máquina de estados; retomada só por humano (G3) |
| Zero desconto pelo agente | gatilho regex escala ANTES do modelo responder (G4/B4) |
| Idade mínima | validação na ponte, recusa venha de onde vier (G5) |

## Arquitetura (visão de 1 minuto)

```
Lead (Instagram/WhatsApp/etc.)
  → Kommo CRM (funil "Chase — AI Sales Funnel", Salesbot + widget custom)
  → Caddy HTTPS (urace-bridge.duckdns.org)
  → sales-bridge (FastAPI no VPS: portões, estados, diretivas, agendador)
  → OpenClaw (agente Chase, sessão por lead)  ← brain/ (conhecimento, via retrieval)
  → resposta volta pelo mesmo caminho (mensagem única no chat)

Escalações → WhatsApp interno (agente Mark) → Italo/Eduardo
```

Página visual completa: peça o artifact "Arquitetura do Chase", ou veja
`docs/auditoria-sales-brain.md` para o diagnóstico detalhado.

## Estrutura do repositório

```
salesagent/     O agente de vendas em produção
  bridge/         A ponte (FastAPI): app, gates, state, directives,
                  textproc, scheduler, brain_kb, kommo_client
  instructions/   Instruções canônicas do Chase (sincronizadas pro OpenClaw)
  identity/       Identidade do agente (IDENTITY/SOUL)
  config/         Rate card, links de programa, pipeline Kommo (dados ≠ prompt)
  kommo-widget/   Widget custom do Salesbot (upload no Kommo)
  deploy/         systemd, Caddy, instaladores
  tests/          19 cenários automatizados contra o agente real
  discovery/      As 8 fontes de negócio extraídas
  CONSOLIDACAO.md Decisões C1–C12 e hierarquia de fontes

brain/          Sales Brain — knowledge base do agente (vault Obsidian)
  _meta/          Schema de frontmatter e regras (leia primeiro)
  _dashboards/    Painel humano
  0*_*/           Conhecimento por tipo (empresa, vendas, produtos...)
  09_LEARNINGS/   Aprendizados (candidate → approved, aprovação humana)
  indexer.py      Vault → índice de busca SQLite FTS5 (incremental)
  extract_learnings.py  Log de auditoria → candidatos de aprendizado

admagent/       Identidade do agente interno (Mark) — WhatsApp interno
docs/           Missões, auditoria, guias (Obsidian, Kommo, OpenClaw)
legacy-v1/      Geração 1 (n8n/Supabase) — nunca implantada, preservada
```

## Sales Brain — como o conhecimento funciona

- **Humanos** editam Markdown no Obsidian (abrir este repositório como
  vault — guia em `docs/obsidian-guia.md`). `git push` publica.
- **O agente** nunca lê o vault: um índice FTS5 entrega só os trechos
  relevantes de documentos **aprovados** por conversa (injeção automática
  + diretiva `[[kb]]`). Conteúdo em português; campo `aliases` faz a ponte
  com leads em inglês/espanhol.
- **Aprendizado**: ciclo diário extrai padrões do log (escalações
  recorrentes, buscas sem resposta) e propõe `candidate` — promover para
  `approved` é sempre gesto humano, no Obsidian.
- Regras completas: `brain/_meta/README.md`.

## Operação no VPS (Lightsail)

```bash
# deploy de qualquer atualização
cd ~/Uraceagent && git pull
bash salesagent/deploy/install_bridge_service.sh   # ponte + reindex do brain

# se as instruções/identidade do agente mudaram:
bash salesagent/tools/sync_agent_instructions.sh
openclaw gateway restart

# testes e diagnóstico
python3 salesagent/tests/run_scenarios.py          # 19 cenários no agente real
python3 brain/indexer.py --self-test               # pipeline do brain, sem custo
python3 brain/indexer.py --query "own kart"        # testa uma busca
python3 salesagent/tools/show_recent_audit.py -n 30
sudo journalctl -u sales-bridge -f
```

## Configuração (segredos NUNCA no repo)

Ficam em `~/.urace/` no servidor — ver `.env.example` para o inventário
completo de variáveis (`kommo.env`, `bridge.env`, chaves). Flags úteis do
`bridge.env`: `BRAIN_RETRIEVAL=on|off` (retrieval do Brain),
`SALESBOT_DISPLAY=json_reply|balloons` (formato de entrega),
`FOLLOWUP_BOT_ID` (follow-up no chat).

## Documentação

- `docs/auditoria-sales-brain.md` — diagnóstico + plano do Sales Brain
- `docs/obsidian-guia.md` — Obsidian para Italo/Eduardo (revisar conhecimento)
- `salesagent/docs/kommo-circuit-setup.md` — circuito Kommo completo
- `salesagent/bridge/README.md` — estado da ponte, checklist
- `docs/openclaw-setup.md` — setup do OpenClaw
- `docs/urace-ai-agent-arquitetura.md` — arquitetura da geração 1 (histórico)
