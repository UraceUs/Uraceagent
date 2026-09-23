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
