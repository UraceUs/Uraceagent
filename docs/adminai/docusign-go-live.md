# DocuSign: da conta demo até a chave de produção

A produção do DocuSign **não deixa criar Integration Key** (ver
`brain/13_PROBLEMAS/P-12 - Integration Key do DocuSign so nasce em conta demo.md`).
O caminho oficial é: criar a chave na **conta de desenvolvedor (demo)**,
fazer chamadas reais nesse ambiente, e pedir o **go-live** — a Intuit da
DocuSign chama isso de *promote to production*.

A chave é a mesma nos dois ambientes depois do go-live. O que muda são
**accountId, userId e base URI** — e é aí que mora a armadilha registrada
em `brain/40_SISTEMAS/DocuSign.md`.

| | Demo | Produção |
|---|---|---|
| Admin | `admindemo.docusign.com` | `admin.docusign.com` |
| Login | `account-d.docusign.com` | `account.docusign.com` |
| API | `https://demo.docusign.net` | `https://na4.docusign.net` |
| accountId | `d3cf672c-62f6-4c5c-bddb-7a3307a52123` | `4261a166-3a91-4fb7-97c5-30257d657c52` |
| userId | `4347151f-fe2a-4e6f-87df-e8457a00a7ff` | `b3ef4ae4-917e-4394-96b4-e1e5498cc75b` |

**Integration Key (o `client_id`):**
`126393c2-ae7a-4b73-9585-fed7e13cafe7` — app `URACE Administrative AI`,
criado em 01/09/2026. É a **mesma chave** depois do go-live; o que muda
é o `accountId` para o qual ela aponta.

⚠️ **Os 4 templates e os 39 envelopes reais estão na produção.** A conta
demo nasce vazia — isso é esperado, não é perda de dados.

---

## Passo 2 — prompt para a extensão

O bloco está em `adminai/deploy/prompts/docusign-integration-key.txt`.
Ele faz: confirmar o ambiente, criar o app, pegar a Integration Key,
cadastrar o Redirect URI e **avisar antes** de gerar o par de chaves RSA.

**A chave privada não pode ser colada em chat nenhum.** A extensão foi
instruída a não transcrevê-la: ela avisa quando a tela estiver aberta, e
quem copia é o dono, direto para o VPS.

---

## Passo 3 — a chave privada até o VPS (feito pelo dono)

Com a chave na tela do DocuSign, no VPS, num bloco só:

```bash
mkdir -p ~/.urace && chmod 700 ~/.urace
cat > ~/.urace/docusign-private.key
# cole a chave inteira, incluindo as linhas BEGIN e END, e feche com Ctrl+D
```

Depois:

```bash
chmod 600 ~/.urace/docusign-private.key
sed -i 's|^DOCUSIGN_INTEGRATION_KEY=.*|DOCUSIGN_INTEGRATION_KEY=126393c2-ae7a-4b73-9585-fed7e13cafe7|' ~/.urace/adminai.env
sed -i "s|^DOCUSIGN_PRIVATE_KEY_PATH=.*|DOCUSIGN_PRIVATE_KEY_PATH=$HOME/.urace/docusign-private.key|" ~/.urace/adminai.env
head -1 ~/.urace/docusign-private.key
openssl rsa -in ~/.urace/docusign-private.key -noout -check
```

A última linha é a prova: `RSA key ok`. Se ela falhar, a chave chegou
truncada ou com quebra de linha errada — e isso importa porque chave RSA
pela metade **não dá erro claro**: dá `invalid_grant`, que parece
problema de permissão e faz procurar no lugar errado por horas.

`DOCUSIGN_PRIVATE_KEY_PATH` no `.env.example` aponta para
`/home/ubuntu/...`; os `sed` acima usam `$HOME`, que resolve para o
usuário real do VPS.

---

## Passo 4 — consentimento único do JWT

O JWT não funciona enquanto um humano não autorizar a aplicação **uma
vez**, por ambiente. É um clique só, mas sem ele todo `invalid_grant`
parece problema de chave.

**Demo** — abrir logado em `account-d`, autorizar, e a página vai
redirecionar para a `privacy.html` com um `?code=` na URL. O código não
serve para nada aqui: o que importa é ter clicado em **Allow**.

```
https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=126393c2-ae7a-4b73-9585-fed7e13cafe7&redirect_uri=https://urace-bridge.duckdns.org/legal/privacy.html
```

**Produção** — só depois do go-live aprovado, e logado em `account`
(não em `account-d`):

```
https://account.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=126393c2-ae7a-4b73-9585-fed7e13cafe7&redirect_uri=https://urace-bridge.duckdns.org/legal/privacy.html
```

O escopo `impersonation` é o que permite o agente agir como o usuário
`support@urace.us` sem ninguém logar. É por isso que a chave privada RSA
é secreto de verdade.

---

