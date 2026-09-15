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

⚠️ **Os 11 `Email Review/…` não são do dono — origem apurada em 11/09.**
Foram aplicados em ~700 conversas a partir de **9 a 12 de agosto**, por cima
dos marcadores dele, com erros de classificação típicos de LLM (extrato do
Home Depot como "Verification Code"). **Não foi o Command Center** — o MCP
recusa marcador que não existe e o código não tem nenhuma função que crie
marcador. O log de tokens OAuth do domínio fechou o caso: entre 9 e 12/08
**nenhum token novo foi emitido**, e o único app com escrita no Gmail naquela
data era o **conector `Claude for Gmail` do claude.ai** (token de 16/07/2026).
Foram sessões do dono no Claude, com o conector do Gmail ligado. Ficaram
**fora** do manual — a IA os ignora. **Apagados da caixa em 11/09** a pedido
dele: os 11 marcadores saíram, 714 conversas perderam a etiqueta e **nenhum
e-mail foi apagado**. Ele optou por **manter o conector do Gmail ligado**, então
pode voltar a acontecer se uma sessão do Claude for instruída a organizar a caixa.
As 11 linhas continuam no manual como `fora`: se algo os recriar, já nascem
ignorados. Ver [[D-2026-09-11 - Manual dos marcadores do Gmail confirmado pelo dono]].

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

Rotina: **07h, 13h e 21h** pelo Command Center. Ver [[Triagem de e-mail]].

## Onde o manual vive (11/09)

Uma fonte só, três consumidores:

| Onde | O que é |
|---|---|
| `command_center/providers/taxonomia_gmail.py` | **a fonte** — 156 marcadores, texto e estado |
| `skills/urace-gmail/MANUAL.md` | gerado dela; é o que o agente lê |
| Painel → Gmail → **Manual dos marcadores** | a tela onde o dono confere e confirma |
| tabela `gmail_labels` | estado por marcador (confirmado / pendente / fora) |

`python3 adminai/gerar_manual_marcadores.py` regera o `MANUAL.md`, e o teste
`test_manual_da_skill_esta_em_dia` quebra se os dois divergirem.

## A caixa support@ — lida em 14/09

A `support@` tem **64 marcadores próprios**, e nenhum deles estava no manual de
11/09: aquele saiu inteiro da `urace@`. São caixas com funções diferentes —
`urace@` é dinheiro, compra e plataforma; `support@` é **atendimento, funil de
cliente e fornecedor**.

O que mais pesa lá: `Softwares|Apps/Docusign` (399 conversas) ·
`Customer Service/LP Leads` (413) · `Fornecedores` (285) ·
`Ex-Funcionários/Jeyson Herrera` (247) · `Softwares|Apps/Ecwid` (322) ·
`Karting School` (187) · `Softwares|Apps/Dialpad` (173).

Os 64 entraram como **`pendente`**: o dono confirma marcador por marcador no
painel (aba `support@`), como fez na `urace@`. Enquanto não confirmar, a triagem
daquela caixa **não roda** — a trava de 11/09 vale para as duas.

### Quatro coisas que a leitura mostrou e ele precisa decidir

1. **`Action Required`, `Lead or Customer` e `Operations` estão aqui também.** São
   os mesmos nomes de categorias `Email Review/` apagadas da `urace@` em 11/09 —
   o que rotulou uma caixa mexeu nas duas. Entraram como `fora`.
2. **`Curriculos` não tem currículo.** São 2 conversas de lead
   ("Thank you for reaching out").
3. **`Ex-Funcionários/George | Atendente` não é atendimento.** São 227 conversas do
   "Relatório Kommo - Leads Diários" que o Samuel (Cygnus) mandava todo dia.
4. **`Marketing/RD Station /MailMarketing` tem cheiro de golpe.** Há mensagens de
   `rdstation-fin.com` e `rdstation-security.com` — o domínio verdadeiro é
   `rdstation.com.br`. Uma delas é "Fatura RD Station em Atraso".

### Sobreposição a resolver

`Softwares|Apps/Docusign` (399) e `Waivers` (57) guardam a mesma coisa por
caminhos diferentes: o primeiro é todo envelope do DocuSign, o segundo é a waiver
do cliente. Vale o dono decidir qual manda, senão a IA vai hesitar em toda waiver.
