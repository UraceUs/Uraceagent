# Configurar o OpenClaw (via Clawdi ou self-host)

O OpenClaw é um assistente pessoal open-source que conversa por WhatsApp,
Telegram e outros canais. Ele precisa de um modelo por trás — sua conta
Anthropic entra aí, por **assinatura** (Claude Pro/Max) ou por **chave de
API** (console.anthropic.com, cobrança por uso).

Há dois jeitos de rodar: **hospedado na Clawdi** (cloud.clawdi.ai — sem
gerenciar servidor) ou **self-host** (VPS próprio). Nos dois casos, a
conexão com a conta Anthropic funciona igual, porque a Clawdi entrega uma
instalação completa do OpenClaw em uma VM dedicada.

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

## Caminho 2 — Self-host

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
