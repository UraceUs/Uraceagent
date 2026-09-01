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
| accountId | **outro** (a extensão vai reportar) | `4261a166-3a91-4fb7-97c5-30257d657c52` |
| userId | **outro** | `b3ef4ae4-917e-4394-96b4-e1e5498cc75b` |

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
cat > ~/.urace/docusign_private.key
# cole a chave inteira, incluindo as linhas BEGIN e END, e feche com Ctrl+D
```

Depois:

```bash
chmod 600 ~/.urace/docusign_private.key
head -1 ~/.urace/docusign_private.key
grep -c . ~/.urace/docusign_private.key
```

A primeira linha tem que ser `-----BEGIN RSA PRIVATE KEY-----`.
Se vier truncada, refazer — chave RSA pela metade não dá erro claro,
dá `invalid_grant`, que parece problema de permissão.

---

## Passo 4 — consentimento único do JWT

O JWT só funciona depois que um humano autoriza a aplicação uma vez.
Assim que a Integration Key existir, monto a URL de consentimento — ela
precisa da chave, então não dá para adiantar.

---

## Passo 5 — as ~20 chamadas de demo

O go-live exige um histórico de chamadas bem-sucedidas no ambiente demo
(a DocuSign pede 20 na documentação atual). As rotinas do agente já
fazem chamadas suficientes: basta apontar `DOCUSIGN_BASE_URI` para
`https://demo.docusign.net` por alguns dias com `APLICAR=0`.

Isso vale um aviso: enquanto estiver assim, **o agente não enxerga as
waivers reais**. É período de homologação, não de operação.

---

## Passo 6 — pedir o go-live

`admindemo.docusign.com` → Apps and Keys → o app → **Go Live**.
Depois de aprovado, trocar no `~/.urace/adminai.env`:

```bash
sed -i 's|^DOCUSIGN_BASE_URI=.*|DOCUSIGN_BASE_URI=https://na4.docusign.net|' ~/.urace/adminai.env
grep '^DOCUSIGN_' ~/.urace/adminai.env | sed 's/=.*/=<definido>/'
```
