# D-2026-09-18 — Menu em trilho que revela, e a tela manda no layout

**Decisão do dono (18/09/2026).** Ele pediu que o menu lateral abrisse e fechasse, com o
layout acompanhando o tamanho da tela no computador e no celular, e **opções antes do
código**. Viu três num canvas (https://claude.ai/artifact/FZecNeJVPAkLUzDnR2cvSb) e escolheu
a **C**, com mais duas decisões no mesmo passo.

## O que ficou

- **Fechado = trilho de 68px** com os ícones à vista. O contador de cada item vira uma
  **bolinha** da cor dele, o título de grupo vira um fio, e o rótulo sai.
- **Ao encostar o mouse — ou ao chegar pelo teclado — o menu abre inteiro POR CIMA do
  conteúdo**, que não se mexe um pixel. É o que separa a opção C da A: leitura completa sem
  perder largura de tela.
- **O estado fica guardado no navegador** (`localStorage` `cc.menu`), por pessoa e por
  aparelho. Quem fecha o menu encontra fechado na próxima vez. Não vai para o servidor: é
  preferência de tela, não dado da operação.
- **Largura em monitor grande:** limitada só onde se lê (ficha do cliente, manual dos
  marcadores, o que a IA pode fazer, minha conta — 1080px). Quadro, tabela larga, calendário
  e chat usam a tela inteira. O resto fica no limite padrão, agora centralizado.
- **No celular nada muda no menu:** continua gaveta por cima com o fundo escurecido, e a
  barra de abas embaixo. O trilho é coisa de computador (≥901px).

## Por que não as outras

- **A (só trilho)** obriga a abrir o menu para ler um rótulo, e o ícone sozinho não diz
  "Automação e memória" de "Atividade da IA".
- **B (menu somindo)** dá a maior largura, mas enquanto fechado ele perde a orientação e os
  contadores — e são eles que dizem que tem coisa esperando (15 de atenção, 18 no Kommo).

## O que o celular ensinou no mesmo dia

Olhar capturas de 390px achou o que a varredura automática não pegava: **o título de toda
página estava alinhado à direita** no celular, porque o `align-items:flex-end` do vidro
continuava valendo depois de o layout virar coluna. Agora vale só no computador. Junto:
calendário do Asana abre na **Lista** no celular, a lista de tarefas virou cartão com rótulo,
e todo botão tem 40px e todo campo 44px com fonte 16px (para o iOS não dar zoom).

O detalhe todo está em [[30_DIARIO/2026-09-18]] e no manual, seção da interface.

[[Command Center]] · [[Italo Silveira]] · [[D-2026-09-17 - Login com a foto da pista]]
