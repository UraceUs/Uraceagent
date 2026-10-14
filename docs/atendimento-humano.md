# Atendimento humano — escalonamento da IA, fila e WhatsApp

Missão de 14/10/2026 (conta urace@urace.us). Decisão registrada em
`brain/08_DECISOES/D-2026-10-14 - Atendimento humano e a IA travada na conversa escalada.md`.
Guia de uso para a equipe: `docs/playbooks/playbook-vendas.md` › "Atendimento humano".

## 0. Estado em uma tabela

| Parte | Implementado | Testado | Em produção | Bloqueio |
|---|---|---|---|---|
| Caso, estados e transições (`handoff_casos`, eventos append-only) | sim | sim (44 + 5 testes) | **não** (falta deploy) | — |
| Trava da IA no sistema (pausa + estado da ponte, conferida na saída) | sim | sim, inclusive corrida e reinício | **não** | — |
| Ferramenta `escalate_to_human` (painel e ponte) | sim | sim | **não** | — |
| Fila no painel (`/ops/atendimento`): assumir, responder, transferir, encerrar, devolver | sim | sim (unidade + navegador) | **não** | — |
| Aviso por push no celular e no chat da equipe | sim | sim (push com dublê) | **não** | a pessoa precisa ativar o aviso no celular |
| Aviso pelo WhatsApp oficial (Cloud API, número da equipe) | sim | sim (Meta com dublê) | **não** | número da equipe, token e template aprovado na Meta |
| Resposta ao cliente pelo WhatsApp | já existia (Kommo) | circuito provado em 11/09 | sim (Kommo) | — |
| Integração ponte ↔ painel ligada | código pronto | sim | **não** | chave de API e segredo na VPS |

Nada foi implantado na VPS nesta sessão: a sessão não tem acesso de shell à VPS, e a chave da AWS
no ambiente é recusada pela STS (`InvalidClientTokenId`). O deploy é um bloco de comandos para o
dono (seção 9).

## 1. O que a auditoria encontrou

Lido no repositório (branch do VPS `claude/configurar-open-claw-ooqo8x`), no Command Center pelo
conector só-leitura e nas notas do cérebro. **Não verificado** está marcado.

- **Hospedagem:** VPS na AWS Lightsail (`OpenClaw-1`, blueprint OpenClaw, Ubuntu), usuário
  `ubuntu`, serviços systemd, Caddy na frente (`ops.urace.us` e `urace-bridge.duckdns.org`). Sem
  Docker para os nossos serviços; o OpenClaw usa sandbox Docker para os agentes.
  *Não verificado:* região, plano, IP, versão do SO e do OpenClaw (sem shell na VPS; chave AWS
  inválida nesta sessão).
- **Command Center** (`command_center/`): FastAPI + SQLite (`~/.urace/command-center.sqlite`) + SPA
  React, `127.0.0.1:8790`. Versão em execução reportada pelo painel: commit `83780bf` (13/10). Papéis
  ADMIN/MANAGER/OPERATOR/VIEWER, chaves de API com hash, auditoria append-only, Web Push, chat da
  equipe, laço de 30 s. Integrações: Asana, DocuSign, Gmail, Kommo e QuickBooks **CONNECTED** em 14/10.
- **Ponte de vendas** (`salesagent/bridge`, serviço `sales-bridge`, `127.0.0.1:8800`): Kommo
  (Salesbot + webhook de conta) → regras → agente OpenClaw `urace-sales` (Chase) → resposta pelo
  Salesbot. Estado em `~/.urace/salesbridge.db`. Nível do robô em 14/10: **organizar** (não responde
  a lead), Chase desligado, 0 conversas pausadas.
- **OpenClaw:** agentes `urace-admin` (rotinas), `urace-sales` (Chase) e `main` (Mark, que repassava
  escalação no WhatsApp). O AI Command do painel saiu do OpenClaw em 08/10 (Claude Agent SDK).
