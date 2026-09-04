---
tipo: processo
area: QuickBooks
fonte: humano
ditado_por: Italo Silveira
data: 2026-08-31
tipo_info: PROCESS
responsavel: Italo Silveira
status: ativo
---

# Processo — invoice e estimate no [[QuickBooks]]

[[URACE]] · [[Asana]] · [[Gmail]] · [[Security deposit]] · [[Rate Card]] · [[Clientes]]

## ✅ O que o agente de invoice PODE fazer

Confirmado pelo dono (31/08). **Criar é o trabalho do agente.** A linha
não está entre ler e escrever — está entre **escrever e ENVIAR**.

| ✅ Pode | 🚫 Não pode |
|---|---|
| **criar invoice** | **enviar invoice** (exceto a do [[Security deposit]]) |
| **criar estimate** | enviar estimate sem "ok" |
| **criar cliente** no QBO | disparar reminder sem "ok" do lote |
| **criar item** no catálogo | apagar, inativar ou alterar o que já existe |

Criar não é enviar. A invoice fica salva, com link, esperando revisão —
é exatamente esse o ponto do fluxo.

Antes de criar cliente: **buscar pelo responsável e pelo e-mail**
(ver [[Clientes]]) — é assim que se evita duplicata.
Antes de criar item: `qbo_catalog_search_products`, e só criar o que
voltar `found: false`.

## 🚫 A regra que manda em tudo

**A IA cria e SALVA. A IA NÃO ENVIA.** A invoice fica com status pendente
esperando [[Italo Silveira]] ou [[Eduardo Resende]] revisar e enviar.

Só envia quando um dos dois disser **explicitamente** "pode enviar" /
"envie diretamente" **para aquele cliente**. Autorização de um caso não
vale para o próximo.

Exceção única já autorizada: a invoice do [[Security deposit]] (valor
fixo US$ 400) — ver [[PARAMETROS]].

## Estimate × Invoice

| Documento | Quando |
|---|---|
| **Estimate** (orçamento) | cliente pediu orçamento · **preparação de corrida** (pré-corrida) |
| **Invoice** | serviço realizado · peças · coaching, daily, Urace Academy, dia de equipe, mensal |

## Onde achar o cliente

**Customer Hub → Customers and Leads.** Busca por nome ou e-mail. Na
página do cliente estão **nome, e-mail e telefone** — o necessário para
enviar. (Pela API: `qbo_contact_search_customer`.)

> ⚠️ **A conta está no nome do RESPONSÁVEL FINANCEIRO, quase nunca no do
> piloto.** Procurar "Bryan Santiago" e concluir que o cliente não existe
> é como se cria cliente duplicado. Ver a tabela de mapeamento em
> [[Clientes]]. Buscar por **e-mail** quando o nome não bate. Só criar
> cliente novo depois de buscar pelos dois.

## Campos da invoice

| Campo | Regra |
|---|---|
| Número | gerado pelo QuickBooks |
| Invoice date | data de emissão |
| **Due date** | **2 a 3 dias depois** da invoice date |
| **Service date** (por linha) | dia do serviço / dia em que as peças foram usadas, **conforme agendado no [[Asana]]**. Não é obrigatório, mas **sempre preencher** |
| Produto/serviço | usar os itens que **já existem**. Ver [[QuickBooks]] — só ~25 faturam de verdade |
| Descrição | nem todo item tem. A IA pode escrever — **será revisada por humano** |
| Quantidade e valor | preço vem da [[Rate Card]] (ver precedência em [[PARAMETROS]]) |
| ⚠️ `amount` da linha | é o **valor UNITÁRIO**, não o total. `quantity: 2` + `amount: 21.25` = linha de $42,50 |
| "x 2 dias" | vira `quantity: 2` — **não** duas linhas |
| Idioma da descrição | **inglês** — é texto que o cliente lê |

### Classe / tag

| Tipo | Classe |
|---|---|
| Prática / treino | prática |
| Peças | peças |
| Corrida | tag da corrida (existem várias) |
| **Urace Academy** | **entra como corrida** |
| Suits · Canotops | a sua |
| **Security deposit ($400)** | **depósito** |

Corrida sem tag → **criar a tag** e usar.

> ⚠️ **A ferramenta MCP de invoice não tem campo de classe/tag.**
> Decisão do dono (31/08): a IA **escreve na mensagem de escalação um
> lembrete** de qual tag e qual classe aplicar. Quem revisa aplica no
> clique. A IA nunca deixa passar em branco sem avisar.

### Mensagem na invoice

Padrão real (confirmado pelo dono, 31/08) — **`TIPO | SUBTIPO | EVENTO`**:

```
RACE | Pre Race | AMR RD 6&7
Parts | AMR RD 6&7
```

**O mesmo texto vai nos dois campos de mensagem.** Não é minúsculo: é
`RACE` em caixa alta e `Parts` capitalizado, como nos exemplos.

## Preço de peça — 15% de margem

Alguns preços estão no [[QuickBooks]]. A maioria **não**: a URACE é
dealer oficial e busca o preço da peça no site do fornecedor
([[KartSport]], [[Comet Kart]] etc.) — **da peça exata, para aquele
chassi e aquele motor daquele cliente**. Trabalho manual hoje.

**Sobre o preço encontrado, aplica-se +15% — por peça, sempre.** Valor
em [[PARAMETROS]] (é lá que se altera, não aqui).

## Como a IA descobre qual peça cobrar

