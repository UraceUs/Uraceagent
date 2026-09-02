---
tipo: sistema
atualizado_em: 2026-08-28
tipo_info: FACT
responsavel: sonda ao vivo
status: ativo
---

# Asana
Onde a operação vive. Workspace ` COMMAND CENTER`.
## Projetos
- **U-RACE** `1205450093098920` — [[Corridas]] e [[Serviços]]
- **SUITS** `1205661933760052` — [[Pedido de macacão]]
- **Shipping Orders** `1215968721507536` — [[Compra e envio]]
- **ADM URACE** `1205530439507169` — ⚠️ **somente leitura**
## Colunas do U-RACE
`RACES` · `Finished Services` · TUESDAY→SUNDAY (dia do serviço) · `Pending Reschedule` · `Luis tasks` · **`Matt tasks` — nenhuma automação**
Serviço concluído sai da coluna do dia → `Finished Services`.
## Como o Administrative AI fala com o Asana

Desde 02/09/2026, por um **servidor MCP nosso** (`adminai/mcp/asana_mcp.py`),
que roda no [[VPS e OpenClaw]] com o token de `~/.urace/adminai.env`. O
agente, isolado no container, recebe só as ferramentas — nunca o token.

O servidor oficial do Asana ficou fora de alcance: o OpenClaw só faz OAuth
com registro dinâmico de cliente, e o Asana exige app pré-registrado.
Acabou sendo melhor: **as regras do dono viraram código**, não instrução.

| Regra | Como o servidor garante |
|---|---|
| ADM URACE é somente leitura | toda escrita checa `memberships.project` e recusa antes de chamar a API |
| "Matt tasks" sem automação | a seção é resolvida pelo **nome** em tempo de execução; escrita recusada na origem e no destino |
| A IA não apaga nada | **não existe** ferramenta de apagar, nem de reabrir tarefa |
| `APLICAR=0` é simulação | escrita devolve *"teria feito X"* e não toca no Asana |
| Subtarefa herda proteção | `Signed waiver?` sob tarefa protegida também é recusada |

**Leitura:** `asana_projetos` · `asana_secoes` · `asana_tarefas_da_secao` ·
`asana_buscar` (avisa que o índice atrasa) · `asana_tarefa` ·
`asana_comentarios` · `asana_anexos`.

**Escrita** (todas protegidas): `asana_comentar` · `asana_mover_para_secao` ·
`asana_concluir` · `asana_criar_tarefa` · `asana_anexar_arquivo`.

O `asana_anexar_arquivo` fecha a lacuna de
[[P-09 - Conector do Asana nao sobe anexo]]: com token próprio, o upload
de waiver assinada na tarefa da criança passa a ser possível.

## Ligações
[[Gmail]] alimenta o Shipping Orders · [[QuickBooks]] dispara a criação da tarefa de serviço · [[Google Calendar]] espelha as corridas. IDs em [[PARAMETROS]].
