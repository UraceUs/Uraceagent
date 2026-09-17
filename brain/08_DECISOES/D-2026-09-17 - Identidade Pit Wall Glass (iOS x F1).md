# D-2026-09-17 — Identidade "Pit Wall Glass": base iOS com energia F1, só cores da URACE

**Decisão do dono (17/09/2026):** o Command Center inteiro passa a usar a identidade que ele aprovou
no canvas de proposta (https://claude.ai/artifact/Uh68Zxpjy2GHUnQRtBfMAv), inspirada no site da
Fórmula 1, nos templates Revio / Campaign Canvas / Request Tracker e, como base, no design do iOS
atual (Liquid Glass do iOS 26, refinado no iOS 27). Correção dele no meio: **"use somente as cores
da identidade visual da URACE"** — nada de paleta das referências.

## O que é
- **Cores**: exatamente os tokens que o painel já tinha. Fundo `#131211`, marfim `#EFEBE5`, vermelho
  URACE `#E8563E` (claro `#C4321F`), teal `#5DAFB2` (claro `#1F5F63`), estados ok/atenção/crítico/info.
  Vidro = marfim translúcido (6–10%). **Preto é o padrão**; claro é opção no menu da pessoa.
- **Forma (iOS)**: superfícies de vidro (blur + borda fina), botões em cápsula, cantos concêntricos
  (28 / 20 / 12), título grande (Geist 700, 34 px), listas agrupadas com ícone à esquerda e seta à
  direita, controle segmentado no lugar das abas sublinhadas, switch iOS, janelas centralizadas no
  desktop e **folha que sobe de baixo** no celular.
- **Energia (F1)**: um vermelho por tela (ação principal da página ou selo); nas listas, a ação do
  item é teal. Títulos largos em caixa alta (Titillium Web) só nos rótulos e nos momentos de pista.
- **Fontes**: Geist (corpo, substituto web da SF Pro), Titillium Web (rótulos F1), Geist Mono.
  Saíram Barlow / Barlow Condensed / IBM Plex Mono.
- **Ícones**: conjunto próprio de traço 1,9 px no padrão SF Symbols (`components/Icon.tsx`), em
  todo item do menu e nas barras.
- **Menu**: quatro grupos por intenção — Hoje (Hoje, Atenção, Corridas) · Pessoas (Clientes, Funil,
  Chat) · Sistemas (Asana, DocuSign, Gmail, QuickBooks) · Inteligência (AI Command, Aprovações,
  Automação, O que a IA pode fazer, Atividade) · Administração. No celular, barra de abas de vidro
  com cinco itens (Hoje, Atenção, Clientes, IA, Mais) — "Mais" abre o menu completo.
- **Tela inicial** chama "Hoje" (era "Dashboard"), com a data em vermelho por cima do título.

## Como foi feito (para não desfazer sem querer)
- `styles/tokens.css`: `:root` é o tema escuro; `[data-theme="light"]` é o claro. Fontes e raios novos.
- `styles/glass.css` (novo, carregado depois): redefine as peças que todas as telas usam — por isso
  a identidade vale para o sistema inteiro sem tocar na lógica de cada página.
- `components/Shell.tsx`: menu com ícones, race control em cápsulas dentro da barra de topo, barra de abas.
- Nenhuma mudança de backend. 181 testes; capturas em desktop e celular, escuro e claro.

---

## Correção de 17/09, mais tarde: o teal saiu, entrou o azul

Ordem dele, ao aprovar o login novo: *"coloca sempre no nosso padrão de azul, preto,
branco e vermelho"*. O teal `#5DAFB2` **não é mais** cor da casa. O token continua sendo
`--accent`, agora com o azul do kart da foto: `#1E5BC6` no tema escuro e `#1B4FA8` no claro
(`--accent-ink` `#6FA0EE` / `#173F86`). Todo realce, foco de campo, link e chip do painel
seguiu o token. **O hex oficial da marca nunca foi documentado** — se ele passar o código
exato, é uma linha em `styles/tokens.css`.

Também mudou o login: ver `D-2026-09-17 - Login com a foto da pista.md`.