- **Backup:** `adminai/backup_banco.py` (timer `urace-backup`) faz `VACUUM INTO` verificado do banco do
  Command Center. O banco da ponte (`salesbridge.db`) **não tem backup** (lacuna anterior a esta missão).

### WhatsApp da URACE

| Pergunta | Resposta | Como foi verificado |
|---|---|---|
| Onde está o número dos clientes? | No **Kommo**, por conexão oficial da API (WABA) | 69 mensagens de WhatsApp em 7 dias no Kommo, todas com origem `waba` (14/10, só metadado); teste ponta a ponta do dono em 11/09 (D-2026-09-11) |
| O painel fala com esse número? | Sim, **pelo Kommo**: resposta do painel → continuação do Salesbot → WhatsApp | código `crm.py` + D-2026-09-11 |
| Existe integração direta do painel com a Meta? | Existe o módulo do **número da equipe** (WhatsApp Cloud API), **não configurado** (`configurado=false`) | `GET /ops/api/whatsapp/status` |
| Como a ponte avisava escalação? | Pelo agente `main` do OpenClaw no canal WhatsApp **pareado por QR** — o WhatsApp Web (não oficial) | `salesagent/bridge/app.py::_notify_human_sync`, `docs/openclaw-setup.md` §2.5 |
| WhatsApp Business App em uso? Coexistência? | **Não verificado** (sem acesso ao Business Manager) | — |
| IDs da WABA/número, app da Meta, webhooks na Meta, escopos do token | **Não verificado** (o Kommo é o dono dessa conexão) | — |

Consequência: **o número de produção não pode ir para outra inbox** sem sair do Kommo (um número,
uma conexão de API). Nada aqui toca essa conexão.

## 2. A inbox: Kommo, com a fila no Command Center

| Critério | **Kommo + fila no painel** (escolhido) | Chatwoot Cloud | Chatwoot auto-hospedado |
|---|---|---|---|
| Número atual | já está nele (WABA oficial) | exige migrar o número (sai do Kommo) | idem |
| App do celular segue funcionando | não muda nada | depende de coexistência (não verificado) | idem |
| Atendimento compartilhado, atribuição | Kommo (responsável do lead) + caso com responsável no painel | sim | sim |
| API e webhooks | Kommo v4 + rotas `/ops/api/atendimento` | sim | sim |
| Travar a IA | trava no sistema da ponte (já existia a pausa por conversa) | precisaria de ponte nova | idem |
| Histórico e auditoria | Kommo + `handoff_eventos` append-only + `audit_logs` | sim | sim |
| Custo identificado | plano Advanced do Kommo já pago (valor **não verificado**); painel e VPS já existem | assinatura por agente (**não verificado** — o site do Chatwoot está fora da rede desta sessão) | VPS maior: Rails + Postgres + Redis + Sidekiq na mesma Lightsail de 2 GB não é seguro (requisito oficial **não verificado**) |
| Implantação e manutenção | um módulo a mais num serviço que já é implantado e testado | outra plataforma, outro login | outra plataforma para manter, atualizar e fazer backup |

**Decisão:** Kommo continua a caixa de entrada onde se responde ao cliente; o Command Center
ganha o que faltava: caso, trava da IA, fila com prazos, avisos e devolução à IA. Chatwoot
faria sentido só se o número saísse do Kommo, o que a missão proíbe e o funil inteiro (Salesbot,
etapas, agente do Kommo) dependem dele. n8n não entrou: o laço de 30 s do painel já faz fila,
retentativa e varredura, com teste.

## 3. Arquitetura implementada