As mensagens que chegam trazem **pouca informação**. A IA tem **três
caminhos** para chegar na peça certa, e usa todos antes de perguntar:

1. **A própria peça tem referência** — dá para saber para qual chassi e
   qual motor ela serve.
2. **Histórico do [[QuickBooks]]** — muitas peças são usadas com
   frequência; o que já foi faturado antes ensina o padrão.
3. **[[Asana]] e [[Gmail]]** — qual chassi e qual motor aquele cliente
   usou naquele treino.

Só depois de esgotar os três é que pergunta. **A peça tem que ser
compatível com o equipamento daquele cliente** — peça errada na invoice é
retrabalho e desgaste.

## 🔑 O que a mensagem de gatilho precisa ter

Para a IA montar uma invoice, a mensagem que pede tem que trazer
**o nome ou o e-mail do cliente** — é a chave que permite localizá-lo
**no [[QuickBooks]] e no [[Asana]] ao mesmo tempo**. Sem isso ela não
consegue cruzar as fontes; pede o identificador antes de qualquer coisa.

> 🔧 **A mecânica do conector** — criar item, item ambíguo, `txnId`, o
> que ele não faz — está em [[Conector do QuickBooks]]. Esta nota é o
> **processo**; aquela é a **ferramenta**.

> 📄 **Estimate de pré-corrida** tem processo próprio:
> [[Estimate de pre-corrida]].
> 💰 **Cobrar invoice vencida** também: [[Cobranca de invoice vencida]].

## Termos fixos da [[Rate Card]] que afetam a cobrança

- **Taxa de pista nunca entra na invoice** — o cliente paga direto na
  pista, pelo link. Nunca vender como "all inclusive".
- Peça comprada pelo cliente (não pela URACE): **+50% na mão de obra**.
- Segundo motor: **40%** do aluguel do motor.
- Campeonato: **entrada de 30% + parcelas**, quitado antes da última corrida.
- Mecânico varia ±$50 e começa **1 dia antes** do evento.

## 🤝 Permuta

**Frankie Iadevaia** e **Brody Robins** operam em permuta, que cobre
**apenas serviço ainda não faturado**. Invoice já emitida **segue como
cobrança normal e não se cancela** por causa do arranjo. Ver [[Clientes]].

## Escalação da invoice pronta

Salvou → **a invoice já tem link**. Mandar no canal de escalação:

```
Invoice para <cliente>
E-mail: <email>   ·   Telefone: <telefone>
Em aguardo para revisão e envio.
<link da invoice>

⚠️ Lembrete ao revisar: aplicar TAG <tag> e CLASSE <classe>
   (a IA não consegue preencher esses dois campos)
```

Resposta "ok, pode enviar" / "tudo certo" → **aí sim envia**.
Qualquer outra coisa = ajuste; a IA corrige e reenvia para revisão.

Esse canal é também onde a IA **aprende**: instrução dada ali que virar
regra é gravada aqui ou em [[PARAMETROS]] — ver [[Stand-by e escalação]].

## Como a IA pergunta

O dono foi explícito: **ela não tira dúvida sobre tudo.** Tem que
entender, e quando perguntar, ser **concisa e certeira**. Pergunta vaga
ou óbvia queima a confiança do canal.

---

## ⚠️ Pendências técnicas descobertas em 31/08

**1. Classe/tag não existe na ferramenta MCP.** `qbo_sales_create_invoice`
aceita cliente, linhas, `service_date` por linha, `due_date`,
`note_to_customer`, referência, desconto e termos — **mas não tem campo
de classe nem de tag**, e não há ferramenta para criar tag.
Ou a classificação fica para o humano na revisão, ou depende da REST API
com token ([[Etapa de conexão]]).

**2. O reminder exige confirmação a cada envio — e isso está alinhado
com a decisão do dono.** A ferramenta obriga mostrar o texto e pedir
"sim" antes de disparar. O dono fechou o escopo em 31/08: **a cada 2
dias, só as OVERDUE, com "ok" a cada lote** — sem autorização permanente.
A limitação técnica e a regra de negócio coincidem: **resolvido**.

**3. O que a IA consegue preencher sozinha hoje:** cliente, itens,
quantidades, valores, descrições, `service_date` por linha, `due_date`
(2–3 dias) e a mensagem no padrão `TIPO | SUBTIPO | EVENTO`. Salvar sem
enviar: sim. **Classe e tag: não** — vão como lembrete na escalação.

**4. ✅ Modelo de e-mail de invoice: não existe porque NÃO É PRECISO.**
Fechado pelo dono em 31/08: **o envio é feito pelo próprio QuickBooks**,
no botão de enviar. O texto e o layout são os do QBO. Não há e-mail
manual pelo [[Gmail]], não há template a escrever, e **não há lacuna a
preencher** — o assunto está encerrado, não pendente.

Consequência prática: o trabalho da IA termina na invoice **salva com
link**. Quem revisa clica em enviar dentro do QuickBooks.

**5. ✅ Os 90 centavos: resolvido.** O mensal Academy 4T é
**US$ 2.756,90** — confirmado por invoice paga (txnId 9391, 02/07/2026),
pelo desconto de $119,10 idêntico ao do 2T, pelo degrau de $400 entre as
categorias e pela metade que dá exatamente $1.378,45. A planilha está
com $2.756,00 em duas células e precisa ser corrigida. Contas e células
em [[Rate Card]].
