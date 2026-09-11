# Resumo do Projeto Chase (Agente de Vendas) — fechamento pré-pivot

**Data:** 27/08/2026 · **Status:** DESCONTINUADO por decisão do dono (pivot para
Administrative AI / Segundo Cérebro Operacional) · **Branch/PR:**
[`claude/configurar-open-claw-ooqo8x` → PR #2](https://github.com/UraceUs/Uraceagent/pull/2)

Este documento é o registro de tudo que o projeto do agente de vendas construiu,
quebrou, consertou e provou — para que nada se perca no pivot e qualquer decisão
futura (reativar, aproveitar peças, ou desmontar) seja tomada com o histórico completo.

---

## 1. O que era o projeto

Um agente de vendas ("Chase") atendendo leads da URACE (kart racing, NAICS 711212)
que chegam pelo Kommo CRM (Instagram/WhatsApp), com escalação para humanos
(Italo e Eduardo) via WhatsApp interno e aprendizado contínuo gravado no vault
Obsidian (`brain/`).

**Pipeline de produção (VPS Lightsail "OpenClaw-1", 34.230.114.116):**

```
Lead (Instagram/WhatsApp) → Kommo CRM → webhook → Caddy (HTTPS)
  → sales-bridge (FastAPI, porta 8800, venv próprio)
      → OpenClaw gateway (127.0.0.1:18789, mode:local) → agente `urace-sales` (Chase)
      → agente `main` (Mark) → WhatsApp interno (escalações p/ Italo/Eduardo)
  ← resposta ao lead via Kommo salesbot `bots/{id}/run` (balloons)
```

**Garantias que o dono exigiu e que foram implementadas:**
- Lead NUNCA fica sem resposta (nem em erro, nem escalado, nem com agente fora do ar).
- Resposta em ≤1 minuto (janela real do salesbot ≈ 58s).
- Continuidade: a conversa retoma de onde parou, mesmo dias depois.
- Memória por cliente: CRM + histórico + fatos confirmados por humano, cruzados a cada turno.
- Escalação IMEDIATA com Nome/ID/Telefone/Pergunta/Contexto (sem cooldown no primeiro aviso).
- Humano responde por texto natural no WhatsApp (sem sintaxe de comando) e a resposta
  vira fato confirmado do cliente, usável na hora — aprovação no Obsidian só para
  conhecimento global.
- HTTP 200/202/rc=0 nunca é prova de entrega — só confirmação visual + logs.

## 2. Arquitetura final (peças e onde estão)

| Peça | Onde | O que faz |
|---|---|---|
| Ponte | `salesagent/bridge/app.py` | `process_inbound` de saída única (nunca-mudo), gates G1/G2/G3/G5/B4, `_memory_context`/`_next_action`, escalação com briefing |
| Estados | `salesagent/bridge/state.py` | AI_ACTIVE→WAITING_HUMAN→HUMAN_HANDOFF→RESUMED→CLOSED + tabela `confirmations` (memória por cliente) |
| Espera com nexo | `salesagent/bridge/holding.py` | Mensagens de espera PT/ES/EN citando a pergunta pendente; detecta ping vs. pergunta nova |
| Loop humano | `salesagent/bridge/human_intents.py` | Texto natural = resposta; extração do lead pela mensagem citada |
| Conhecimento | `salesagent/bridge/knowledge_writer.py` | Candidatos ao Brain com dedupe, detecção de conflito, nunca sobrescreve fato promovido por humano |
| Confiança | `salesagent/bridge/confidence.py` | BM25 (limiar −3.8 medido) → NONE/LOW/CONFLICT/STALE/OK |
| Agendador | `salesagent/bridge/scheduler.py` | Follow-ups, teto de re-alertas (4 → tarefa no Kommo), resgate autônomo de dívida de resposta |
| Kommo | `salesagent/bridge/kommo_client.py` | Rota de entrega confirmada empiricamente (`bots/{id}/run`, `entity_type:"leads"` string) |
| Manual do Chase | `salesagent/instructions/urace-sales-agent.md` | Protocolo de diretivas `[[...]]`, exceção de lead retornante, lista de "nunca dizer" |
| Operador | `salesagent/tools/chase_doctor.py` / `chase_validate.py` | Recuperação e validação em um comando (auto re-exec no venv) |
| Doctor de acesso | `salesagent/tools/openclaw_access_doctor.py` | Diagnóstico do login do painel (token do ARQUIVO, pareamento, 3 rotas) |
| Deploy | `salesagent/deploy/` | Caddy do painel (`fix_claw_ui_ws.sh`, `remove_claw_ui_password.sh`, `setup_claw_ui.sh`), serviço da ponte |
| Testes | `salesagent/tests/` | 5 suítes / 83 checagens — todas verdes (ver §5) |
| Operadores | `salesagent/config/human-operators.json` | Autoridade de Italo/Eduardo; conhecimento de operador = review_required |

Documentos de arquitetura e auditoria:
- `docs/arquitetura-final-chase.md` — mapa de camadas, invariantes, tabela USE/ADAPT/INSPIRE/REJECT de skills do ClawHub
- `docs/auditoria-sales-brain.md` · `docs/missao-sales-brain-obsidian.md` · `docs/obsidian-guia.md`
- `docs/openclaw-setup.md` · `salesagent/docs/kommo-circuit-setup.md`
- `docs/adminai/descobertas-fase2.md` — já do pivot: mapa real de Asana/Calendar/QuickBooks + fechamento da FASE 1

## 3. Linha do tempo de incidentes → correções (o histórico que não pode se perder)

1. **Incidente fundador (25/08):** lead 31764961 (Eduardo) perguntou "can I bring my own kart?", o gatilho B4 escalou e um `return` deixou o lead mudo. → `process_inbound` reescrito com saída única: todo caminho produz resposta (`test_never_silent`, 26 checagens).
2. **`json_reply` fantasma:** toda entrega retornava 202 e nada aparecia no chat. Só `balloons` renderiza nesta conta → `SALESBOT_DISPLAY=balloons`. Origem da regra "202 nunca é prova".
3. **Meu erro de `tools.allow` (causa dominante da 1ª validação real):** setar `agents.list.0.tools {"allow":[...]}` SUBSTITUI o toolset inteiro → "No callable tools remain", Mark mudo, escalações mortas. → `chase_doctor` faz sonda funcional e só REMOVE allowlists quebradas; nunca seta.
4. **AGENTS.md truncado em 25%** (`bootstrapMaxChars` corta em silêncio): Chase nunca leu o protocolo de diretivas → limite 40000 + guarda no `sync_agent_instructions.sh`.
5. **Menu A/B/C/D reenviado a lead retornante** (artefato da era truncada) → exceção de lead retornante nas instruções + `_next_action`.
6. **"Come by anytime" para serviço 100% agendado** → lista de "nunca dizer" no manual.
7. **`notify_human` bloqueante (36s+/operador)** roubava a janela de ~58s do salesbot → thread fire-and-forget com verificação de entrega por marcador de lead-id.
8. **Alarme sem teto** e, no oposto, lead escalado repetindo a pergunta sem reaviso → teto de 4 re-alertas com fallback em tarefa Kommo + reaviso IMEDIATO quando lead escalado manda mensagem substantiva.
9. **`WAITING_HUMAN→CLOSED` não existia:** "fechar <lead>" era aceito, logado e recusado em silêncio pela máquina de estados → transição adicionada.
10. **G3 refinado:** lead escalado que pergunta algo que o Brain cobre (ex.: horário) recebe resposta na hora; escalação é só para o que o Chase não sabe. B4 escalado nunca volta ao modelo.
11. **`ModuleNotFoundError: httpx`** (python do sistema vs. venv da ponte) em validadores → padrão `os.execv` de re-execução no venv em TODOS os scripts (o `chase_validate` foi pego pela extensão contradizendo o doctor 5/5).
12. **Caddy derrubado por import duplicado** (o bridge do Kommo divide o mesmo Caddy!) → check glob-aware + `caddy validate` antes de todo reload.
13. **Login do painel OpenClaw — 4 causas empilhadas:** URL de IP cru (roteamento por hostname), token `__OPENCLAW_REDACTED__` (o CLI redige; o arquivo tinha o token real), basic_auth bloqueando o handshake WebSocket (erro 1006), gateway rejeitando Origin externo (anti-DNS-rebinding) → rota `@ws` com `header_up Host/Origin`, doctor v3 lendo o token do arquivo, pareamento de dispositivo aprovado pelo dono. **Validado: "entrei".**
14. **Teste poluindo o vault real** (`test_human_loop` gravou candidato como Italo) → `LEARNINGS_DIR` redirecionado no import + verificação de vault-intacto na suíte.
15. **Harness com expectativa errada na validação do lead real:** assumi que o fato confirmado era o kart; era o horário. A re-escalação do Chase estava CORRETA — o harness passou a ler a pergunta confirmada do banco. (Inconsistências documentam-se, não se corrigem em silêncio.)

## 4. O que foi provado AO VIVO (não só em teste)

- **Loop humano completo, ponta a ponta:** lead perguntou → escalação chegou no WhatsApp com briefing → Italo respondeu por texto natural ("de quarta a domingo das 8am as 1 pm") → resposta entregue ao lead → estado RESUMED → confirmação gravada → candidato de conhecimento criado. Confirmado por screenshot.
- **Entrega visual via balloons** no Instagram do lead real (screenshots).
- **Memória por cliente:** fato confirmado dias antes entra no contexto do turno; isolamento entre leads verificado.
- **Login do painel OpenClaw** validado pelo dono ("entrei") após as 4 correções.

## 5. Estado dos testes na descontinuação

Todas verdes: `test_never_silent` (26) · `test_escalation_alarm` (8) ·
`test_lead_rescue` (9) · `test_human_loop` (22, vault-hardened) ·
`test_customer_memory` (18). Total: 83 checagens.

## 6. Invariantes e regras de segurança (valem também para o pivot)

- Escalação imediata, sem cooldown no primeiro aviso; teto só nos RE-alertas.
- Resposta humana = fato confirmado do cliente, usável na hora; Obsidian aprova só conhecimento global.
- Nunca instalar skills de terceiros do ClawHub em agente voltado a cliente (campanha "ClawHavoc": centenas de skills maliciosas).
- `tools.allow` explícito SUBSTITUI o toolset — nunca setar; só remover quando quebrado, com sonda funcional antes e depois.
- Token do gateway por FRAGMENTO de URL (`#token=`), nunca `?token=`; CLI redige `config get` — a fonte da verdade é o arquivo.
- `caddy validate` antes de qualquer reload (a ponte do Kommo divide o Caddy).
- rc=0 / HTTP 200/202 / `sent=true` nunca são prova de entrega.
- Não presumir schema/paths/python; descobrir antes de agir.

## 7. Pendências herdadas (parqueadas, não perdidas)

- `remove_claw_ui_password.sh` pronto; execução é do dono (a extensão recusou rodar script que enfraquece segurança — recusa correta e endossada).
- Verificar `openclaw devices list` — dispositivo `43dc...5220c2` (operator.read, sem IP; provavelmente pareamento local benigno).
- Rotacionar o token do gateway (transitou em chats) via `--regen-token` (dono).
- Rotação do client secret do Kommo (pendente desde 24/08).
- 2 arquivos não rastreados no vault do VPS em `brain/09_LEARNINGS/`.
- **Decisão de negócio em aberto:** o Chase continua atendendo leads durante a migração, ou é desligado? (Produção nunca se mata em silêncio.)

## 8. Onde o pivot já está

FASE 1 (login do painel OpenClaw) **encerrada e validada**. FASE 2 adiantada com
sondas reais via MCP: workspaces e projetos do Asana mapeados (U-RACE, ADM URACE,
Financeiro), **template de corrida com 25 subtarefas padrão** descoberto
(inclui "Pre race invoice" e "After race invoice" — a regra "A IA NÃO ENVIA A
INVOICE" já está registrada), calendário alvo "Urace Race Calendar", QuickBooks
identificado (URACE / NAICS 711212). Detalhes em `docs/adminai/descobertas-fase2.md`.

## 9. Links de referência

**Projeto**
- PR do trabalho inteiro: https://github.com/UraceUs/Uraceagent/pull/2
- Painel OpenClaw: https://urace-claw.duckdns.org
- Clawdi (conta cloud): https://cloud.clawdi.ai/
- Health da ponte: https://urace-bridge.duckdns.org/health

**Pesquisa que fundamentou as decisões**
- Memória canônica do OpenClaw (markdown curado por turno + FTS5): https://docs.openclaw.ai/concepts/memory
- Guia MEMORY.md: https://launchmyopenclaw.com (guia MEMORY.md)
- Supply chain do ClawHub ("ClawHavoc", 341→824 skills maliciosas): https://thehackernews.com (busca: 341 malicious ClawHub) · Unit42: openclaw-ai-supply-chain-risk
- Catálogo auditado de skills: https://github.com/VoltAgent/awesome-openclaw-skills
- Agentes SDR / escalação por exceção: arXiv 2603.27517 · arXiv 2604.02837 · sellscale (AI sales 2026 field guide) · foxreach (build an AI SDR)
- Série de vídeo usada pelo dono: https://youtu.be/u4ydH-QvPeg

**Dados de produção (não recriar; histórico é evidência)**
- Lead de validação: 31764961 (NUNCA resetar/recriar/limpar histórico)
- Banco da ponte: `~/.urace/salesbridge.db` (conversations/audit/confirmations)
- Config do gateway: `~/.openclaw/openclaw.json` · Relatórios do doctor: `~/.urace/doctor-*.md`
