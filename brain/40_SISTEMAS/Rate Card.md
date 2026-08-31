---
tipo: sistema
fonte: google_drive
atualizado_em: 2026-08-31
---

# Rate Card — a fonte de verdade de PREÇO

[[URACE]] · [[QuickBooks]] · [[Invoice e estimate no QuickBooks]] · [[PARAMETROS]]

> **A Rate Card manda acima do catálogo do [[QuickBooks]].**
> O catálogo do QBO tem preço defasado; a Rate Card é mantida pelo dono.
> Ordem de precedência: **valor que o [[Italo Silveira]] passar** →
> **Rate Card** → **invoice anterior do mesmo serviço** → catálogo do QBO.
> Nunca cotar de memória.

| Fonte | Arquivo no Drive | ID |
|---|---|---|
| **URACE RATE CARD 2026** (planilha) | serviços, corridas, Academy, mecânico, aluguel | `160efDlmavKKGbtGfJKCTOV_3Q9JEO3Lc6xA1mEMMNyo` |
| **Canotops_Price_List** (documento) | barracas Canotops | `1bIVVEVqloBH4yWqrECODplAX8eQ9u3Mrz_byQ5TRM58` |

Ambos lidos ao vivo em 31/08/2026 pelo conector do Google Drive — dono
`urace@urace.us`. A planilha foi alterada em **29/08/2026**: é documento
vivo, **reler antes de faturar**, não confiar nos números copiados aqui.

## O que tem dentro da planilha

1. **Rate Card 2026** — tabela comercial (mecânico, aluguel de motor e
   chassi, team fee, campeonatos, practice week).
2. **Services Rate Card** — [[Urace Academy]], lead & follow, summer camp,
   corporate/eventos.
3. **Modelo de ESTIMATE** — formulário pronto (`EST-YYYYMM-NNN`) com
   Client/Company/Email/Phone/Class/Program/Event Dates, 10 linhas
   `Item · Description · Unit · Qty · Unit Price · Total`, Subtotal,
   Discount, Tax, **Deposit Due 30%**, Balance Due, TERMS & NOTES e
   duas assinaturas.
4. **Lista normalizada** — ~165 linhas `Item | Category | Unit | Price |
   Notes`. É esta que a IA deve ler para montar linha de invoice.

Categorias da lista normalizada: Shop Service · Engine Rental ·
Summer Camp · Academy Monthly · Arrive & Drive · Academy Contract ·
Mechanics · URACE DIY · Team Fee · Corporate Event · Championship ·
Practice Week · Chassis Rental · Academy · Lead & Follow · Kart Rental ·
Consumables · Custom.

## [[Urace Academy]] — os dois modos de cobrar

| Modo | Preço |
|---|---|
| **Sessão avulsa** (`Academy`, per session) | kart próprio $500 · Baby Kart $719 · **4 stroke $719** · 2 stroke $819 · adult shifter $899 |
| **Mensal sem contrato** (`Academy Monthly`, 4 sessões/mês) | kart próprio + mecânico $1.200 · kart próprio $1.800 · Baby Kart **$2.756,90** · **4 stroke $2.756,90** · 2 stroke $3.156,90 · *(planilha diz $2.756,00 nas duas primeiras — ver abaixo)* |
| **Sessão extra** no mensal | $300 · $450 · $689 · **$689** · $789,23 *(contratos indicam $789 — ver abaixo)* |
| **Contrato 6 meses / 27 sessões** | 4T $17.858,88 (4% off · 33% entrada $5.893,43 + 5× $2.393,09) · 2T $20.450,88 |
| **Contrato 12 meses / 54 sessões** | 4T $34.229,52 (8% off · 20% entrada $6.845,90 + 11× $2.489,42) · 2T $39.197,52 |

Academy fora do OKC cobra hotel, comida e transporte à parte.

### ✅ Os 90 centavos — RESOLVIDO em 31/08

**O mensal Academy 4T é US$ 2.756,90.** A planilha perdeu os 90 centavos
na célula. Quatro caminhos independentes chegam no mesmo número:

**1. Invoice paga, valor exato.** Michael Nicholas (id 677), 02/07/2026,
item `Service:Urace Academy Training Program` (id 177), memo "Urace
Academy": **$2.756,90**, saldo zero.
`https://qbo.intuit.com/app/login?pagereq=invoice%3FtxnId%3D9391&deeplinkcompanyid=9341453113046421`
Não é dedução — é o mês cheio cobrado e pago.

**2. O desconto do mensal é o mesmo nas duas categorias.**

