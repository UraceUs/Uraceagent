# Rate Card do Drive → preço no QuickBooks

**Decisão do dono (18/09/2026):** *"use o rate card sempre; ele será atualizado no Drive,
sempre consultar lá"*, *"não preciso aprovar se o valor estiver como está no rate card"*,
*"peças podem manter o mesmo valor"* e *"faça ele ler isso uma vez por semana e atualizar o
quickbooks"*.

## Como funciona

```
Segunda, 07:30 (Flórida)
  → lê a URACE RATE CARD 2026 na planilha do Drive (Sheets API, token que já existe)
  → extrai cada linha com UM preço e um nome
  → compara com o catálogo do QuickBooks (itens ativos)
  → aplica o que está no MAPA REVISADO; cria o que o dono marcou para criar
  → o que não está no mapa vira pergunta em "Precisa de atenção"
```

Nos outros dias a rotina acorda e não faz nada: o recorte da segunda-feira está em
`precos.rodar_semanal`. Para aplicar na hora, sem esperar segunda: **`POST
/ops/api/precos/aplicar`** (gerente ou administrador), e **`GET /ops/api/precos/plano`**
mostra o que mudaria sem tocar em nada.

## Por que existe um mapa revisado

Casar por nome parecido **não funciona** aqui, e isso foi aprendido apanhando:

- `Summer Camp — 3 Days` e `5 Days` só se distinguem pelo qualificador; um casamento por
  semelhança colocou o preço de 3 dias no item de 5;
- um item do catálogo está escrito **"Pratice"** (com erro de digitação), o que fura
  qualquer comparação por palavra;
- a planilha mistura **`$1,250`** (milhar com vírgula) e **`$2.756,90`** (milhar com ponto,
  decimal com vírgula) — o primeiro parser leu `$2.756,90` como **dois e setenta e seis**.

Por isso: só é aplicado o que está em **`command_center/db/ratecard_mapa.json`**, revisado
por gente. O arquivo tem quatro partes:

| Parte | Para que serve |
|---|---|
| `pares` | linha da Rate Card ↔ item do catálogo, com `acao`: `atualizar` ou `ignorar` |
| `correcoes` | preço quebrado no catálogo (o separador de milhar comido na importação: item de $2.400 cadastrado como $2,40). Só aplica enquanto o preço ainda for o quebrado — depois some sozinho |
| `familias` | o que fazer com uma família inteira da Rate Card que não tem item: `criar` ou `ignorar` |
| `notas` | o que o dono pediu por escrito (ex.: "per practice" vira "per additional practice") |

**Para ligar uma linha nova:** acrescente um par em `pares` com o nome exato da linha da
Rate Card e o nome completo do item no QuickBooks (`Service:...`, `Rental:...`).

## As travas

- **Peça nunca muda de preço** (dono, 18/09). A recusa está em dois lugares: no plano
  (`ratecard.planejar`) e na escrita (`quickbooks_mcp.preco_item_sistema`).
- **Preço fora da faixa** (negativo ou acima de US$ 100 mil) é recusado na escrita.
- **Item inativo ou inexistente** é recusado.
- **Alguém mexeu no preço desde a revisão?** A correção não atropela: vira pergunta.
- **Falha em um item não derruba os outros** — cada linha tem seu resultado, como no
  fechamento da venda.
- Tudo auditado item a item (`precos.item`, `precos.criar`, `precos.semanal`).

## Onde está

| O quê | Onde |
|---|---|
| Leitura, parser e plano | `command_center/providers/ratecard.py` |
| Mapa revisado | `command_center/db/ratecard_mapa.json` |
| Rotas e rotina | `command_center/api/precos.py` |
| Escrita no QuickBooks | `adminai/mcp/quickbooks_mcp.py` → `preco_item_sistema` |
| Rotina na agenda | `automation_rules` → `ratecard_semanal`, 07:30 |
| Testes | `command_center/tests/test_precos.py` (19) |

A planilha é a `160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo` (URACE RATE CARD 2026). Para
apontar para outro arquivo: `RATECARD_SHEET` no ambiente do serviço.
