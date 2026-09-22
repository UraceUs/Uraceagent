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

## Cliente Kommo — não chame a API na mão

`agent/kommo_client.py` existe pra isso: ler lead, ler custom fields/pipelines,
atualizar campos, mover etapa, ler eventos (checagem de robô antes de mover em
lote), criar nota. Usa `KOMMO_TOKEN` (env) ou `~/.urace/kommo_token.txt` — a
mesma convenção de guarda de token desta seção.

```bash
python agent/kommo_client.py --self-test       # sem rede, sem token
python agent/kommo_client.py --whoami          # confirma que o token funciona
python agent/kommo_client.py --custom-fields   # lista os IDs reais dos campos
python agent/kommo_client.py --pipelines       # lista pipelines e etapas
```

```python
from agent.kommo_client import KommoClient
client = KommoClient()
lead = client.get_lead(12345, with_=("contacts", "notes"))
client.update_lead(12345, custom_fields_values=[{"field_id": 1331943, "values": [{"value": 9}]}])
```

`send_native_channel_message()` propositalmente **lança erro** — a API do
Kommo não manda mensagem de Instagram/Facebook/WhatsApp, só o Salesbot ou a
tela manual. Isso é estrutural no código, não um lembrete de prompt: quem
tentar usa Salesbot ou a UI, nunca esse client.

## Regras operacionais aprendidas na marra

- **Cliente terminou o serviço → pedir review.** Depois que uma sessão
  (Arrive and Drive, Academy, etc.) acontece, o próximo passo padrão é pedir
  avaliação pro responsável (link do Google review). Não é opcional nem
  precisa ser pedido toda vez — é parte do ciclo de atendimento.
- **Nunca declare algo "pendente" (invoice não criada, pagamento faltando)
  sem checar o QuickBooks primeiro.** A nota do Asana pode estar
  desatualizada ou catalogar sob o nome do responsável, não do piloto —
  aconteceu com o Dinai Amankwa (invoice existia, mas sob "Nya Amankwa",
  a mãe). Buscar por família/responsável, não só pelo nome do piloto.
- **Threads marcadas "só o Lucas escreve" (Joseph Kurian, Syed Gillani, etc.)
  são reais e devem ser respeitadas por padrão** — mas o Italo, como dono,
  pode liberar exceção pontual explicitamente. Sempre perguntar antes de
  escrever numa thread congelada, mesmo com instrução direta do Italo —
  confirmar que ele sabe da trava antes de agir.
- **Ler o contexto antes de mandar qualquer mensagem, sempre** — card no
  Kommo, notas no Asana, histórico no Dialpad/e-mail, invoice no QuickBooks.
  Nunca escrever pra um lead ou cliente com base só no que foi pedido na
  hora; confirmar nome certo, o que já foi dito, o que já foi pago/assinado,
  antes de compor a mensagem.
