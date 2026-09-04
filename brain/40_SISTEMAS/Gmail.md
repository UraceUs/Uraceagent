---
tipo: sistema
atualizado_em: 2026-08-28
tipo_info: FACT
responsavel: sonda ao vivo
status: ativo
---

# Gmail
Caixas `urace@urace.us` e `support@urace.us`. Processo: [[Triagem de e-mail]].
## Marcadores que mais importam
- `wNews` (1.943) — **toda propaganda**. Só ele é arquivado.
- `Finances/Pending Invoices ❗` — **contas a pagar**
- `Shipping Status` (905) — alimenta [[Compra e envio]]
- `Marketing & Sales/Comercial/Formulario do site` (957) — leads
- `Suits` (432) — [[Pedido de macacão]] · `RACES/...` — [[Corridas]]
## Regra
A IA **cria rascunho, não envia** — exceto as duas do [[Pedido de macacão]].

## Como o Administrative AI fala com o Gmail (04/09)

Por servidor MCP nosso (`adminai/mcp/gmail_mcp.py`), no
[[VPS e OpenClaw]], com um refresh token **por caixa** — `urace@` e
`support@`. ⚠️ A delegação de acesso na tela do Gmail **não vale para a
API**; cada caixa autoriza uma vez (`adminai/google_auth.py`).

O app OAuth é **interno ao Workspace**: sem revisão do Google, e o token
não expira por inatividade curta. É a única conexão sem fila de terceiro.

As regras em código: **não existe ferramenta de envio**; arquivar só com
`wNews`; `TRASH`/`SPAM` nunca; marcador inexistente é erro, não criação;
`APLICAR=0` vira simulação. Ferramentas: `gmail_contas` ·
`gmail_marcadores` · `gmail_buscar` · `gmail_thread` ·
`gmail_baixar_anexo` · `calendar_eventos` · `sheets_ler` ·
`gmail_rotular` · `gmail_rascunho`. Passo a passo em
`docs/adminai/google-conexao.md`.
