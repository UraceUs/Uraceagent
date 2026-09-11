---
tipo: sistema
tipo_info: FACT
data: 2026-09-11
fonte: leitura ao vivo dos 156 marcadores de urace@urace.us (11/09) + confirmação do dono, marcador por marcador
responsavel: Italo Silveira
status: ativo
---

# Taxonomia do Gmail — os marcadores reais

[[Gmail]] · [[Triagem de e-mail]] · [[URACE]]

**Atualizado em 11/09/2026.** A conta tem **156 marcadores**; o dono leu e
**confirmou 145, um a um**, no manual (artifact + painel: Gmail → Manual dos
marcadores). É esse manual — e só ele — que a triagem usa; o texto de cada
marcador vive em `command_center/providers/taxonomia_gmail.py` e na tabela
`gmail_labels`. Marcador que aparecer na caixa depois disso entra como
`pendente` e a IA **não o enxerga** até o dono confirmar.

Duas correções que ele fez com a própria mão: `LOC | Practice` = "treino
independente da pista"; `Shipping Status` inclui também o **'purchased'**.

⚠️ **Os 11 `Email Review/…` não são do dono.** Apareceram em setembro e
foram aplicados em ~700 conversas, **nenhuma com mais de 14 dias**, por cima
dos marcadores dele. Não foi o Command Center (o MCP recusa marcador que não
existe e nunca cria nenhum): veio de um filtro do Gmail ou de um app com
acesso à caixa. Ficaram **fora** do manual — a IA os ignora.

A tabela abaixo é o retrato de 28/08, mantido porque explica o peso de cada
família.

| Marcador | Threads | O que guarda |
|---|---|---|
| `wNews` | **1.943** | propaganda — o maior volume da caixa |
| `Banks` | 1.784 + 645 | Bank of America · American Express |
| `Travels/Flights` | 1.165 | passagens |
| `Travels/Hotels Reservation` | 732 | hotéis |
| `Suits` | 432 | macacões · `Suits/Homologação` (7) é FIA 8877-2022 |
| `LOC/Practice Orlando` | 370 | treino no [[Orlando Kart Center]] |
| `Kart Racing School \| Client talks` | 344 | conversa com cliente de [[Urace Academy]] |
| `Team/LARA` | 329 | [[Lara Carvalho]] |
| `Team/Samira` · `Team/Anabelly` · `Team/Eduardo` | 151 · 68 · 33 | [[Equipe]] |
| `LOC/Practice Bushnell` | 65 | [[Bushnell Motorsports Park]] |
| `Finances` | — | dinheiro · `Pending Invoices ❗` é **contas a pagar** |
| `RACES` | — | por série ([[Corridas]]) |
| `Marketing & Sales` | — | **a porta de entrada comercial** |

## O que isso implica para a triagem

- **`wNews` é quase metade do volume.** Propaganda é o único tipo que
  sai sozinho — decisão do dono.
- **`Finances/Pending Invoices ❗` é contas a PAGAR**, não a receber.
  (Eu tinha lido errado antes e corrigi conferindo.)
- E-mail de compra alimenta o **Shipping Orders** do [[Asana]] —
  ver [[Compra e envio]].
- E-mail de corrida vira evento no [[Google Calendar]].
- A waiver assinada chega no `support@`, mas **a fonte de verdade é o
  [[DocuSign]]**, não o e-mail.

Rotina diária proposta: **07h**. Ver [[Triagem de e-mail]].
