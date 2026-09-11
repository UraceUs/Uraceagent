---
tipo: decisao
data: 2026-09-11
fonte: dono (chat + confirmação marcador por marcador no manual)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-11 — O manual dos marcadores do Gmail, confirmado pelo dono

**Dono:** *"Em momento nenhum eu falei que era para criar marcadores… eu
preciso que a IA leia marcador por marcador que existia antes, entenda o que
se coloca em cada um, me dê o manual e eu confirmo — só daí ela sabe como
agir."*

## O que ficou decidido

1. **A IA não cria marcador** (já era regra no MCP; agora está dito em voz
   alta) e **não usa marcador que o dono não tenha confirmado**.
2. **O manual é a única regra de classificação**: 156 marcadores lidos da
   caixa em 11/09, com o que vai em cada um e o volume real. O dono
   confirmou **145**; deixou **11 de fora** (`Email Review/…`).
3. **Sem manual confirmado, a triagem não roda.** Com ele, o prompt leva o
   manual inteiro e a lista fechada de marcadores — o que não está lá não
   existe para a IA.
4. **Marcador novo que aparecer na caixa entra como `pendente`** e fica
   invisível para a IA até o dono confirmar (Gmail → Manual dos marcadores).
5. Correções do dono, com a própria mão: `LOC | Practice` = "treino
   independente da pista"; `Shipping Status` cobre também **'purchased'**.

## Sobre os `Email Review/…` — caso encerrado em 11/09

Não são dele e **não foram feitos pelo painel**. A investigação percorreu os
41 filtros do Gmail (nenhum aplica esses marcadores), os projetos do Apps
Script (nenhum gatilho), o cabeçalho bruto de um e-mail rotulado (nenhum
rastro — rotulagem via API não deixa) e, por fim, o **log de tokens OAuth do
domínio**, que fechou o caso:

- a rotulagem começou entre **9 e 12 de agosto**;
- nesse intervalo **nenhum token novo foi emitido** — quem rotulou usou um
  token que já existia;
- naquela data o **único** app com escrita no Gmail era o conector
  **`Claude for Gmail`** do claude.ai, autorizado em **16/07/2026**;
- o `URACE Administrative AI` (nosso cliente OAuth, os mesmos quatro escopos
  de `adminai/google_auth.py`) só ganhou acesso em **04/09 às 11:09** — a
  manhã em que conectamos o Google, com a triagem das 11:34 rodando sem Gmail
  e a primeira triagem real às 11:53. O IP da AWS é o navegador da extensão,
  que roda na nuvem. Não é invasor.

Foram **sessões do dono no Claude com o conector do Gmail ligado**. Os
marcadores ficam **fora** do manual e a IA os ignora. O dono decidiu não
caçar o responsável: "não quero ir atrás de quem foi".

## Ponto que o dono ainda pode querer mudar

Ele confirmou também os 6 marcadores de `Years 2019-2023`, cujo texto diz
"arquivo morto por ano — a triagem NÃO usa" — e disse **"resolvido"** em
11/09, mantendo como está. Um clique em "não usar" na tela reverte.

Onde vive: `command_center/providers/taxonomia_gmail.py` (o manual),
tabela `gmail_labels` (estado e confirmação), `providers/triagem.py` (a
trava), tela `Gmail → Manual dos marcadores`, artifact do dono.
