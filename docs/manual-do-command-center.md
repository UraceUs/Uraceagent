# Manual do Command Center — URACE

**Para quem é:** para as pessoas da URACE que usam o painel, e para qualquer IA que
precise operar ou explicar o sistema. Tudo aqui foi conferido no código, não é
lembrança: quando uma regra existe, o arquivo que a impõe está citado.

**Painel:** https://urace-bridge.duckdns.org/ops/
**Última revisão:** 17/09/2026 · 207 testes automatizados passando

---

## 1. O que o Command Center é (e o que ele não é)

É a **mesa de operação** da URACE. Ele não substitui Asana, DocuSign, Gmail,
QuickBooks e Kommo: ele **espelha** esses sistemas, mostra tudo em um lugar,
deixa a IA propor o que fazer e **guarda quem decidiu o quê**.

Três frases que explicam o sistema inteiro:

1. **Nada é inventado.** Toda tela mostra o que foi lido das fontes. Quando uma
   fonte não responde, a tela diz que não respondeu — não preenche com palpite.
2. **A IA propõe, a pessoa decide.** Ação que sai da empresa (waiver, invoice)
   nunca executa sozinha. A política de cada ação está numa tabela do banco, não
   no humor do modelo.
3. **Tudo fica registrado.** `audit_logs` é imutável: gatilhos no SQLite impedem
   `UPDATE` e `DELETE`. Login, comando, aprovação, rejeição e mudança de papel
   ficam lá para sempre.

O que ele **não** faz: não envia e-mail livre (o Gmail é leitura + rascunho), não
apaga nada pela IA, não mexe nos projetos **ADM URACE** e **Matt tasks** do Asana
(só leitura, decisão do dono), e não usa Turo nem Hostaway para nada.

---

## 2. Entrar

1. Abra https://urace-bridge.duckdns.org/ops/
2. E-mail e senha que o administrador cadastrou. Mínimo de 5 caracteres — o que
   segura a porta é o bloqueio por tentativas, não o tamanho da senha.
3. "Manter conectado por 30 dias" é opcional; sem isso a sessão dura 12 horas.

Regras de segurança que já estão valendo (`command_center/api/auth.py`):

| Regra | Como funciona |
|---|---|
| Senha | `scrypt` com sal por usuário. O sistema nunca guarda a senha, nem de forma reversível. |
| Sessão | token aleatório no cookie; no banco fica só o SHA-256 dele. Revogar vale na hora. |
| Cookie | `HttpOnly` + `Secure` + `SameSite=Strict`; toda mutação exige o header `X-CSRF`. |
| Erro de login | a mensagem é sempre a mesma ("Invalid email or password"), nunca revela se o e-mail existe. |
| Tentativas | 5 erros em 15 minutos por IP **e** por e-mail travam o acesso por alguns minutos. |
| Trocar a senha | derruba todas as sessões daquela pessoa. |

**Esqueci a senha:** não existe autoatendimento. Um administrador redefine em
**Usuários**. (Por decisão do dono, a tela de login não tem essa instrução escrita.)

---

## 3. Quem acessa o quê

| Quem | Alcança | Não alcança |
|---|---|---|
| **Acesso livre** (hoje `eduardoffresende@gmail.com`) | tudo, e **sem cargo**: o painel mostra "Acesso livre" no lugar do papel | — (e ninguém consegue trocar o papel dessa conta) |
| **Administrador** | tudo: usuários, políticas da IA, integrações, auditoria, financeiro, vendas, dia a dia | — |
| **Gerente** | tudo do operador + financeiro (QuickBooks, invoices) e auditoria; aprova qualquer proposta da IA | usuários e políticas |
| **Operador** | o dia a dia **e as vendas**: clientes, serviços, waivers, e-mails, chat, corridas, oportunidades e a IA — **e aprova o que a IA propõe nesses módulos** | financeiro (QuickBooks e invoice), auditoria, usuários, políticas |
| **Leitura** | vê tudo o que a tela mostra | não escreve nada |