```
cliente (WhatsApp/Instagram) ⇄ Kommo (WABA oficial · inbox da equipe)
          │ Salesbot / webhook de conta                    ▲ resposta da pessoa
          ▼                                                │ (Kommo ou painel → Salesbot)
  sales-bridge (ponte) ──── POST /ops/api/atendimento/casos (X-API-Key) ───▶ Command Center
   │ estado local WAITING_HUMAN                              │ handoff_casos  (HUMAN_PENDING…)
   │ outbox handoff_outbox (retentativa)                     │ ~/.urace/sdr_pausas.json  ◀── trava
   │ ia_pode_enviar() na SAÍDA ◀──── lê a pausa ─────────────┤ handoff_notificacoes (fila de avisos)
   │                                                         │   push · chat da equipe · WhatsApp Cloud API (equipe)
   ▲ POST /handoff/estado (X-Handoff-Token)                  │ /ops/atendimento (fila, caso, ações)
   └──────────── assumir / encerrar / devolver ──────────────┘ laço 30 s: reconciliar trava, avisos, prazos, ponte
```

Componentes (nenhum serviço novo):

| Componente | Onde |
|---|---|
| Estado, transições, avisos, reconciliação | `command_center/providers/atendimento.py` |
| Rotas (fila, ações, ferramenta) | `command_center/api/atendimento.py` |
| Tela | `command_center/web/src/pages/Atendimento.tsx` (`/ops/atendimento`, `/ops/atendimento/<id>`) |
| Cliente do painel na ponte + outbox | `salesagent/bridge/handoff_cc.py` |
| Trava na saída | `salesagent/bridge/pausas.py::ia_pode_enviar` (usada em `send_to_lead`, `deliver_followup`, entrega pendente) |
| Volta do painel para a ponte | `POST /handoff/estado` em `salesagent/bridge/app.py` |
| Laço | `command_center/api/main.py::_ciclo_atendimento` (junto do laço do chat, 30 s) |

### Estados

| Conversa | Caso | Quem fala com o cliente |
|---|---|---|
| `AI_ACTIVE` | nenhum aberto (ou o último foi `RETURNED_TO_AI`) | a IA (se o nível do robô for "atender") |
| `HUMAN_PENDING` | aberto, sem responsável | ninguém automático; a equipe é avisada |
| `HUMAN_ACTIVE` | aberto, com responsável | a pessoa |
| `RESOLVED` | encerrado com resultado | a IA volta na próxima mensagem do cliente (ciclo novo) |

Transições permitidas: criar → `HUMAN_PENDING`; `HUMAN_PENDING → HUMAN_ACTIVE` (assumir);
`HUMAN_ACTIVE → HUMAN_ACTIVE` (transferir); `HUMAN_ACTIVE → RESOLVED` (encerrar, resultado
obrigatório); `HUMAN_ACTIVE → RETURNED_TO_AI` (devolver, contexto obrigatório). Qualquer outra é
recusada (409). Toda transição usa trava otimista (`UPDATE … WHERE estado=?`): dois cliques em
"Assumir" ao mesmo tempo, só um vence. O banco garante **um caso aberto por conversa** (índice
único parcial).

Encerrar e devolver **esperam a ponte confirmar** antes de soltar a trava. Sem confirmação, o
caso continua `HUMAN_ACTIVE` com `ponte_pendente`, a IA continua travada e o laço tenta de novo.
Errar para o lado da pessoa custa espera; errar para o lado da IA custa uma resposta automática no
meio de um atendimento.

### A ferramenta

```
POST /ops/api/atendimento/casos          (chave de API OPERATOR, não só-leitura; ou pessoa logada)
{ "conversation_id": "kommo:31764961", "reason": "...", "priority": "high",
  "summary": "...", "customer_name": "...", "requested_action": "...",
  "category": "pagamento", "idempotency_key": "ponte:31764961:1760450000" }
→ { "resultado": "caso_criado" | "caso_existente", "caso_id", "estado", "ia_bloqueada",
    "notificacao": "enviada" | "pendente" | "falhou" | "sem_destino",
    "humano_notificado": bool, "avisos": {canal: {status: n}}, "instrucao_para_ia": "..." }
```

