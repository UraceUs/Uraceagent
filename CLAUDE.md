# Antes de fazer qualquer coisa neste repositório

Leia `docs/mapa-de-agentes.md`. Ele lista as sessões que operam sobre este
mesmo repositório — **U RACE**, **CRM**, **COMERCIAL**, **AGREGADOR** — e o
que cada uma faz. Você é uma dessas sessões (o nome da sessão, na barra
lateral do Claude Code, diz qual). Se não estiver claro qual, **pergunte ao
usuário antes de agir** — não assuma.

Leia também `docs/urace-ai-agent-arquitetura.md` para a arquitetura técnica
do agente de vendas em si (Orchestrator, schema, catálogo) — esse documento
está congelado como baseline, não edite sem necessidade real.

## Conectar no Kommo

Conta **Support Urace**, subdomínio `urace`: `https://urace.kommo.com/api/v4`,
header `Authorization: Bearer <token>`.

**Se você roda localmente** (Mac ou Windows — não numa sessão de nuvem do
Claude Code): sua rede é a rede normal da máquina, sem restrição. Só falta o
token.

**Se você roda numa sessão de nuvem** (Claude Code on the web, tipo esta
sessão "U RACE"): a rede é restrita por allowlist a nível de ambiente. Teste
antes de assumir que está bloqueado:

```bash
curl -o /dev/null -w "%{http_code}\n" https://urace.kommo.com
```

`401` = chegou no servidor, falta só o token (bom sinal). Erro de
`CONNECT tunnel failed` = domínio fora da allowlist — precisa adicionar
`kommo.com`, `*.kommo.com` e `api-g.kommo.com` nas configurações de rede do
ambiente (Nuvem → engrenagem do ambiente → Acesso à rede → Personalizado →
Domínios permitidos), depois salvar. `dialpad.com` tem o mesmo problema e,
até a data deste commit, **continuou bloqueado mesmo depois de adicionado**
— há indício de que existe também uma política a nível de organização, não
só de ambiente, para esse domínio específico. Não gaste tempo tentando de
novo sem antes confirmar isso em `claude.ai/admin-settings`.

**Gerar o token** (se ainda não tiver um): no Kommo, Configurações →
Integrações → Create integration → preenche Nome/Redirect URL (qualquer
`https://` válido, não precisa funcionar de verdade) → Save → aba
"Keys and scopes" → "Generate long-lived token". Ele só aparece **uma vez**
— copia na hora.

⚠️ **Nunca cole o token em código, commit ou neste repositório.** Guarde
fora do repo:
- Local (Mac/Windows): `~/.urace/kommo_token.txt` ou variável de ambiente
- Sessão de nuvem: campo "Credenciais de API" nas configurações do ambiente
  (Nuvem → engrenagem → Credenciais de API → Adicionar credencial) — assim
  a sessão chama a API sem o valor aparecer no transcript.

**Antes de criar qualquer campo customizado ou pipeline**, confira o que já
existe — `GET /api/v4/leads/custom_fields` e `GET /api/v4/leads/pipelines`
— pra não duplicar. Os 8 campos de qualificação (`interest`, `program`,
`experience`, `driver_age`, `budget`, `urgency`, `lead_score`,
`score_reason`) e o pipeline `Chase — AI Sales Funnel` (14316000) já
existem e estão mapeados em `db/002_seed_config.sql`.