**Quem vende é operador.** Não existe papel "vendas": a área de vendas é uma tela
do operador como qualquer outra (correção do dono em 17/09 — *"vendas e operador
devem ser a mesma coisa, com os acessos de operador"*). Todos os operadores veem
todas as oportunidades; o botão **Só minhas / Todas** no quadro é filtro de tela,
não trava.

Onde isso está no código: os papéis em `auth.PAPEIS` / `auth.NIVEL`; a conta de
acesso livre em `auth.ACESSO_LIVRE` (ajustável pela variável `CC_ACESSO_LIVRE`,
e-mails separados por vírgula); quem pode decidir cada proposta em
`ia.pode_decidir`.

---

## 4. O painel, tela por tela

### O menu, e a tela

O menu lateral **abre e fecha** pelo botão de painel na barra de cima (o segundo
ícone, ao lado da busca). Fechado, ele vira um **trilho de ícones**: o contador de
cada item continua ali, como uma bolinha colorida. **Encoste o mouse no trilho** e o
menu inteiro aparece por cima da página — o conteúdo não se mexe. O jeito como você
deixou o menu **fica guardado naquele navegador**: quem fecha encontra fechado.

Em monitor grande, as páginas de **leitura** (ficha do cliente, manual dos
marcadores, o que a IA pode fazer, minha conta) têm largura máxima, para a linha de
texto não ficar cansativa; **quadro, tabela larga, calendário e chat** usam a tela
inteira.

No **celular** o menu é uma gaveta que entra por cima, pelo botão de três linhas, e
embaixo fica a barra de abas (Hoje, Atenção, Vendas, IA, Mais). Toda tela é montada
para a largura do aparelho: nada rola para o lado sem querer, tabela larga vira
cartão ou rola dentro do próprio quadro, e o calendário do Asana abre na **Lista**
(o mês fica a um toque).

### Hoje (`/ops/`)
A abertura do dia: serviços de hoje, o que vence, invoices abertas (gerente e
acima), integrações e os itens que precisam de atenção.

### Precisa de atenção (`/ops/attention`)
A fila do que dói, ordenada por impacto: waiver que voltou, serviço sem waiver,
invoice vencida, lead esperando resposta, retorno de venda atrasado. Cada item
tem o balão **"Instruir a IA"**: você escreve (ou dita) o que fazer com aquele
item e a IA age com o contexto do cliente. O que você escreve ali pode ficar
guardado na memória da IA.

### Vendas
- **Oportunidades** (`/ops/sales`) — o quadro de vendas, uma coluna por etapa:
  Novo → Em conversa → Proposta → Fechamento → Ganho / Perdido. Em cima, os
  números do dia (abertas, retornos de hoje, atrasados, valor em proposta e em
  fechamento) e o botão **Só minhas / Todas**.
- **Agenda de vendas** (`/ops/sales/agenda`) — os retornos marcados em cada
  ligação, agrupados por dia; atrasado em vermelho.
- **Chat do Kommo** (`/ops/crm/chat`) — a conversa do lead dentro do painel, com
  os dados que o Kommo mostra ao lado, favoritos, e o botão **"Passar para o
  closer"**, que transforma o lead em oportunidade (a pessoa que vende — não é um
  papel do sistema).
- **Funil do Kommo** (`/ops/crm/funil`) — as etapas do funil espelhadas.

O fluxo completo da venda está no item 5.

### Clientes (`/ops/clients` e `/ops/clients/:id`)
Um card por pessoa. Regras que valem aqui: **corrida não é cliente**; "ativo" é
quem teve serviço nos últimos 6 meses; a ordem é por serviço mais recente. Cards
duplicados só são unidos quando têm o mesmo e-mail, telefone ou responsável — fora
disso a ação recusa e vira decisão humana. O card tem varredura de Gmail +
DocuSign daquele cliente.

### Sistemas (o espelho de cada ferramenta)
- **Asana** (`/ops/asana`) — calendário, quadro, lista e a tarefa por dentro
  (descrição, campos, subtarefas, anexos, comentários), com a caixa da IA dentro
  do modal da tarefa. Serviço novo nasce do **modelo oficial**, na coluna do dia.