Na ponte, o mesmo contrato em `POST /tools/escalate` (aceita o formato antigo). Categorias:
`pedido_explicito, reclamacao, pagamento, excecao_comercial, falhas_repetidas, sem_autoridade,
seguranca, baixa_confianca, competidor, operacional, outro` — sem categoria, as palavras do motivo
escolhem. Prioridades `baixa | normal | alta | urgente` (aceita `low/medium/high/urgent`).
Os gatilhos que já existiam continuam valendo antes do modelo (B4 da ponte e roteador do SDR);
a ferramenta cobre o que o agente decide sozinho (baixa confiança, falha repetida, sem autoridade).

### Avisos

Texto (português, padrão interno): `[URACE IA · ATENDIMENTO HUMANO]`, prioridade, cliente,
conversa e canal, motivo, resumo, ação pedida, link do caso, link do Kommo, status. Sem telefone
do cliente.

| Canal | Para quem | Conta como "humano avisado"? |
|---|---|---|
| Push (Web Push do painel) | Operador, Gerente, Admin ativos sem cargo de box | sim, quando um aparelho aceita |
| Chat da equipe, canal "Atendimento humano" | os mesmos | não (é registro) |
| WhatsApp Cloud API (número **da equipe**) | contatos da equipe com `recebe_handoff=1` | sim, com id da Meta; o recibo (entregue/lido) chega pelo webhook |

Dentro da janela de 24 h vai texto; fora, só o template aprovado `WA_TEMPLATE_HANDOFF`; sem
template, o aviso fica `bloqueado` com o motivo. Sem configuração, `simulado` — e nunca conta como
avisado. Falha passageira volta para a fila (1, 2, 4, 8 min) e desiste na 5ª. Caso pendente depois
do prazo (urgente 5 min, alta 15, normal 60, baixa 240) é re-avisado a cada 15 min, até 4 vezes
(normal/baixa só seg–sex 8h–18h de Orlando). Cliente que escreve num caso em atendimento gera um
push para quem atende (um a cada 10 min).

Template para a Meta (categoria UTILITY, `pt_BR`), a submeter pelo Business Manager:

```json
{"name": "urace_handoff_alert", "language": "pt_BR", "category": "UTILITY",
 "components": [{"type": "BODY",
   "text": "Atendimento humano na URACE. Prioridade: {{1}}. Cliente: {{2}}. Motivo: {{3}}. Abra o caso: {{4}}",
   "example": {"body_text": [["ALTA", "Maria", "pagamento, cobrança ou reembolso", "https://ops.urace.us/ops/atendimento/12"]]}}]}
```

### Pontos de falha

| Falha | O que acontece |
|---|---|
| Painel fora do ar na escalação | a ponte já travou a conversa (WAITING_HUMAN); o pedido fica em `handoff_outbox` e sai quando o painel voltar (mesma chave: não duplica) |
| Arquivo de pausas apagado ou escrita interrompida | o laço reescreve a trava a partir do banco em até 30 s; o estado local da ponte trava enquanto isso |
| Ponte fora do ar ao devolver/encerrar | o caso segue com a pessoa e a IA travada; o laço confirma depois |
| Push/WhatsApp falhando | aviso fica na fila com o erro; a tela mostra; a IA recebe `humano_notificado=false` |
| Pessoa assume enquanto o modelo pensa | a trava é conferida na saída: a resposta da IA não sai |
| Reprocessamento do mesmo evento | chave de idempotência + índice único + chave por aviso |

Limite conhecido: robôs que rodam **dentro do Kommo** (menu do chatbot, agente de IA do Kommo,
automações da Meta) não passam pela ponte e não são travados por ela. Em 14/10 o agente de IA do
Kommo está desligado (D-2026-09-25, 30/09 — não reverificado nesta sessão). Se for ligado, a regra
equivalente precisa ser configurada no Kommo.

## 4. Segurança

