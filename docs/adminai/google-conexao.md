# Google: Gmail, Calendar e Sheets no VPS

Três coisas, nesta ordem: um **cliente OAuth** no Google Cloud (uma vez),
um **consentimento por caixa** (urace@ e support@), e o servidor MCP
(`adminai/mcp/gmail_mcp.py`) que o instalador registra sozinho.

## Por que aqui não tem fila de revisão

A URACE é Google Workspace (`urace.us`). Um app OAuth com público
**Internal** só pode ser autorizado por contas do próprio domínio — e
por isso o Google **não exige verificação**. É a única das três
conexões (QuickBooks, DocuSign, Google) sem terceiro no caminho.

Consequência prática: o refresh token de app interno **não expira em 7
dias** como o de app externo "em teste". Só morre se for revogado ou
ficar 6 meses sem uso.

## Passo 1 — o cliente OAuth (prompt para a extensão)

`adminai/deploy/prompts/google-oauth-client.txt`. Resultado: um arquivo
`client_secret_….json` baixado. Ele contém o **client secret** — vai
direto para o VPS, não para chat.

## Passo 2 — o JSON até o VPS

O arquivo é pequeno (~400 bytes) e uma linha só. Cabe numa colagem:

```bash
cat > ~/.urace/google-credentials.json
```

Cole o conteúdo, **Ctrl+D**. Depois:

```bash
chmod 600 ~/.urace/google-credentials.json; python3 -c "import json;d=json.load(open('/home/ubuntu/.urace/google-credentials.json'));c=d.get('installed') or d.get('web');print('client_id:',c['client_id'][:20]+'…','| tipo:',list(d)[0])"
```

Tem que imprimir o `client_id` e `tipo: installed`.

## Passo 3 — consentimento, uma vez por caixa

```bash
cd ~/Uraceagent && python3 adminai/google_auth.py
```

O script imprime uma URL. Abra **na sua máquina**, logado como
`urace@urace.us`, autorize. O navegador vai falhar ao abrir
`localhost:1` — esperado. Copie o `code=` da barra de endereços e cole
no terminal. O script confere **qual e-mail autorizou** antes de gravar:
se for a caixa errada, não grava nada.

Depois, a segunda caixa, logado como `support@urace.us`:

```bash
python3 adminai/google_auth.py --conta support
```

## Passo 4 — registrar e provar

```bash
nohup bash adminai/deploy/install_adminai.sh > /tmp/inst.txt 2>&1 &
```

Esperar 30 s, então:

```bash
grep -E 'mcp google|política do sandbox|- google: [0-9]+ tools|Google' /tmp/inst.txt
```

`✅ Google`, `mcp google: registrado`, `google: 9 tools`, e a política
com 27 (12 + 6 + 9). A prova real, pela ferramenta:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"gmail_contas","arguments":{}}}' | URACE_ENV=$HOME/.urace/adminai.env timeout 60 python3 ~/Uraceagent/adminai/mcp/gmail_mcp.py 2>/dev/null | tail -1 | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];print(r['content'][0]['text'])"
```

Tem que vir as duas contas com `"ok": true` e o e-mail real de cada.

## O que o servidor garante em código

| Regra do dono | Como |
|---|---|
| A IA não envia e-mail | **não existe** ferramenta de envio |
| Propaganda sai sozinha, o resto fica | remover `INBOX` só com `wNews` |
| Não apaga, não marca spam | `TRASH`/`SPAM` recusados sempre |
| Taxonomia é do dono | marcador inexistente é erro, não criação |
| `APLICAR=0` | rotular e rascunho viram simulação |

A waiver assinada que chega em `support@`: `gmail_baixar_anexo` grava em
`/workspace/anexos/` e `asana_anexar_arquivo` aceita esse caminho. O
ciclo da subtarefa "Signed waiver?" fecha sem passar pelo chat.