- **DocuSign** (`/ops/docusign`) — waivers: baixar o PDF assinado, reenviar
  corrigindo o e-mail, anular envelope em aberto, lixeira, aba de assinadas e os
  documentos internos separados. `delivered` **não é** assinado.
- **Gmail** (`/ops/gmail`) — três colunas: marcadores, lista, corpo. A IA sugere o
  marcador; o botão **Mover** aplica e tira da caixa de entrada. O manual dos
  marcadores (`/ops/gmail/manual`) é a fonte: **a IA não cria marcador**, só sugere.
- **QuickBooks** (`/ops/quickbooks`) — invoices, lembretes recorrentes e o
  catálogo. O cliente é o **responsável**, nunca o piloto. A **Rate Card manda**
  acima do catálogo.

### Inteligência
- **AI Command** (`/ops/ai`) — a conversa contínua com o agente. Enter envia,
  Shift+Enter quebra linha, o microfone dita e o botão **Ouvir** lê a resposta.
- **Aprovações** (`/ops/approvals`) — a fila de propostas. Cada uma mostra a
  prévia do que vai acontecer e, quando você não pode decidir aquela, o motivo.
- **Automação e memória** (`/ops/automation`) — as rotinas automáticas e o que a
  IA aprendeu (cada aprendizado pode ser desligado).
- **O que a IA pode fazer** (`/ops/ai/capabilities`) — lido do código e da tabela
  de políticas, nunca escrito à mão: ferramenta por ferramenta, com a política.
- **Atividade da IA** (`/ops/activity`) — tudo que a IA fez, em ordem.

### Administração
- **Integrações** (`/ops/integrations`) — estado de cada fonte, sincronizar agora
  e o botão **Atualizar agora** (item 8).
- **Auditoria** (`/ops/audit`, gerente+) — o registro imutável.
- **Políticas da IA** (`/ops/policies`, administrador) — a política de cada ação.
- **Usuários** (`/ops/users`, administrador) — criar, desativar, mudar papel.
- **Minha conta** (`/ops/account`) — trocar a própria senha e o tema.

---

## 5. O fluxo da venda, passo a passo

**Oportunidade não é cliente.** Ela vive em `opportunities`, separada de
`clients`, e só vira card de cliente quando a venda fecha.

1. **Nova oportunidade** — durante a ligação, só o nome é obrigatório; todo campo
   aceita ditado. Se o e-mail já for de um cliente, o painel avisa na hora.
2. **Registrar ligação** — resultado (fechou, vai pensar, não atendeu, sem
   interesse, remarcou), minutos, o que a pessoa falou (ditado) e o próximo
   passo com data. A etapa se move sozinha: "vai pensar" leva para Em conversa,
   "fechou" leva para Fechamento e abre a tela de fechar.
3. **Retorno** — o que você marcou aparece na Agenda de vendas e, quando atrasa,
   em Precisa de atenção.
4. **Fechar venda** — uma tela. À esquerda o que foi vendido (editável,
   ditável); à direita a lista do que acontece ao confirmar, cada linha com uma
   chave para desligar:

   | Passo | O que faz |
   |---|---|
   | Card do cliente | cria ou liga ao card existente (mesmo e-mail ou telefone), com responsável, piloto, contato e anotação |
   | QuickBooks | acha ou cria o cliente e envia a invoice do valor fechado |
   | Waiver | DocuSign no modelo certo: parental se o piloto é menor, adulto se não |
   | Asana | tarefa no quadro U-RACE com a data do serviço |
   | Kommo | o lead do chat vai para "Closed won" |
   | Tarefa personalizada | o que mais você escrever: lembrete no painel ou tarefa no Asana |

   Depois de confirmar, **a mesma tela vira acompanhamento**: cada linha mostra
   feito, aguardando ou falhou, com "tentar de novo" ao lado. Falha de um passo
   nunca derruba os outros.

5. **Valor fora da tabela** — a venda fecha, o resto sai, e **a invoice fica
   esperando a aprovação do dono**. Administrador e gerente passam direto.
6. **Falar com a IA na ficha** — a caixa dentro da oportunidade: você dita e ela
   registra a ligação, marca retorno, anota, move etapa, cria tarefa, manda
   waiver ou fecha a venda, sempre naquela oportunidade.

