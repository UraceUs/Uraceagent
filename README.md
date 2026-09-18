# URACE — Command Center + agentes de IA

Este repositório tem **dois sistemas** da URACE. Um está rodando hoje; o
outro está em stand-by desde 27/08/2026.

## O que está no ar: Command Center

**https://urace-bridge.duckdns.org/ops/** — a mesa de operação da URACE.
Espelha Asana, DocuSign, Gmail, QuickBooks e Kommo em um lugar; a IA
propõe o que fazer e a pessoa aprova; tudo fica em auditoria imutável.
No ar desde 04/09/2026, com as cinco fontes conectadas.

Inclui a **área de vendas** (oportunidades, agenda de retornos e o
fechamento que dispara cliente, QuickBooks, waiver, Asana e Kommo numa
tela), o **chat do Kommo** dentro do painel e **voz** (ditar e ouvir) em
todo campo de texto.

→ **Manual completo, para humanos e para IA:**
[`docs/manual-do-command-center.md`](docs/manual-do-command-center.md)
→ **Fotografia do estado de hoje:**
`brain/04_PROJETOS/Administrative AI - Estado completo em 2026-09-17.md`
→ **Código:** `command_center/` (FastAPI + SQLite + React) · **deploy:**
`adminai/deploy/command_center/servir_command_center.sh`

## Em stand-by: agente de vendas (Chase)

Agente comercial que atendia leads no Kommo, qualificava pela
classificação A/B/C/D, recomendava o programa e passava para uma pessoa
quando era o caso. Ficou em produção de 24/08 a 27/08/2026 (circuito
validado com lead real via Instagram) e foi **pausado** quando o projeto
virou para o administrativo — o gargalo real não era vender, era
administrar. O dossiê do que existia está em
[`docs/resumo-chase-pre-pivot.md`](docs/resumo-chase-pre-pivot.md).
O resto deste README descreve esse agente, e continua valendo como
documentação dele.

## Por onde começar

| Você quer | Leia |
|---|---|
| **usar o painel** (o que está rodando) | [`docs/manual-do-command-center.md`](docs/manual-do-command-center.md) |
| saber o estado do projeto hoje | `brain/04_PROJETOS/Administrative AI - Estado completo em 2026-09-17.md` |
| entender o agente de vendas (Chase, em stand-by) | este README, abaixo |
| ver o porquê de cada regra | `brain/08_DECISOES/` |
| saber o que aconteceu, dia a dia | `brain/30_DIARIO/` |

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

- `docs/arquitetura-final-chase.md` — **decisões de arquitetura (camadas, skills, garantias) — leia primeiro**
- `docs/auditoria-sales-brain.md` — diagnóstico + plano do Sales Brain
- `docs/obsidian-guia.md` — Obsidian para Italo/Eduardo (revisar conhecimento)
- `salesagent/docs/kommo-circuit-setup.md` — circuito Kommo completo
- `salesagent/bridge/README.md` — estado da ponte, checklist
- `docs/openclaw-setup.md` — setup do OpenClaw
- `docs/urace-ai-agent-arquitetura.md` — arquitetura da geração 1 (histórico)