- Segredos fora do repositório: `~/.urace/bridge.env` (ponte), `~/.urace/atendimento.env` e
  `~/.urace/whatsapp.env` (painel), permissão 600. Nada de segredo em log: a auditoria da ponte já
  mascara token/telefone; os eventos do caso não guardam texto do cliente.
- Ponte → painel: chave de API do painel (hash scrypt, papel efetivo nunca acima da pessoa,
  revogável). Painel → ponte: `X-Handoff-Token` próprio, comparado em tempo constante — não é a
  chave que abre o hook do Kommo.
- Assumir, transferir, encerrar, devolver e responder: **só pessoa** (chave de API recebe 403);
  encerrar, devolver e transferir só quem atende ou gerente; VIEWER só lê; chave só-leitura não
  abre caso.
- Webhook da Meta com `X-Hub-Signature-256` obrigatório (já existia). Teto de 30 aberturas por
  minuto por credencial (429; a ponte guarda e tenta de novo).
- Logs estruturados com `X-Request-ID`, que vai para cada evento do caso (`correlacao`).
- Retenção: caso fechado há mais de `HANDOFF_RETENCAO_DIAS` (padrão 365) perde o texto (resumo,
  motivo, resultado, nome) e mantém datas, estados e responsável (`limpar_retencao`; a rodar pelo
  dono quando quiser, não está agendada).
- Backup: tudo do caso mora no banco do Command Center, já coberto pelo backup diário verificado.
  A trava (arquivo de pausas) é derivada do banco e se refaz sozinha.

## 5. Testes (missão, letras A–K)

`python -m pytest -q command_center/tests/test_atendimento.py` (painel) e
`python3 salesagent/tests/test_handoff.py` (ponte; também roda no pytest via
`command_center/tests/test_ponte_atendimento.py`). Navegador:
`CC_E2E=1 python -m pytest -q command_center/tests/e2e -k atendimento`.

| Teste | Resultado | Evidência |
|---|---|---|
| A escalonamento básico | PASS | `test_A_*` (caso, motivo, trava, auditoria; conversa inválida 400); ponte: "A: escalar abre caso no Command Center" |
| B notificação | PASS (com dublês) | `test_B_*`: texto com todos os campos e sem telefone; push; WhatsApp dentro/fora da janela, template, recibo "lido" pelo webhook; simulado não conta |
| C atendimento humano | PASS | `test_C_*`: assumir, responder pelo circuito do Kommo, corrida de dois cliques, transferir; navegador: assumir na tela |
| D bloqueio da IA | PASS | `test_D_*`; ponte: resposta barrada na saída com o caso aberto durante o turno, follow-up/resgate/pendente barrados, texto humano passa |
| E devolução | PASS | `test_E_*`; ponte: RESUMED + nota na memória confirmada + IA volta a responder com o contexto; navegador: devolver na tela |
| F reinicialização | PASS | `test_F_*` (arquivo apagado → reconciliação; app reiniciado); ponte: processo novo continua travado |
| G eventos duplicados | PASS | `test_G_*` (mesma chave, mesma conversa, índice único, avisos não duplicam); ponte: reenvio idempotente |
| H indisponibilidade | PASS | `test_H_*` (ponte fora → pendente → recupera; aviso falha → fila → sai; desiste no teto; atrasado com teto); ponte: painel fora → outbox → entrega |
| I ciclo de webhooks | PASS | aviso no chat da equipe não vai ao WhatsApp; webhook da ponte ignora mensagem `outgoing` |
| J isolamento | PASS | `test_J_*`; ponte: travar um lead não trava outro |
| K autorização | PASS | `test_K_*`: chave abre mas não decide, leitor e chave só-leitura recusados, só quem atende/gerente encerra, sem login 401, teto por minuto |
| WhatsApp real ponta a ponta | **BLOCKED** | número da equipe, token e template não existem; nenhum envio real foi feito (por regra: nada de mensagem não autorizada) |

Mutação conferida: tirar a trava de `send_to_lead` ou o filtro do agendador faz os testes de D
falharem.

