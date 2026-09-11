# Configurar o OpenClaw (via Clawdi ou self-host)

O OpenClaw é um assistente pessoal open-source que conversa por WhatsApp,
Telegram e outros canais. Ele precisa de um modelo por trás — sua conta
Anthropic entra aí, por **assinatura** (Claude Pro/Max) ou por **chave de
API** (console.anthropic.com, cobrança por uso).

Há três jeitos de rodar: **hospedado na Clawdi** (cloud.clawdi.ai — sem
gerenciar servidor), **VPS da Amazon via Lightsail** (blueprint oficial —
foi o caminho que usamos em produção) ou **self-host** (VPS próprio). Em
todos os casos, a conexão com a conta Anthropic funciona igual.

---

## Caminho 1 — Clawdi (cloud.clawdi.ai)

A Clawdi é OpenClaw gerenciado: cada usuário recebe uma VM dedicada com o
OpenClaw instalado, rodando 24/7, com os canais de mensagem pré-integrados
e suporte a **BYOK** (Bring Your Own Key — você usa sua própria conta
Anthropic).

1. **Entre em https://cloud.clawdi.ai/** com sua conta e crie/implante a
   instância do OpenClaw pelo painel.
2. **Conecte o modelo (BYOK).** O painel pede a credencial da Anthropic —
   ou você configura conversando com o próprio agente depois de implantado.
   As duas credenciais possíveis estão na seção
   [Conectar a conta Claude](#conectar-a-conta-claude) abaixo:
   chave de API (mais estável) ou setup-token da assinatura Pro/Max.
3. **Conecte os canais** (Telegram/WhatsApp) pelo painel — os passos de
   BotFather e QR code da seção [Canais](#canais-whatsapp--telegram)
   valem igual.
4. **Ative a allowlist** de contatos antes de divulgar o bot (seção de
   segurança abaixo).

Como a VM é uma instalação completa do OpenClaw, os comandos
`openclaw models auth add`, `openclaw models status` e
`openclaw channels login` funcionam nela se o painel der acesso a um
terminal/CLI da instância.

---

## Caminho 2 — VPS Amazon (Lightsail, blueprint oficial) ✅ testado

Foi o caminho usado em produção. A AWS tem um **blueprint pronto do
OpenClaw** no Lightsail: a instância já vem com OpenClaw, Node e painel
web instalados. Custo fixo (~US$ 12/mês no plano de 2 GB) + o uso da sua
chave Anthropic. Tudo se faz pelo navegador — console AWS e terminal SSH
web; nada é instalado na sua máquina.

### 2.1 Criar a instância

1. [lightsail.aws.amazon.com](https://lightsail.aws.amazon.com) →
   **Create instance** (qualquer região serve; us-east-1 é a mais completa).
2. Plataforma **Linux apps** → blueprint **OpenClaw**.
3. Plano com **mínimo 2 GB de RAM**.
4. Criar e aguardar o status **Running**.
5. **Attach Static IP** (aba da instância — grátis enquanto anexado).
   Sem isso o IP muda a cada stop/start e o painel/pareamentos quebram.

### 2.2 Parear o painel web

1. Aba **Connect** → **Connect using SSH** (terminal no navegador).
2. O terminal mostra a URL do painel (`https://SEU-IP/overview`) e o
   **Access Token** — cole o token no campo "Token do Gateway" do painel.
3. O painel pede aprovação do dispositivo; aprove no terminal:
   `openclaw devices approve <id-mostrado-no-painel>`.
4. Reconecte. Para recuperar o token depois: ele fica em
   `gateway.auth.token` no `~/.openclaw/openclaw.json`.

### 2.3 Atualizar o OpenClaw (necessário antes de tudo)

O blueprint vem com versão defasada, e o plugin do WhatsApp exige
runtime mais novo. O botão de update do painel **não funciona** neste
blueprint (`managed-service-handoff-unavailable`); o `openclaw update`
também falha por permissão (EACCES). O caminho que funciona:

```bash
openclaw gateway stop
sudo npm i -g openclaw@latest
openclaw gateway install --force
openclaw gateway restart
openclaw --version   # confirmar versão nova
```

### 2.4 Trocar o cérebro de Bedrock para a sua chave Anthropic

O blueprint vem travado no Amazon Bedrock: `plugins.allow` no
`~/.openclaw/openclaw.json` contém só `["amazon-bedrock"]`, o que bloqueia
o plugin da Anthropic ("blocked by allowlist"). Correção:

1. Edite o `~/.openclaw/openclaw.json` e acrescente `"anthropic"` e
   `"whatsapp"` ao array `plugins.allow`.
2. `openclaw plugins enable anthropic && openclaw gateway restart`
3. Registre a chave e escolha o modelo:
   ```bash
   openclaw onboard --anthropic-api-key "sk-ant-api03-..."
   ```
   No wizard: Setup mode **QuickStart** → Default model
   `anthropic/claude-sonnet-5` → canais: Skip.
4. Depois que tudo funcionar, desative o Bedrock:
   `openclaw plugins disable amazon-bedrock && openclaw gateway restart`

Atenção: no `openclaw models auth add`, o método **setup-token** espera
token de assinatura (`sk-ant-oat01-...`); para chave de API
(`sk-ant-api03-...`) use o flag do onboard acima ou o método "API key".

### 2.5 WhatsApp

**Instale o plugin pelo ClawHub, nunca por caminho local.** Plugin
carregado por path fica em capability mode `plain` e o canal morre com
`error: openKeyedStore is only available for trusted plugins`. Se isso
acontecer (sintoma: `linked` mas `stopped/not-running`):

```bash
# limpar instalação por path (ajuste se houver entrada em plugins.load.paths)
rm -rf ~/.openclaw/extensions/whatsapp
openclaw plugins install clawhub:@openclaw/whatsapp
openclaw gateway restart
```

Pareamento e allowlist:

```bash
openclaw channels login --channel whatsapp
```

- O QR aparece no terminal; se a câmera não pegar (QR de terminal é
  ruim), abra `https://SEU-IP/channels` no painel — lá ele renderiza
  como imagem nítida. QR expira em <1 min; gere outro se passar.
- Informe seu número no formato internacional; a **allowlist** é criada
  com ele (`dm:allowlist, allow:<numero>`), e só esse número comanda o
  agente.
- Pareamento por código (sem QR) ainda não existe no OpenClaw
  (issue #81889).

Verificação final — a linha deve ficar assim:

```
WhatsApp default: enabled, configured, linked, running, connected, health:healthy
```

### 2.6 Notas de operação

- Terminal web da Lightsail: **Ctrl+V não cola** — use o ícone de
  prancheta (canto inferior direito) + botão direito, ou Ctrl+Shift+V.
  Linhas longas renderizam por cima umas das outras (`Ctrl+L`/`reset`
  limpam); confira a linha antes do Enter.
- O menu amarelo que aparece ao abrir o SSH (`openclaw-login`) é do
  blueprint e só oferece Bedrock — ignore, configure pelos comandos.
- Sessão do WhatsApp expira após ~14 dias sem uso: repita o
  `channels login` + QR.
- Reload/F5 no navegador não perde nada — tudo vive no servidor.
- Trocar o token do painel (ex.: se vazou em um print):
  `openclaw doctor --generate-gateway-token` e reconectar.

---

## Caminho 3 — Self-host

### Requisitos

- Um host Linux/macOS com Node.js 22+ (VPS, ou a própria máquina).

### Instalar

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

### Rodar o onboarding

```bash
openclaw onboard --install-daemon
```

O assistente guia tudo em uma sessão: autenticação do modelo, criação do
workspace, configuração do gateway e canais opcionais. O `--install-daemon`
deixa o gateway rodando como serviço.

---

## Conectar a conta Claude

Vale para os dois caminhos — na Clawdi, é a credencial que você informa no
painel ou no onboarding da instância.

### Opção A — assinatura Claude (Pro/Max)

O OpenClaw usa um *setup-token* gerado pelo Claude Code CLI (não pelo
console da Anthropic):

1. Em uma máquina onde o Claude Code está logado na sua conta:
   ```bash
   claude setup-token
   ```
   Copie o token gerado.
2. No host do OpenClaw:
   ```bash
   openclaw models auth add
   ```
   Escolha `anthropic` → `setup-token` → cole o token.
3. Reinicie o gateway e abra um chat novo.

Se o Claude Code já está logado **no mesmo host** do OpenClaw, o onboarding
reaproveita esse login diretamente — nem precisa do token.

Atenção: o token de assinatura expira e pode ser revogado. Se o agente parar
de responder depois de um tempo, gere um token novo e repita o passo 2.

### Opção B — chave de API

Mais estável para rodar em servidor:

```bash
openclaw onboard --anthropic-api-key "$ANTHROPIC_API_KEY"
```

ou, no onboarding interativo, escolha `anthropic` → `api-key`.

### Verificar

```bash
openclaw models status
```

E, num chat, pergunte: "What auth are you using right now?".

Nota: a autenticação é **por agente**. Agente novo não herda as credenciais
do principal — repita o onboarding para ele, ou configure a chave de API no
host do gateway.

## Canais (WhatsApp / Telegram)

- **Telegram** é o mais rápido: crie um bot com o @BotFather, informe o
  token no onboarding.
- **WhatsApp** exige pareamento por QR code e guarda estado em disco.

**Configure a allowlist antes de divulgar qualquer número ou bot.** Sem ela,
qualquer pessoa que conheça o número/bot pode mandar comandos para o agente —
que roda com acesso ao seu servidor.

## Segurança — leia antes de ligar

- O OpenClaw executa ações reais no host. Na Clawdi a VM dedicada já isola
  isso; no self-host, rode em um servidor isolado (VPS dedicado ou
  container), nunca em máquina com credenciais de produção.
- Allowlist de contatos sempre ativa.
- Se usar a chave de API, trate-a como o `.env` deste repo: fora do git,
  restrita ao host.

## Relação com o agente URace

O OpenClaw **não substitui** o agente de vendas deste repositório: os portões
(preço, idade, escalada) vivem no Postgres/orchestrator e continuam valendo
apenas no fluxo Kommo/n8n descrito no README. O OpenClaw serve como
assistente pessoal/operacional seu — por exemplo, para consultar o estado do
sistema ou tarefas do dia a dia — usando a mesma conta Anthropic.

---

Referências: docs.openclaw.ai (Getting started, Onboarding, Providers →
Anthropic, Channels).