## Passo 4b — provar o consentimento sem depender de memória

Quem clicou em Allow não precisa lembrar: a API responde. No VPS, uma
chamada direta ao servidor MCP, sem passar pelo agente:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"docusign_ambiente","arguments":{}}}' | URACE_ENV=$HOME/.urace/adminai.env timeout 60 python3 ~/Uraceagent/adminai/mcp/docusign_mcp.py 2>/dev/null | tail -1 | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];print(r['content'][0]['text'])"
```

| Resposta | Significa |
|---|---|
| `usuario: support@urace.us` + contas | consentimento dado, JWT vivo, chave certa |
| `consent_required` | falta o clique do Passo 4 |
| `invalid_grant` | chave privada não bate com a pública do app, ou `userId` errado |

## Passo 5 — as ~20 chamadas de demo

O go-live exige um histórico de chamadas bem-sucedidas no ambiente demo
(a DocuSign pede 20 na documentação atual). As rotinas do agente já
fazem chamadas suficientes: basta apontar `DOCUSIGN_BASE_URI` para
`https://demo.docusign.net` por alguns dias com `APLICAR=0`.

Isso vale um aviso: enquanto estiver assim, **o agente não enxerga as
waivers reais**. É período de homologação, não de operação.

---

## Passo 6 — pedir o go-live

**Estado em 02/09:** "Pending approval", faltando só o *verification
form* — um envelope que o **Italo assina**, com nome igual ao documento.
Valores para o envelope:

| Campo | Valor |
|---|---|
| Nome | Italo Jorge da Silveira |
| E-mail (admin da produção) | `support@urace.us` |
| **Production Account ID** | `4261a166-3a91-4fb7-97c5-30257d657c52` — o GUID, não `152293148`, não o do demo |
| Integration Key | `126393c2-ae7a-4b73-9585-fed7e13cafe7` |
| App | `URACE Administrative AI` · Private custom integration · JWT Grant |
| Empresa | URACE.US INC · 6149 Cyril Ave, Orlando, FL 32809 · (407) 250-2291 |
| Volume | ~15 envelopes/mês (39 desde junho) |
| Connect / embedded signing | Não / Não |

**02/09 14:43 — assinado.** Envelope `53FB5A34-…`, identidade verificada
por documento, na fila de *Go Live Execution*.

## Passo 7 — a virada para produção (só depois do e-mail de aprovação)

Confirmar primeiro no admin de **produção** (`admin.docusign.com` →
Apps and Keys) que o app `URACE Administrative AI` aparece lá com a
mesma chave. Só então, no VPS, num bloco só:

```bash
cp -a ~/.urace/adminai.env ~/.urace/adminai.env.antes-da-producao
sed -i 's|^DOCUSIGN_ACCOUNT_ID=.*|DOCUSIGN_ACCOUNT_ID=4261a166-3a91-4fb7-97c5-30257d657c52|' ~/.urace/adminai.env
sed -i 's|^DOCUSIGN_USER_ID=.*|DOCUSIGN_USER_ID=b3ef4ae4-917e-4394-96b4-e1e5498cc75b|' ~/.urace/adminai.env
sed -i 's|^DOCUSIGN_BASE_URI=.*|DOCUSIGN_BASE_URI=https://na4.docusign.net|' ~/.urace/adminai.env
grep '^DOCUSIGN_' ~/.urace/adminai.env | grep -v PRIVATE
```

Depois, **o consentimento de novo, agora em produção** — é por
ambiente, o do demo não vale aqui. Logado em `account` (não `account-d`):

```
https://account.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=126393c2-ae7a-4b73-9585-fed7e13cafe7&redirect_uri=https://urace-bridge.duckdns.org/legal/privacy.html
```

E a prova, pela mesma ferramenta:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"docusign_envelopes","arguments":{"status":"sent,delivered,completed","desde_dias":120}}}' | URACE_ENV=$HOME/.urace/adminai.env timeout 60 python3 ~/Uraceagent/adminai/mcp/docusign_mcp.py 2>/dev/null | tail -1 | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];t=r['content'][0]['text'];print(t[:600])"
```

Tem que vir `"ambiente": "PRODUÇÃO"` e `"total"` na casa dos 39. Se vier
`consent_required`, é o Allow de produção que faltou. Depois disso,
`openclaw mcp reload` e a varredura seguinte enxerga as waivers reais.

Depois da aprovação (até 48h):

`admindemo.docusign.com` → Apps and Keys → o app → **Go Live**.
Depois de aprovado, trocar no `~/.urace/adminai.env`:

```bash
sed -i 's|^DOCUSIGN_BASE_URI=.*|DOCUSIGN_BASE_URI=https://na4.docusign.net|' ~/.urace/adminai.env
grep '^DOCUSIGN_' ~/.urace/adminai.env | sed 's/=.*/=<definido>/'
```
