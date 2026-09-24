# Canal de DM (Instagram/Facebook/WhatsApp) e Remote Control

Documento de referência de 23/09/2026 — resultado de uma investigação ao
vivo, nesta sessão, sobre por que não dá pra responder DM direto pela API
do Kommo, e o que fazer pra ligar a função de clique/cursor (como a AZ
Car Rental usa) numa sessão futura. Ler antes de reabrir essa investigação.

## O que está fechado, confirmado ao vivo (não reabrir sem fato novo)

- `GET /api/v4/talks/{id}` funciona — mostra a conversa real (`chat_id`,
  `origin` tipo `instagram_business`, `source_id`).
- `GET /api/v4/talks/{id}/messages` devolve **403 "Invalid scope"**.
- A tela "Keys and scopes" do Kommo, pra integração privada
  ("URACE Claude Integration CPU"), **não tem seletor de escopo nenhum** —
  só secret key, ID e token de longa duração. Não existe opção pra marcar,
  nem gerando token novo.
- Acesso de escrita a canal nativo (Instagram/Facebook/WhatsApp via Kommo)
  é reservado a app aprovado no Marketplace do Kommo + revisão do Meta pra
  mensageria de negócio. Integração privada não consegue isso — é limite
  do produto, não de configuração.
- Os 17 bots/Salesbots da conta (`GET /api/v4/bots`) são todos de fluxo
  fixo (NPS, boas-vindas, aviso de horário, Black Friday, Command Center)
  — nenhum aceita texto livre composto na hora.

## O que É possível hoje, sem depender de nada disso

- `add_note()` (`agent/kommo_client.py`) — escrever nota interna no card.
  Isso **não é** mandar mensagem pro cliente — é o mesmo que o `nota.py`
  da operação irmã (AZ) faz: "alimenta o card", não "manda no chat".
  Confirmado lendo o histórico real de sessão da AZ (23/09) — o padrão
  deles também é ler/organizar/anotar e **a pessoa manda na tela**, não
  enviar automático (inclusive um e-mail redigido lá ficou esperando
  confirmação humana antes de sair).
- SMS via Dialpad API — funciona, testado com 19 envios reais.
- E-mail via Gmail MCP — funciona.

## Caminho ainda aberto, não fechado: API de canal customizado (amoJo)

Kommo roda sobre um motor de chat separado, `amojo.amocrm.ru` (achado
via `account.amojo_id` na resposta de `/api/v4/account?with=amojo_id`).
Existe, em tese, um fluxo de **canal customizado** (diferente do escopo de
canal nativo que já vimos fechado) que não passa pela revisão do Meta —
mas:

1. **`amojo.amocrm.ru` está fora da allowlist de rede desta sessão de
   nuvem** (`CONNECT tunnel failed, 403`). Pra testar, adicionar em
   Nuvem → engrenagem do ambiente → Acesso à rede → Domínios permitidos:
   ```
   amojo.amocrm.ru
   *.amocrm.ru
   amojo.amocrm.com
   *.amocrm.com
   ```
2. Mesmo com a rede liberada, um canal customizado de verdade normalmente
   exige um registro próprio (`scope_id`/`secret_key` gerado num fluxo de
   desenvolvedor do Kommo, separado do token de "Keys and scopes" que já
   temos) — **não testado ainda**, não prometer que funciona antes de
   confirmar.

**Atualização 23/09, mesmo dia — rede já liberada, testado:** com
`amojo.amocrm.ru`/`amojo.amocrm.com` na allowlist, os dois hosts
respondem (deixaram de dar `CONNECT tunnel failed`). Mas
`GET /v2/origin/custom/{amojo_id}` e `GET /v2/chats/{chat_id}` com o
Bearer token da API v4 devolvem `404` vazio — o amoJo usa esquema de
autenticação próprio (normalmente assinatura HMAC com `secret_key` do
canal, não o Bearer token do Kommo). **Confirmado: falta mesmo o
registro de canal** — rede aberta não bastou. Sem esse `secret_key`
próprio, não tem endpoint a mais pra tentar por tentativa e erro.

## Função de clique/cursor (como a AZ opera) — via Remote Control

A AZ usa uma sessão de Claude Code **local** (Mac/Windows), com a
extensão **Claude in Chrome** instalada num navegador logado no
Kommo/Meta — essa sessão local clica e digita na tela de verdade. Isso
**não existe nesta sessão de nuvem** (sem navegador, sem login, sem
extensão) e não tem como replicar por aqui sozinho.

Pra ligar isso:

1. No computador de quem vai operar: instalar o Claude Code localmente e
   a extensão **Claude in Chrome** (Chrome Web Store), no mesmo perfil de
   navegador já logado no Kommo/Instagram/Meta Business Suite.