Travas que o servidor impõe (`command_center/api/vendas.py`):
"Ganho" não sai pela mão (é resultado do fechamento); "Perdido" exige motivo;
sem e-mail, waiver e invoice recusam com texto claro em vez de fingir envio.

---

## 6. Falar e ouvir (voz)

Todo campo de texto do painel tem microfone, e a resposta da IA tem **Ouvir**.
É o reconhecimento de fala **do próprio navegador** (`components/Voz.tsx`):
nenhuma chave nova, nada sai para servidor nosso.

- **Onde funciona:** Chrome e Edge no computador, Safari 14.5+ no iPhone. Onde o
  navegador não tem o recurso, o botão simplesmente não aparece.
- **Como usar:** clique no microfone e fale; o texto vai aparecendo enquanto você
  fala. Clique de novo para parar. No primeiro uso o navegador pede permissão.
- **Detalhe útil:** em campo de e-mail, dizer "arroba" vira `@` e os espaços caem.
- **Onde tem:** AI Command, IA da venda, IA na tarefa do Asana e no item de
  atenção, chat do Kommo (resposta e anotação), anotações de venda e de cliente,
  novo cliente, nova oportunidade, nova tarefa de serviço, corridas, equipamento,
  memória da IA, manual dos marcadores e o campo dos diálogos de confirmação.

---

## 7. Como a IA trabalha

```
fontes (Asana, DocuSign, Gmail, QuickBooks, Kommo)
   → espelho no banco, a cada 15 min (CC_AUTOSYNC_MIN) ou no botão
   → o que mudou vira evento e acorda o agente, com o contexto do cliente e a memória
   → o agente responde e declara as ações que faria
   → cada ação recebe a política da tabela action_policies
   → SAFE executa; CONFIRMAÇÃO/APROVAÇÃO esperam uma pessoa
   → aprovar executa na hora, auditado; rejeitar registra o porquê
```

As quatro políticas:

| Política | O que significa |
|---|---|
| `SAFE` | executa sozinha (leitura, registro interno, comentário, tarefa) |
| `REQUIRES_CONFIRMATION` | alguém precisa clicar; muda o estado de um sistema |
| `REQUIRES_APPROVAL` | **sai da empresa** ou é dinheiro: waiver, invoice, reenvio |
| `BLOCKED` | a IA nunca faz. Hoje: `docusign_void`, `qbo_apagar`, `apagar_cliente`. `apagar_qualquer_coisa` saiu daqui em 22/09: virou `REQUIRES_APPROVAL` e voltou a valer como **piso** para qualquer ação com apagar/excluir/deletar/remover no nome |

Ação que não está na tabela cai em `REQUIRES_CONFIRMATION` por padrão
(`ia._politica`) — o sistema erra para o lado de perguntar.

**Ações de venda** (a IA dentro da oportunidade): `venda_registrar_ligacao`,
`venda_agendar_retorno`, `venda_anotar`, `venda_mover_etapa`, `venda_tarefa`
(SAFE) · `venda_enviar_waiver`, `venda_fechar` (confirmação) ·
`venda_enviar_invoice` (aprovação do dono).

**Quem decide** (`ia.pode_decidir`): administrador, gerente e a conta de acesso
livre decidem tudo; o operador decide nos módulos dele — o que inclui vendas;
invoice e QuickBooks nunca saem do gerente para cima. Leitura não decide nada.

---

## 8. Atualizar o sistema

**Pelo painel (jeito curto):** Integrações → **Atualizar agora** (só
administrador). O painel escreve um pedido em `~/.urace/deploy.request`; o
`urace-deploy.path` vê o arquivo e roda o `urace-deploy.service`, que faz
`git pull` e chama o mesmo script de deploy — numa unit separada, então reiniciar
o serviço no meio não mata o deploy. O log aparece ao vivo no cartão.

**Pelo terminal (quando precisa ver tudo):**

```bash
cd ~/Uraceagent && git fetch origin claude/configurar-open-claw-ooqo8x && git checkout claude/configurar-open-claw-ooqo8x && git pull origin claude/configurar-open-claw-ooqo8x && bash adminai/deploy/command_center/servir_command_center.sh
```