| | 4 avulsas | Mensal | Desconto |
|---|---|---|---|
| 4 stroke | 4 × $719 = $2.876 | **$2.756,90** | **$119,10** |
| 2 stroke | 4 × $819 = $3.276 | $3.156,90 | **$119,10** |

Com $2.756,00 o desconto do 4T viraria $120,00 e quebraria a simetria.
Com $2.756,90 os dois batem em $119,10.

**3. A distância entre 2T e 4T tem que ser $400.** A avulsa custa $100 a
mais no 2T; quatro sessões = $400. $3.156,90 − $2.756,90 = **$400,00**
exato. Com $2.756,00 daria $400,90 — um degrau que não existe em lugar
nenhum da tabela.

**4. A metade bate com a invoice de meio mês.** $2.756,90 ÷ 2 =
**$1.378,45**, exatamente o pacote de 2 dias faturado ao mesmo cliente em
01/08/2026 (invoice paga). Com $2.756,00 daria $1.378,00.

**Baby Kart segue o 4 stroke** em todas as linhas da tabela, então também
é **$2.756,90**.

#### O que corrigir na planilha (célula, não aqui)

| Célula | Está | Deve ser |
|---|---|---|
| `Academy Monthly — 4 Stroke Kart Rental` | $2.756,00 | **$2.756,90** |
| `Academy Monthly — Baby Kart` | $2.756,00 | **$2.756,90** |

Até a planilha ser corrigida, **o valor válido é $2.756,90** — está aqui,
e é daqui que a IA lê.

#### Achado secundário: a sessão extra do 2T

A planilha traz `Academy Extra Session — 2 Stroke` a **$789,23** (que é
$3.156,90 ÷ 4). Mas os quatro contratos só fecham no centavo com
**$789,00** — e a sessão extra do 4T é $689,00, uma distância de $100,
igual à das avulsas:

| Contrato | Conta | Bate com a planilha |
|---|---|---|
| 6 meses 4T | 27 × $689 × 0,96 | $17.858,88 ✅ |
| 6 meses 2T | 27 × **$789** × 0,96 | $20.450,88 ✅ |
| 12 meses 4T | 54 × $689 × 0,92 | $34.229,52 ✅ |
| 12 meses 2T | 54 × **$789** × 0,92 | $39.197,52 ✅ |

Ou seja: **a sessão extra é $689 e $789 redondos** — o mensal é que leva
os $119,10 de desconto e termina em ,90. O $789,23 da planilha é ela
mesma dividindo o mensal por 4, na direção errada.
**Não mexi nesse valor** — é decisão do dono, não a pergunta que ele fez.

## Termos que a Rate Card fixa (valem na invoice e no estimate)

- **Taxa de pista não entra** — é paga direto na pista, pelo link.
- Peça comprada pelo cliente (não pela URACE) **soma 50% na mão de obra**.
- Mecânico varia ±$50 e **começa 1 dia antes** do evento, para preparação.
- **Segundo motor = 40%** do aluguel do motor.
- **Campeonato = entrada + parcelas**, quitado antes da última corrida.
  (Confere com o parcelamento visto no A/R do [[QuickBooks]].)
- Pró capaz de vencer local: **50% off** no team fee de evento local.
  Piloto em 2 categorias paga **50% na segunda**.
- Sem penalidade para sair de campeonato, só perda de crédito.
- Salvo se listado, o estimate **não inclui** pneu, gasolina,
  consumíveis nem dano de batida.

## Canotops — tabela de preço

Frames: 20ft $649 · 15ft $613 · 10ft $589 · 5ft $495
Tops: 20x10 $429 · 15x10 $359 · 10x10 $325 · 5x5 $280
Full walls: 20ft liso $195 · 20ft 1 porta $239 · 20ft 2 portas / 1 porta
+ 1 janela / 2 janelas $275 · 15ft $160 · 10ft $112 · 10ft porta $159 ·
10ft janela $179 · 5ft $89
Half walls: 5ft $99 · 10ft $125
Extras: porta $34 · janela $54 · banner 33x79 $89 · impressão dupla face
$46 · feather flag $79 · beach flag $79 · calha de chuva $25
Toalhas: 4ft $59 · 6ft $79

## Endereço na Rate Card ≠ endereço de cobrança

A capa comercial traz **10724 Cosmonaut Blvd, Orlando FL**
(o [[Orlando Kart Center]]). O modelo de estimate e o rodapé trazem **6149 Cyril Ave,
Orlando FL 32809** — este é o de cobrança, o que está em [[PARAMETROS]].
Não trocar um pelo outro.