2. Abrir uma sessão do Claude Code local (não precisa ser na pasta deste
   repo).
3. Rodar o comando de Remote Control nessa sessão local pra ativá-lo.
4. A sessão local passa a aparecer pro `ListAgents` desta sessão de
   nuvem — dá pra mandar comando daqui pra ela executar clique/digitação
   de verdade.

Sem esse passo, `ListAgents` desta sessão sempre vai retornar "nenhuma
sessão alcançável" — não é bug, é a ausência real dessa ligação.

## Procedimento de envio por clique, quando o Remote Control estiver ligado

Portado de `ENVIO_POR_CLIQUE_KOMMO.md` da AZ (24/09) — as armadilhas já
custaram tempo real na operação irmã, não reaprender na marra aqui.
Adaptado: onde a AZ usa `kommo_pipe.py`, a URACE usa `agent/kommo_client.py`
(`add_note()` + `update_lead(status_id=...)`) — mesma ideia, tooling local.

**Antes de abrir a tela — decidir se vale abrir:**
1. O lead tem canal social conectado? Se só tem telefone, não é aqui —
   é SMS pelo Dialpad.
2. A última mensagem é DELE e tem menos de 24h? Mais velha, o Meta
   recusa e volta `Error` — não adianta mudar o texto, é a janela de
   24h do Meta, não o conteúdo.
3. Alguém mais já está nessa thread? Registrar quem pegou (nome, canal,
   hora) antes de escrever, pra dois agentes não abrirem a mesma
   conversa ao mesmo tempo (vira spam pro cliente).

**Passo a passo:**
1. Abrir o card pelo ID direto: `https://urace.kommo.com/leads/detail/<lead_id>`
   — o Kommo perde clique se você procurar o card pela lista.
2. Ler as duas últimas mensagens da thread na hora, na tela — nunca
   confiar no que foi lido minutos antes nem no espelho da API (que
   atrasa horas). O cliente pode ter escrito no meio.
3. Clicar no campo de escrita e conferir a aba **antes de digitar**. O
   compose do Kommo **volta sozinho pra "Nota interna"** — se escrever
   com a aba errada, o texto vira nota interna e o cliente não recebe
   nada, mas parece que mandou. Selecionar o canal (Instagram/Facebook)
   antes de digitar, confirmar de novo depois.
4. Escrever o texto de uma vez (inserir/colar, nunca digitação
   simulada caractere a caractere — corrompe o compose do Kommo, some
   caractere e quebra emoji). Reler na tela antes de mandar.
5. Enviar.
6. Confirmar a entrega **na própria tela** — a mensagem tem que virar
   **Delivered**. `Error` é quase sempre a janela de 24h; registrar e
   não tentar de novo. Só o `Delivered` prova que saiu — sem ele,
   considerar que não foi.
7. Registrar por API, não na tela:
   ```python
   from agent.kommo_client import KommoClient
   client = KommoClient()
   client.add_note(lead_id, "respondido no IG: <resumo> — Delivered HH:MM")
   client.update_lead(lead_id, status_id=<id_do_follow_up_1>)
   ```
   Depois lançar em `data/leads_master.xlsx`: fala literal, idade se
   veio, próximo passo — mesma disciplina do Passo 4 do
   `prompts/LOOP_URACE.md`.

**Armadilhas, todas já pagas (na AZ):**

| Armadilha | O que acontece | O que fazer |
|---|---|---|
| Compose volta pra "nota interna" | "manda" e o cliente não recebe nada | conferir a aba antes **e** depois de digitar |
| Digitação simulada corrompe o texto | mensagem sai truncada ou com lixo | inserir de uma vez, reler antes de mandar |
| Janela de 24h do Meta | volta `Error` | checar a última mensagem do cliente antes de abrir a tela |
| Reload na aba | derruba a sessão, ninguém aqui faz login de novo | ⛔ nunca dar reload |
| Print de tela pra ler a conversa | caro, lento, ainda erra | ler por API/JS; print só sem alternativa nenhuma |
| Dois agentes na mesma thread | cliente recebe duas aberturas, vira spam | registrar quem pegou, antes de escrever |

**O que nunca sai por aqui, nem com Remote Control ligado:** data
confirmada, desconto ou preço fora da tabela, waiver, caução, cobrança,
promessa de filmagem na pista — tudo isso é do Lucas/Italo. O agente
escreve o achado e para, mesmo com a tela na mão.

**Quando o SMS estiver sem crédito (Dialpad):** não existe contorno
técnico — é a mesma conta e a mesma carteira, API ou tela. Nesse caso
a saída é mudar de canal: responder quem está dentro da janela de 24h
no Instagram (de graça) e deixar o SMS em fila até alguém recarregar
em Settings → Billing do Dialpad.