O deploy roda solto do terminal (`setsid nohup`), grava em
`~/.urace/deploy-<data>.log` e sobrevive à queda do SSH. Se a conexão cair:
`tail -n 60 "$(ls -t ~/.urace/deploy-*.log | head -1)"`.

O que o script faz, em ordem: venv → `npm ci && npm run build` → **pytest** (se
um teste falha, o deploy para) → primeiro ADMIN se não houver ninguém → unit
systemd em `127.0.0.1:8790` → bloco `/ops` no Caddy → prova real (`/ops/` 200,
API sem sessão 401, páginas legais 200).

**Trocar a foto do login:** coloque o arquivo em
`command_center/web/public/pista.jpg` (JPG, ~2000 px de largura, abaixo de
400 KB) e rode o deploy. Sem o arquivo, o login mostra um fundo escuro de
asfalto — nada quebra.

---

## 9. As regras que o sistema impõe (não são pedidos ao modelo)

| Regra | Onde é imposta |
|---|---|
| A IA não envia e-mail livre | política `gmail_enviar = BLOCKED`; o Gmail do painel é leitura + rascunho |
| A IA nunca apaga | políticas `*_apagar = BLOCKED` |
| Invoice só depois de aprovada | `qbo_*_invoice = REQUIRES_APPROVAL`; a prévia é obrigatória na aprovação |
| Waiver tem travas no servidor + aprovação | `adminai/mcp/docusign_mcp.py`: recusa sem `idade_confirmada`, sem `nome_email_conferidos`, com modelo errado ou com e-mail do domínio da URACE |
| Invoice fora da tabela é do dono | `vendas._confere_preco` + `pode_decidir` |
| ADM URACE e Matt tasks: só leitura | regra do dono dentro do `asana_mcp` |
| Auditoria não se apaga | gatilhos no SQLite contra `UPDATE`/`DELETE` em `audit_logs` |
| Tudo no fuso da Flórida | `America/New_York` no servidor (`vendas.hoje_local`, `dia_local`, `quando_pt`) e no frontend (`components/fmt.ts`) |
| Segredo nunca no repositório | tokens em `~/.urace/*.env` no VPS |

---

## 10. Quando algo dá errado

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| "Sem conexão com o servidor" no login | serviço parado | no VPS: `sudo systemctl status urace-command-center` e `journalctl -u urace-command-center -n 50` |
| Tela diz "Kommo não conectado" | token expirado (401) | conferir `~/.urace/kommo.env` e sincronizar em Integrações |
| Chat do Kommo sem o texto das mensagens | webhook da conta desligado | Kommo → Configurações → Webhooks → "Incoming message received" (ou "All") apontando para o painel |
| Mensagem do painel não chega ao lead | falta `KOMMO_BOT_ID` ou o Salesbot | seguir o cartão "Ligar o chat" na própria tela do chat |
| Passo do fechamento falhou | integração fora do ar ou dado faltando | a linha mostra o motivo; corrigir e clicar em "tentar de novo" |
| A foto do login não aparece | arquivo ausente ou não publicado | conferir `command_center/web/public/pista.jpg` e rodar o deploy |
| Microfone não aparece | navegador sem reconhecimento de fala | usar Chrome/Edge no computador ou Safari no iPhone |
| Deploy "verde" mas nada mudou | build antigo em cache do navegador | recarregar com Ctrl+Shift+R |

---

## 11. Para a IA (bloco estruturado)

Se você é um modelo operando este sistema, comece por aqui. Os caminhos são
relativos à raiz do repositório `UraceUs/Uraceagent`, branch
`claude/configurar-open-claw-ooqo8x`.

**Onde o código está**

