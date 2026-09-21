---
tipo: sistema
tipo_info: FACT
fonte: uso real do conector MCP, 31/08/2026
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Conector do QuickBooks — a mecânica

[[QuickBooks]] · [[Sistemas]] · [[Invoice e estimate no QuickBooks]] ·
[[Rate Card]]

Como a ferramenta se comporta de verdade. O **processo** (o que fazer, e
quando) está em [[Invoice e estimate no QuickBooks]] — aqui é só a
mecânica, aprendida no uso.

## Ordem obrigatória das chamadas

Pular etapa produz duplicata de cliente ou de item.

1. `company_info` — estabelece a conexão. **Sempre primeiro.**
2. `qbo_contact_search_customer` — com a tabela de [[Clientes]] na mão
   (a conta está no nome do **responsável**, não do piloto).
3. Preço na [[Rate Card]] — precedência em [[PARAMETROS]].
4. `qbo_catalog_search_products` — até 20 termos de uma vez.
5. `qbo_catalog_create_product` só para o que voltar `found: false`.
6. `qbo_sales_create_invoice` **ou** `qbo_sales_create_estimate`.

## Criar item novo no catálogo

- **O QBO não aceita dois-pontos no campo `Name`.** `Parts IAME:X` falha.
  Criar com nome simples e **avisar** que o item nasceu fora da categoria
  e precisa ser movido à mão.
- `taxable: false` é o padrão desta conta.
- `product_type: "SERVICE"` **mesmo para peça** — é o padrão do catálogo.
- Preço desconhecido entra como `unit_price: 0`, para o dono preencher.

## Item ambíguo no catálogo (`requires_clarification: true`)

Aparece com frequência e **nem sempre exige parar**. Critério:

| Situação | O que fazer |
|---|---|
| Match claro pela marca ou motor | **escolher e declarar**. KA100 é IAME → "IAME Front Sprocket Z10" é a escolha certa para "front gear Z10" |
| Peças genuinamente diferentes | escolher a mais provável, criar assim mesmo, e **sinalizar a alternativa com preço**. Ex.: "IAME Reed petal" $21,25 × "IAME Fiberglass Reed Petal" $21,89 |
| Pacote fechado × mão de obra avulsa | **nunca sobrescrever**. "Engine rebuild top end KA100" é pacote a $650; jogar $250 de mão de obra nele distorce o item — sugerir item separado |

**Travar a tarefa inteira por uma peça de $20 custa mais que sinalizar bem.**

## Identificadores e links

- Reference number: `4YZRN1QWN###NQM`, `5YZRN1QWN###NQM`, `6YZRN1QWN###NQM`.
- ⚠️ **Existem `doc_number` duplicados nesta conta.** Deep link usa
  **sempre `txnId`**, nunca o número do documento.
- Formato:
  `https://qbo.intuit.com/app/login?pagereq=invoice%3FtxnId%3D{txnId}&deeplinkcompanyid=9341453113046421`
- **Reproduzir o link que a ferramenta devolveu, literalmente.** Nunca
  montar link inventando id.

## O que o conector NÃO faz

- **Não edita preço** de item existente. **Não inativa** item. Só cria e busca.
- Atualização de preço em lote sai por CSV: *Settings > Import data >
  Products and services*, com a opção de **sobrescrever por match exato de
  nome** marcada. Sem essa opção o QBO **cria duplicata** em vez de atualizar.
- O CSV precisa da coluna **Income Account** preenchida ou mapeada na tela
  de importação — o conector não lê o plano de contas, esse campo é do dono.
- Os nomes no CSV têm que bater com o campo `Name` (**sem** o prefixo de
  categoria), senão vira item novo.

## O valor da linha

**`amount` é o valor UNITÁRIO, não o total.** `quantity: 2` +
`amount: 21.25` = linha de $42,50. E "x 2 dias" vira `quantity: 2`, não
duas linhas.

⚠️ Para pacote de [[Urace Academy]], **derivar do mensal**, nunca
multiplicar a unitária arredondada — ver [[Rate Card]].
