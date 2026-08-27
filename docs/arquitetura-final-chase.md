# Chase — Arquitetura Final (fechamento de 27/08/2026)

> Documento de DECISÕES, não relatório. Cada capacidade do Chase tem uma
> camada dona, escolhida deliberadamente. Quem mudar de camada precisa
> refutar o motivo registrado aqui.

## 1. Arquitetura atual (o que existe e funciona)

```
Lead (Instagram/WhatsApp/site)
  → Kommo (Salesbot #9, id 162247, widget "Chase Bridge")
  → Caddy HTTPS (urace-bridge.duckdns.org: /kommo/hook /health /human/whatsapp)
  → sales-bridge (FastAPI) ────────── as GARANTIAS vivem aqui
  →   gates (G1..G9, B4) · state machine · confidence · holding
  →   scheduler (follow-up B2, re-alerta C2, resgate autônomo)
  → OpenClaw agente urace-sales (Chase), sessão permanente por lead
  ←   diretivas [[qualify|price|crm|escalate|followup|unknown|kb]]
  → resposta → Salesbot continue (modo balloons) → chat do lead

Escalação: bridge → (thread) Mark/main → WhatsApp Italo+Eduardo
Decisão:   reply no WhatsApp → Mark → POST /human/whatsapp (token mínimo)
           → parser de intenção → entrega ao lead + RESUMED
           → fato confirmado do cliente + candidato no Brain
Conhecimento: brain/ (vault Obsidian) → indexer FTS5 → retrieval por turno
Aprendizado:  extract_learnings (padrões) + knowledge_writer (respostas
              humanas) → candidate/review_required → humano aprova → índice
```

## 2. Achados da pesquisa (27/08)

- **A arquitetura de memória canônica do OpenClaw** é a que já praticamos:
  arquivos markdown curados injetados por turno (`MEMORY.md`/`USER.md`,
  <3k tokens, "curadoria > acúmulo") e **SQLite FTS5 local** como
  retrieval — sem vector DB em nuvem. Nosso Brain está no padrão da casa.
- **Skills no OpenClaw** são pacotes de 3 camadas (metadata, instrução,
  recursos/scripts) carregados no contexto — ou seja, uma skill É
  essencialmente prompt+scripts com privilégios. Para o Chase, isso
  compete com as instruções e com a ponte, não as substitui.
- **ClawHub tem problema grave de supply chain**: auditorias públicas
  acharam 341 → 824 skills maliciosas (campanha "ClawHavoc": stealers,
  instruções ocultas, exfiltração). Cinco passaram pelos scanners
  integrados.
- **Padrão vencedor de AI SDR 2026**: "exception-based escalation" com
  confidence thresholds (o agente roda sozinho no rotineiro e escala o
  caro-de-errar), CRM bidirecional, humano dono do julgamento. É
  literalmente `gates.py` + `confidence.py` + `/human/whatsapp`.

