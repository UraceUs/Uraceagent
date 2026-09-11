# Conectar o QuickBooks ao VPS (produção)

O agente roda no VPS; o conector do Claude não conta. Para o QuickBooks
real (URACE US INC, realm `9341453113046421`) falar com o VPS são três
coisas: **chaves de produção** do app na Intuit, **redirect URI** em
HTTPS, e **um consentimento** feito pelo Command Center.

## 1. Chaves de produção (developer.intuit.com)

Pré-requisito: o app precisa ter saído de `IN DEVELOPMENT`
(`docs/adminai/intuit-app-review.md` tem as respostas de cada campo;
as páginas legais já respondem em `https://urace-bridge.duckdns.org/legal/`).

Em *Dashboard → app → Keys & credentials → Production*:
- copie **Client ID** e **Client Secret**;
- em **Redirect URIs**, adicione exatamente:
  `https://urace-bridge.duckdns.org/ops/api/qbo/callback`

Se a aba Production ainda estiver com cadeado, o app não foi aprovado:
ver o que a Intuit está pedindo em *App details* e *Compliance*.
O prompt para a extensão fazer essa checagem está em
`adminai/deploy/prompts/quickbooks-producao.txt`.

## 2. Chaves no VPS (um bloco, no terminal do VPS)

Cole substituindo os dois valores. Nada entra no git; o arquivo é 600.

```
python3 - <<'PYEOF'
import re,os
p=os.path.expanduser('~/.urace/adminai.env'); s=open(p).read()
def put(k,v):
    global s
    s = re.sub(rf'^{k}=.*$', f'{k}={v}', s, flags=re.M) if re.search(rf'^{k}=', s, re.M) else s.rstrip('\n')+f'\n{k}={v}\n'
put('QBO_CLIENT_ID','COLE_AQUI_O_CLIENT_ID')
put('QBO_CLIENT_SECRET','COLE_AQUI_O_CLIENT_SECRET')
put('QBO_REALM_ID','9341453113046421')
open(p,'w').write(s); os.chmod(p,0o600); print('ok')
PYEOF
sudo systemctl restart urace-command-center && sleep 2 && curl -s -o /dev/null -w "ready %{http_code}\n" http://127.0.0.1:8790/ops/ready
```

## 3. Consentimento (no navegador, como ADMIN)

`https://urace-bridge.duckdns.org/ops/quickbooks` → **Conectar QuickBooks**.
A Intuit pede para escolher a empresa (URACE US INC) e autorizar. Ao
voltar, o painel mostra CONNECTED e o token fica em
`~/.urace/qbo-token.json`.

O refresh token **rotaciona a cada uso e vale 100 dias**. O MCP grava o
novo a cada refresh. Sem uso por 100 dias, refazer o passo 3.

## 4. Agente no VPS

O instalador registra o MCP `quickbooks` quando o token existe:

```
cd ~/Uraceagent && bash adminai/deploy/install_adminai.sh
```

## O que a IA pode

| Ação | Gate |
|---|---|
| ler empresa, clientes, itens, invoices, estimates, contas a receber | livre |
| criar cliente, item, invoice, estimate | confirmação no painel (`APLICAR=0` simula) |
| **enviar invoice** | **aprovação humana** no painel (D-2026-09-04) |
| apagar | **nunca** |
