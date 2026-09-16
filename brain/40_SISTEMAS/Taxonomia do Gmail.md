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

## Regra do dono (14/09): não mexer em marcador fora do manual

> *"Não mexa em marcadores que no momento não estão no manual."*

Marcador que aparece na caixa e não está no manual é **ignorado**, não apagado,
não editado, não usado. A IA não o enxerga na triagem, o filtro não o cria e
nenhum script encosta nele. Ele só existe para a IA depois que o dono o coloca no
manual e confirma.

Vale inclusive para os que ela desconfia: em 11/09 os `Email Review/…` só saíram
da caixa porque **ele mandou**, com essas palavras. A leitura e o aviso são
trabalho da IA; a decisão é dele.

## Propaganda é trabalho da IA, não do filtro (14/09)

`wNews` é o maior marcador da caixa (1.981 conversas) e o único que sai da inbox
sozinho — e é justamente o que o filtro por remetente **não cobre**: propaganda
vem de centenas de endereços, cada um com uma ou duas mensagens, e nenhum passa no
corte de evidência. Na primeira geração, `wNews` ganhou **um** remetente.

Decisão do dono: *"faça de uma forma que a IA leia esses que não forem pegos pelo
filtro e identifique a propaganda"*. A regra entrou no prompt, com o critério
escrito (quer vender/divulgar × já existe relação) e com a trava que importa:
**na dúvida, não usar `wNews`** — recibo enterrado custa mais caro que propaganda
na inbox.

## Segunda revisão dos filtros (15/09) e o "arquivar" da família wNews

O dono revisou o relatório novo e tirou mais quatro regras. A que importava:
`@orlandokartcenter.com` estava indo para `Finances/Pending Invoices ❗` — a fila de
**contas a pagar** do painel. Todo e-mail do OKC viraria dívida fantasma. As
outras três: e-mail devolvido (`mailer-daemon`) indo para marketing, companhia
aérea (Breeze) indo para corrida, cobrança do Google indo para rede social.

E decidiu: **o relatório diário do Kommo pode arquivar** (`samuel.rulli@itcygnus.com`
→ `wNews/George | Atendente`, 31 de 31). Isso expôs uma inconsistência antiga: a
regra "arquivar só com `wNews`" estava escrita no código como **nome exato**, então
`wNews/Study`, `wNews/Italo| MAA` e `wNews/George | Atendente` não contavam — nem
no gerador de filtros, nem no MCP (`gmail_rotular` recusaria). A taxonomia sempre
disse que a família inteira é propaganda. Agora o código diz o mesmo:
`wNews` e qualquer `wNews/…` saem da inbox.

## Decisão do dono (16/09): a lista de destinos mostra TODOS os marcadores

Perguntei se a barra lateral do Gmail no painel devia listar só o que está
confirmado no manual, já que um clique ali move o e-mail — inclusive para
marcador que não é dele (`Action Required`, `Legal or Contract`). Resposta:
**"mostra todos os marcadores"**.

A distinção que ele faz é clara e vale registrar: a regra "só o que está no
manual" é para a **IA**. O clique humano é decisão dele, na hora, com o marcador
que ele quiser — inclusive um que ainda não entrou no manual. Não filtrar a lista.

## Intrusos na urace@ em 16/09 — o registro

Relatório do gerador, revisado pela extensão. Marcadores que existem na caixa,
não são do sistema e não estão no manual:

`Action Required` · `Finance` · `Legal or Contract` · `Operations` · `Receipts` ·
`Travel` · `Vendor or Partner` — sete, com os mesmos nomes de categoria dos
`Email Review/…` apagados em 11/09, agora sem prefixo. O e-mail do D4Sign de
14/09 às 22:50 chegou com dois deles colados. **Continua ativo.** O dono decidiu
não caçar e não mexer: o painel ignora; este registro é só para a linha do tempo.
(Os dois `Years 2019-2023/…/[Gmail]…` são lixo de importação antiga, não intruso.)

## Os filtros nativos das duas caixas ficaram de pé em 16/09

A `urace@` foi pela tela (importação do XML), depois de duas tentativas frustradas
no mesmo dia — conta delegada e clique em dobro. Entraram **89 regras novas** por
cima das **41 que já existiam**, com `ken@naturecoasthealthcare.com → Team/LARA`
desmarcada na hora da importação (pasta de quem já saiu); a recusa entrou no
gerador para não voltar.

A `support@` foi **pela API**, do botão *Criar no Gmail* do painel. O painel
respondeu **"2 criado(s), 22 já existiam"**: as 22 derivadas de remetente já
tinham sido importadas antes, e os 2 criados são justamente **as duas regras
ditadas pelo dono** — as que sustentam o fluxo da waiver:

| Critério | Marcador |
|---|---|
| `from:(docusign.net OR docusign.com)` | `Softwares\|Apps/Docusign` |
| `from:(docusign.net)` + assunto com *Waiver of Liability* e *Please Complete* / *Completed:* | `Waivers` |

Essas duas foram as que erraram duas vezes com HTTP 400 antes: o critério ia como
`hasTheWord`, que é o nome **na tela** do Gmail — na API o campo é `query`, e a
API descarta campo que não conhece sem reclamar do nome, só diz que o filtro "não
tem critério nenhum". Corrigido no commit `063099a`, com recusa explícita de campo
desconhecido para não repetir o diagnóstico.

### A contagem real (16/09, no VPS)

`urace@` **130** filtros — bate com o previsto (41 + 89).

`support@` **37**, não 24 como o painel fez parecer. A conta fecha assim:
**13** filtros que o dono já tinha, **22** derivadas importadas pelo XML antes, e
**2** criadas pela API. O "22 já existiam" do painel era a trava de duplicata
reconhecendo o que a importação anterior já tinha posto lá — não filtro do dono.

Dois achados da contagem, os dois de antes desta rodada:

1. **Um filtro manda todo envelope do DocuSign para `Waivers`** —
   `dse_na4@docusign.net` é o endereço de envio da conta inteira. É o gatilho do
   fluxo da waiver disparando em documento que não é waiver.
   Ver [[P-14 - Filtro manda todo envelope do DocuSign para Waivers]].
2. **Sete pares redundantes.** A importação criou versões "com um remetente a
   mais" ao lado das do dono (`info@bushnellmotorsportspark.com` sozinho e com
   `@united.com`; RD Station com e sem `receiv@rdstation-fin.com`; Spirit com e
   sem Marriott; n8n com e sem `accounts.google.com`; Dialpad, Ecwid e Kommo em
   dobro). A trava de duplicata compara critério **idêntico** — superset não é
   idêntico, então passou. Mesmo marcador nos dois, então não erra nada; só suja.

Duas coisas para o dono olhar, que **não** são obra desta rodada:
`receiv@rdstation-fin.com` está dentro de um filtro como se fosse RD Station
legítimo (é o domínio que levantou suspeita de golpe em 14/09), e
`samuel.rulli@itcygnus.com` tem filtro marcando **IMPORTANT** — o mesmo remetente
que ele mandou arquivar na `urace@` em 15/09. Há ainda um filtro
(`[Newsletter Form] new lead`) que **não faz nada**: critério sem ação nenhuma.

### O que o filtro nativo não cobre — de propósito

Propaganda (`wNews`) e qualquer coisa que dependa de contexto continuam com a IA:
o filtro pega remetente e assunto, a IA lê o corpo, confirma o marcador do filtro,
acrescenta o que faltar e escala o que não souber. As duas coisas rodam juntas —
foi o desenho que o dono pediu: *"vai ter o nativo rodando e a IA também vai fazer
esse trabalho"*.
