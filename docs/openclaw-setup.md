# Configurar o OpenClaw com a sua conta Claude

O OpenClaw é um assistente pessoal open-source que roda em um servidor seu
(ou na sua máquina) e conversa por WhatsApp, Telegram e outros canais. Ele
precisa de um modelo por trás — e é aí que entra a sua conta Claude: você
conecta o OpenClaw à Anthropic por **assinatura** (Claude Pro/Max) ou por
**chave de API** (console.anthropic.com, cobrança por uso).

Este guia cobre a instalação, a conexão com a conta Claude e os cuidados de
segurança mínimos.

---

## 1. Requisitos

- Um host Linux/macOS com Node.js 22+ (VPS, ou a própria máquina).
- Uma conta Claude:
  - **Assinatura Claude Pro/Max** (claude.ai) — usa a franquia da assinatura,
    sem cobrança por token; ou
  - **Chave de API** da Anthropic (console.anthropic.com) — cobrança por uso.
    É a mesma `ANTHROPIC_API_KEY` do `.env.example` deste repositório.

## 2. Instalar

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

## 3. Rodar o onboarding

```bash
openclaw onboard --install-daemon
```

O assistente guia tudo em uma sessão: autenticação do modelo, criação do
workspace, configuração do gateway e canais opcionais. O `--install-daemon`
deixa o gateway rodando como serviço.

### Caminho A — assinatura Claude (Pro/Max)

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

### Caminho B — chave de API

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

## 4. Canais (WhatsApp / Telegram)

- **Telegram** é o mais rápido: crie um bot com o @BotFather, informe o
  token no onboarding.
- **WhatsApp** exige pareamento por QR code e guarda estado em disco.

**Configure a allowlist antes de divulgar qualquer número ou bot.** Sem ela,
qualquer pessoa que conheça o número/bot pode mandar comandos para o agente —
que roda com acesso ao seu servidor.

## 5. Segurança — leia antes de ligar

- O OpenClaw executa ações reais no host. Rode em um servidor isolado (VPS
  dedicado ou container), nunca em máquina com credenciais de produção.
- Allowlist de contatos sempre ativa.
- Se usar a chave de API, trate-a como o `.env` deste repo: fora do git,
  restrita ao host.

## 6. Relação com o agente URace

O OpenClaw **não substitui** o agente de vendas deste repositório: os portões
(preço, idade, escalada) vivem no Postgres/orchestrator e continuam valendo
apenas no fluxo Kommo/n8n descrito no README. O OpenClaw serve como
assistente pessoal/operacional seu — por exemplo, para consultar o estado do
sistema ou tarefas do dia a dia — usando a mesma conta Anthropic.

---

Referências: docs.openclaw.ai (Getting started, Onboarding, Providers →
Anthropic, Channels).
