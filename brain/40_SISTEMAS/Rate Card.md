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
| **Mensal sem contrato** (`Academy Monthly`, 4 sessões/mês) | kart próprio + mecânico $1.200 · kart próprio $1.800 · Baby Kart $2.756 · **4 stroke $2.756** · 2 stroke $3.156,90 |
| **Sessão extra** no mensal | $300 · $450 · $689 · **$689** · $789,23 |
| **Contrato 6 meses / 27 sessões** | 4T $17.858,88 (4% off · 33% entrada $5.893,43 + 5× $2.393,09) · 2T $20.450,88 |
| **Contrato 12 meses / 54 sessões** | 4T $34.229,52 (8% off · 20% entrada $6.845,90 + 11× $2.489,42) · 2T $39.197,52 |

Academy fora do OKC cobra hotel, comida e transporte à parte.

### ⚠️ Divergência a confirmar com o dono

O pacote de 2 dias do [[Michael Nicholas|Elijah Nicholas]] foi faturado
a **US$ 1.378,45** (invoice paga, confirmada no [[QuickBooks]]).

- $1.378,45 = **2 × $689,225** → implica mensal 4T de **$2.756,90**
- A Rate Card diz **$2.756,00** (→ sessão extra $689,00 exata)
- A linha vizinha, 2 stroke, mantém os centavos: $3.156,90 / $789,23

Ou seja: **a URACE cobra pelo valor da sessão extra do mensal ($689,x),
não pela sessão avulsa ($719)** — e há 90 centavos de diferença entre a
planilha e a invoice real. Falta o dono dizer qual dos dois é o certo.
Até ele responder, **reaproveitar o valor da invoice anterior do mesmo
cliente** e declarar isso na escalação.

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