Fontes: [security analysis do framework](https://arxiv.org/pdf/2603.27517),
[skills: arquitetura e taxonomia de ameaças](https://arxiv.org/pdf/2604.02837),
[341 skills maliciosas](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html),
[Unit 42 sobre supply chain](https://unit42.paloaltonetworks.com/openclaw-ai-supply-chain-risk/),
[docs de memória](https://docs.openclaw.ai/concepts/memory),
[guia MEMORY.md](https://launchmyopenclaw.com/openclaw-memory-md-guide/),
[campo de AI SDR 2026](https://www.sellscale.com/blog-posts/the-ai-sales-industry-in-2026-a-field-guide),
[guia de build de AI SDR](https://www.foxreach.io/blog/build-an-ai-sdr),
[catálogo awesome-openclaw-skills](https://github.com/VoltAgent/awesome-openclaw-skills/blob/main/categories/marketing-and-sales.md).

*Limite honesto: a série de vídeos indicada não pôde ser assistida deste
ambiente (egress bloqueia YouTube). A arquitetura foi extraída das fontes
textuais acima, incluindo resumos independentes da mesma série/ecossistema.*

## 3. Skills avaliadas (ClawHub/comunidade)

| Skill/classe | Fonte | Serve p/ Chase? | Veredito | Motivo |
|---|---|---|---|---|
| CRM Automation (HubSpot/Salesforce) | ClawHub | não | **REJECT** | CRM é Kommo; nossa integração é código auditado com portões |
| Lead Hunter / Lead Enrichment / Apollo | ClawHub | não | **REJECT** | Chase é inbound; scraping/enriquecimento muda o produto e o risco |
| Cold-email / LinkedIn Outreach / Sequences | ClawHub | não | **REJECT** | outbound ≠ nosso funil; e follow-up já é código com trilhas B2 |
| Lead Scoring (heat map por tom/frequência) | ClawHub | conceito | **INSPIRE** | sinal útil; se um dia entrar, entra como código na ponte lendo o audit log |
| Memory/persistent-memory skills | ClawHub | não | **REJECT** | memória do cliente é SQLite da ponte (auditável, testável, com portões); skill de memória = estado fora das garantias |
| Browser automation / web research | ClawHub | não | **REJECT** | princípio: Chase sem shell, sem browser, sem filesystem |
| Scheduling (calendário) | ClawHub | ainda não | **INSPIRE** | agendamento hoje é humano (Italo); automatizar é decisão comercial futura |
| **Qualquer** skill de terceiro no agente de vendas | ClawHub | — | **política: REJECT por padrão** | 824 maliciosas confirmadas; agente fala com clientes e toca CRM |

**Decisão-síntese**: as "skills" do Chase são as **diretivas** (`[[...]]`)
executadas pela ponte — mesma modularidade, com autorização, log e teste.
Nenhuma skill de ClawHub instalada no `urace-sales`.

## 4. Mapa de camadas (quem é dono de quê)

| Capacidade | Camada dona | Implementação |
|---|---|---|
| Voz, fluxo A/B/C/D, roteiro, tom | Instruções (AGENTS.md) | `salesagent/instructions/` (sync + trava de truncamento) |
| Preço nunca em número; link | **Código (portão G1)** | `gates.get_price` |
| Competidor → Italo; desconto/refund/jurídico → humano | **Código (G2/B4)** | `gates.py`, antes do modelo |
| Idade mínima | **Código (G5)** | `gates.age_eligible` |
| "Não sei" vira handoff | **Código + diretiva** | `confidence.py` (limiar medido) + `[[unknown]]` |
| Conversa (histórico) | Sessão OpenClaw | `--session-key kommo-<lead>` (permanente) |
| **Memória estruturada do cliente** | **Código (SQLite)** | `conversations` + `confirmations`; injetada por turno via `_memory_context` |
| Fatos confirmados por humano (§7) | **Código** | `state.add_confirmation` → contexto de todo turno futuro |
| Próxima ação comercial (§10) | **Código (heurística) + instruções** | `_next_action` sugere; instruções detalham |
| Conhecimento do negócio | **Knowledge (vault Obsidian)** | `brain/` — humano edita, humano aprova |
| Busca de conhecimento | **Retrieval (FTS5)** | `brain/indexer.py`, incremental por hash |
| Aprendizado (respostas humanas → docs) | **Código → Knowledge** | `knowledge_writer` (§9/§14/§16, candidato sempre) |
| Follow-up (trilhas), resgate, alarme | **Workflow (scheduler da ponte)** | `scheduler.py` — determinístico, testado |
| Estágio, tarefas, notas, tags | **CRM (Kommo)** | via ponte, nunca direto pelo modelo |
| Entrega verificada (nunca 202 = prova) | **Código** | marcador no notify; modo balloons validado; fallback nota SEMPRE |
| Decisão humana em linguagem natural | **Código (parser)** | `human_intents` — na dúvida pergunta |

**Garantias abaixo do modelo (invioláveis)**: G1 preço, G2 roteamento,
G3 refinado (escalado não vende; factual coberto responde), G5 idade,
B4 gatilhos, autoridade por telefone, §9 candidato-nunca-approved,
lead-nunca-sem-resposta (holding + resgate), teto de alarme com migração
para tarefa.

## 5. Gaps fechados nesta sessão (26–27/08)

1. Lead mudo (3 caminhos) → `holding` + envio único ✔
2. Resgate autônomo (dívida de resposta paga sozinha) ✔
3. Escalação com nome/pergunta/perfil; reaviso imediato em pergunta nova ✔
4. Alarme com teto + migração para tarefa Kommo ✔
5. Loop do WhatsApp em linguagem natural (reply = resposta) ✔
6. Resposta humana → chat do lead + **fato do cliente** + candidato no Brain ✔
7. Memória estruturada por turno + próxima ação ✔
8. Entrega real (json_reply quebrado → balloons validado) ✔
9. Notify assíncrono (não rouba a janela do lead) ✔
10. Truncamento do AGENTS.md detectado + trava no sync ✔ (correção no VPS pendente de confirmação)

## 6. Painel oficial (Clawdi)

- **URL oficial do painel gerenciado**: https://cloud.clawdi.ai/
  (Overview, Sessions, Channels, Skills, Memories, Vault, Agents,
  Settings; restart e health do gateway pela UI).
- Painel self-host deste projeto: https://urace-claw.duckdns.org
  (Caddy basic_auth usuário `urace` + token do gateway;
  `openclaw config get gateway.auth.token`).
- Não inventar URLs internas: o gateway local é 127.0.0.1:18789 e só sai
  pelo Caddy acima.

## 7. Multi-agente (fronteiras que não se cruzam)

- **Chase (`urace-sales`)**: fala SÓ com leads, SÓ via Kommo. Sem shell,
  sem browser, sem skills de terceiro, sem WhatsApp.
- **Mark (`main`)**: fala SÓ com Italo/Eduardo no WhatsApp interno.
  Relay burro por desenho: entrega texto cru + citação à ponte com token
  de escopo mínimo. Futuro ADM Agent: pode crescer, MAS o caminho de
  escalação não muda de comportamento.
- Autoridade humana: `salesagent/config/human-operators.json` (fonte
  única); telefones no env.

## 8. Pendências que dependem de ação externa (VPS/Kommo)

| # | Ação | Comando/local | Efeito se ficar |
|---|---|---|---|
| 1 | Confirmar fim do truncamento do AGENTS.md | `openclaw config set agents.defaults.bootstrapMaxChars 40000` + sync + restart + doctor | Chase opera sem 25% do manual (incl. protocolo de diretivas) |
| 2 | Ferramenta de mensagem do Mark | somar `group:messaging` em `agents.main.tools` + restart | reply do WhatsApp pode falhar → loop humano não fecha |
| 3 | Teste vivo do handoff | responder uma escalação real no WhatsApp | único elo nunca exercitado ponta a ponta |
| 4 | Cooldown 5min dos 13 gatilhos | 2 msgs em 30s → conferir 2 hook_raw | mensagem de lead pode morrer antes da ponte |
| 5 | Rotação de segredos | client secret Kommo (24/08) + `openclaw secrets configure` (plaintext no openclaw.json) | exposição conhecida |

## 9. Como validar depois de qualquer mudança

```bash
for t in salesagent/tests/test_*.py; do python3 "$t" >/dev/null && echo "OK  $t" || echo "FALHOU $t"; done
python3 brain/indexer.py --self-test
python3 salesagent/tools/probe_notify_human.py      # canal humano em 30s
python3 salesagent/tools/probe_salesbot_run.py --bot 162247 --lead <id>
```

## 10. Status final

**NOT READY para "fechado sem ressalvas" — READY para operação assistida.**

Objetivamente: toda a lógica está implementada, testada (5 suítes + 6
self-tests, ~90 checagens, todas verdes) e em produção via git. O que
impede o carimbo final são os itens da seção 8 — todos exigem mãos no
VPS/Kommo/WhatsApp, nenhum é código. O primeiro handoff real respondido
no WhatsApp, com o item 1 e 2 aplicados, fecha o ciclo. A partir daí o
critério de pronto é o teste de vida real do brief (lead → qualifica →
escala → humano responde → lead some → follow-up → volta dias depois →
memória intacta → fechamento), que agora tem TODAS as peças no lugar.
