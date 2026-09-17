# D-2026-09-17 — Login com a foto da pista, e o azul no lugar do teal

**Decisão do dono (17/09/2026):** o login do Command Center foi redesenhado. Ele viu quatro
opções num canvas (https://claude.ai/artifact/9oTfVcXqWsKZeeLPZsnD7R), escolheu a **B** e
disse "tá ótimo assim". A tela está no ar.

## O que ficou

- **Duas metades.** À esquerda a **foto da pista** (o kart da URACE em Orlando, foto dele),
  cortada na diagonal; sobre o corte, uma **linha vermelha** de 7px. À direita o formulário,
  no cinza do painel.
- **Foto tratada:** preto e branco, 62% de opacidade, contraste leve e **duas máscaras em
  degradê** — uma dissolve a imagem na beirada do corte, a outra no pé da tela, onde fica o
  título. O véu escuro só segura contraste no topo (marca) e embaixo (título).
- **Só o essencial no texto:** marca, o título "A operação inteira / no mesmo lugar" e o
  formulário. Ele marcou a lápis, no canvas, tudo o que não queria: o "01" gigante, o
  parágrafo do subtítulo, o rodapé em mono, a linha "use o e-mail que o administrador
  cadastrou", o bloco "Esqueceu a senha / Suporte" e o rótulo "Orlando · Flórida".
  **Consequência aceita por ele:** quem esquece a senha não tem instrução na tela; quem
  redefine é o administrador.
- **Senha:** o texto "Mostrar" virou um **olho** (38×36, com `aria-label`), porque o texto
  mudava de largura entre "Mostrar" e "Esconder".
- **Celular:** a foto vira faixa no topo, cortada na diagonal, e o formulário desce logo
  abaixo; campos de 52px e fonte 16px (o iOS não dá zoom).
- **Cores:** preto, branco, vermelho e **azul** — o teal saiu do painel inteiro (ver a
  correção no fim de `D-2026-09-17 - Identidade Pit Wall Glass (iOS x F1).md`).

## Onde a foto vive

`command_center/web/public/pista.jpg` — 2000 px de largura, 363 KB (a original tinha
4,2 MB; reduzida com Pillow, qualidade 80, progressiva). Trocar a foto é substituir o
arquivo e rodar o deploy. **Se o arquivo não existir**, o login mostra um fundo escuro de
asfalto: o `onError` do `<img>` troca sozinho e ninguém vê espaço vazio.

## O bug que apareceu no caminho (para não voltar)

A tela estava certa e a foto não aparecia: a rota do SPA só servia `/ops/assets` como
arquivo, então `/ops/pista.jpg` devolvia o `index.html`. O `<img>` recebia HTML, dava erro
de decodificação e a tela caía no fundo de asfalto — parecia que o arquivo não estava lá.
**Corrigido em `main.spa`:** arquivo solto do `dist` (o que o Vite copia de `web/public`)
sai como arquivo, com trava para não escapar do diretório; o resto continua caindo no index.
Teste que segura isso: `test_foto_do_login_e_servida_e_a_rota_do_spa_continua_no_index`.

## Método que ele fixou aqui

Ele desenha em cima do protótipo, no próprio canvas, e o traço **é** o pedido: o que está
circulado sai. Vale continuar lendo os traços antes de mexer no código — e confirmar quando
o traço for ambíguo (aconteceu: entendi que um círculo pedia para tirar a faixa vermelha,
e era o triângulo escuro do corte; ele corrigiu na hora).

[[Command Center]] · [[Italo Silveira]]