| Parte | Arquivo |
|---|---|
| Autenticação, RBAC, auditoria | `command_center/api/auth.py` |
| Rotas principais e dashboard | `command_center/api/rotas.py` |
| App, arquivos do build, cabeçalhos | `command_center/api/main.py` |
| Vendas (oportunidades, fechamento) | `command_center/api/vendas.py` |
| Ações do painel e de venda | `command_center/api/acoes_painel.py` |
| Motor da IA (contexto, execução) | `command_center/api/motor.py` |
| Conversa com o agente, políticas, aprovação | `command_center/api/ia.py` |
| Normalização de argumentos de ação | `command_center/api/acoes.py` |
| Chat e funil do Kommo | `command_center/api/crm.py` |
| Atualizar o sistema | `command_center/api/sistema.py` |
| Schema e migrações | `command_center/db/schema.sql`, `command_center/db/__init__.py` |
| Frontend | `command_center/web/src` (`pages/`, `components/`, `styles/`) |
| Servidores MCP das fontes | `adminai/mcp/*_mcp.py` |
| Deploy | `adminai/deploy/command_center/` |

**Endpoints que importam** (prefixo `/ops/api`)

`POST /auth/login`, `POST /auth/logout`, `GET /auth/me` ·
`GET /dashboard` · `GET /needs-attention`, `POST /needs-attention/instruct` ·
`GET /clients`, `GET /clients/{id}` ·
`GET /sales/board` (`?minhas=1`), `GET /sales/agenda`, `GET /sales/{id}`, `POST /sales`,
`PATCH /sales/{id}`, `POST /sales/{id}/call`, `POST /sales/{id}/next`,
`POST /sales/{id}/note`, `POST /sales/{id}/stage`, `POST /sales/from-lead/{lead}`,
`POST /sales/{id}/close`, `POST /sales/{id}/step/{passo}` ·
`GET/POST /crm/leads...`, `GET /crm/leads/{id}/detail` ·
`POST /ai/commands`, `GET /ai/commands/{id}`, `GET /ai/actions`,
`POST /ai/actions/{id}/approve`, `POST /ai/actions/{id}/reject`,
`POST /ai/actions/{id}/complete`, `GET /ai/capabilities` ·
`GET /users`, `POST /users`, `POST /users/{id}/role` ·
`GET /audit` · `GET/POST /system/update`

Toda mutação exige o header `X-CSRF` igual ao cookie `cc_csrf`.

**Protocolo das ações.** O agente termina a resposta declarando, uma por linha:

```
ACAO: <ferramenta> | <alvo> | <resumo> | {"json":"com os argumentos exatos"}
```

O painel lê essas linhas (`ia.extrair_acoes`), aplica a política, e só executa o
que a política permite. Dentro de uma oportunidade, o comando começa com
`[oportunidade #N — nome]` e o painel injeta o contexto da venda com o formato
exato de cada `ACAO` (`motor.contexto_da_venda`).

**Invariantes que não se negociam**

1. Resposta 200 de uma API externa **não é prova** de que algo aconteceu: confira
   na fonte.
2. Nunca escreva segredo no repositório. Credencial vive em `~/.urace/*.env`.
3. Nunca invente dado para preencher tela: a ausência é informação.
4. Data e hora em `America/New_York`.
5. Ação nova nasce com política; sem política, é confirmação obrigatória.
6. `audit_logs` é imutável — não tente contornar.
7. ADM URACE e Matt tasks: leitura.

**Como testar antes de entregar**

```bash
python3 -m pytest command_center/tests -q          # 207 testes
cd command_center/web && npx tsc --noEmit -p tsconfig.app.json && npm run build
```

---

## 12. Onde mais ler

- **Decisões do dono** (o porquê de cada regra): `brain/08_DECISOES/`
- **Diário** (o que aconteceu, dia a dia): `brain/30_DIARIO/`
- **Identidade visual** ("Pit Wall Glass"):
  `brain/08_DECISOES/D-2026-09-17 - Identidade Pit Wall Glass (iOS x F1).md`
- **Fluxo da venda, voz e acesso livre**:
  `brain/08_DECISOES/D-2026-09-17 - Fluxo do closer, voz no painel e acesso livre.md`
- **ADR do Command Center**: `docs/adminai/command-center-adr.md`
- **Parâmetros operacionais**: `docs/adminai/parametros-operacionais.md`
- **Preferências do dono** (como ele quer ser respondido e o que nunca fazer):
  `brain/00_SYSTEM/Preferencias do dono.md`