## 6. Deploy na VPS (dono) e reversão

Pré-requisito: o PR mesclado no branch do VPS. Comandos em uma linha, separados por `;` (D-2026-09-11).

1. **Atualizar o painel** (botão "Atualizar sistema" ou `bash adminai/deploy/command_center/servir_command_center.sh`).
   A tabela nova é criada na subida; nada existente muda. A tela `/ops/atendimento` já funciona
   para casos abertos à mão.
2. **Chave de API para a ponte:** no painel, **Usuários** (`/ops/users`, só Admin) › **Chaves de API**:
   criar a chave "ponte de vendas", papel **OPERATOR**, **sem** "só leitura". Ela aparece uma vez só.
3. **Segredo compartilhado** (na VPS):
   `T=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))'); printf 'HANDOFF_PONTE_URL=http://127.0.0.1:8800\nHANDOFF_PONTE_TOKEN=%s\n' "$T" >> ~/.urace/atendimento.env; chmod 600 ~/.urace/atendimento.env; printf 'CC_URL=http://127.0.0.1:8790\nHANDOFF_SYNC_TOKEN=%s\n' "$T" >> ~/.urace/bridge.env; echo 'CC_API_KEY=<colar a chave urk_ do passo 2>' >> ~/.urace/bridge.env; chmod 600 ~/.urace/bridge.env`
   (trocar o `<colar…>` à mão no arquivo; a chave nunca no chat).
4. **Reiniciar:** `sudo systemctl restart urace-command-center sales-bridge; sleep 3; curl -s 127.0.0.1:8800/health; curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:8790/ops/api/atendimento/saude`
   (esperado: ponte ok e `401` no painel sem sessão).
5. **Prova sem cliente real:** no painel, abrir um caso à mão para um lead de teste
   (`POST /ops/api/atendimento/casos` com `assume: true`, ou o fluxo da ponte com a tag
   `teste-sdr`), conferir a pausa em `~/.urace/sdr_pausas.json`, devolver à IA e ver a pausa sumir.
6. **WhatsApp oficial (quando o dono quiser):** número **da equipe** (não o dos clientes) na Meta,
   `~/.urace/whatsapp.env` com `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN`,
   `WA_APLICAR=1` e, aprovado o template acima, `WA_TEMPLATE_HANDOFF=urace_handoff_alert`; em
   Equipe › WhatsApp marcar quem recebe (`recebe_handoff`).

**Reversão** (do mais leve ao total):
- Desligar a integração sem deploy: tirar `CC_API_KEY` do `bridge.env` e reiniciar a ponte — o aviso
  volta a ser o anterior (OpenClaw). A regra nova continua: conversa escalada não recebe mensagem
  automática (ela não depende de configuração; voltar a regra antiga é reverter o código).
- Soltar as conversas: fechar os casos na tela (ou, em emergência, apagar as entradas com `handoff`
  de `~/.urace/sdr_pausas.json` — o laço as recria enquanto o caso estiver aberto no banco).
- Código: reverter o merge do PR. As tabelas `handoff_*` ficam no banco sem uso (nada lê delas); a
  coluna `team_contacts.recebe_handoff` também. Não há migração destrutiva.

## 7. O que ainda depende de alguém

| O quê | Quem | Por quê |
|---|---|---|
| Deploy (seção 6, passos 1–5) | dono na VPS | sessão sem acesso à VPS |
| Número da equipe no WhatsApp Cloud API + template aprovado | dono no Business Manager da Meta | aprovação externa e titularidade |
| Confirmar se o app WhatsApp Business ainda usa o número dos clientes (coexistência) | dono | sem acesso ao Business Manager |
| Desligar o aviso pelo OpenClaw/WhatsApp Web (`HANDOFF_LEGADO_OPENCLAW`) | dono | só quando push/WhatsApp oficial estiverem chegando |
| Backup do `salesbridge.db` | quem cuidar da VPS | lacuna anterior, fora do escopo |
