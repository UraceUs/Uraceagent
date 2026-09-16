---
tipo: projeto
data: 2026-09-16
fonte: pedido do dono (brief completo de redesign) + auditoria do código do frontend
responsavel: Italo Silveira
status: primeira rodada entregue (16/09)
---

# Command Center — Redesign "Pit Wall"

[[VPS e OpenClaw]] · [[D-2026-09-09 - Design para cognicao rapida, cada link no seu item]] · [[Administrative AI - Estado completo em 2026-09-04]]

Pedido do dono (16/09): *"reformulação completa do visual e da experiência de uso, com
foco em tornar a interface intuitiva, rápida de entender, organizada e fácil de usar, sem
perder a identidade. Conceito: Formula 1 Pit Wall moderno. Clareza > estética; usabilidade >
quantidade; hierarquia > decoração. Motorsport profissional, não interface gamer."*

Processo que ele pediu, nesta ordem: **auditoria → direção → design system → redesign →
revisão de UX → refinamento.** Este documento é a auditoria e a direção; o design system
vive em `command_center/web/src/styles/tokens.css`; o redesign vai em commits por tela.

---

## ETAPA 1 — Auditoria do que existe

### A identidade (o que fica)

Ela já **se chama Pit Wall** — `tokens.css` abre com "Identidade aprovada do Pit Wall".
Não é uma troca; é a mesma identidade levada até o fim.

| Elemento | Como está | Veredito |
|---|---|---|
| Tipografia | **Barlow** (texto) · **Barlow Condensed** (títulos, chips, rótulos, em caixa alta com tracking) · **IBM Plex Mono** (datas, números, ids) | **fica.** É a família do motorsport: condensada para rótulo, mono para telemetria. |
| Paleta clara | papel quente `#F6F3EF`, superfície branca, tinta `#191714`, régua `#DED8D0` | fica; ganha um nível a mais de superfície e uma régua mais forte para "painel". |
| Paleta escura | `#131211` / `#1C1A18` / `#242120` | fica; é a que ele usa (as telas que mandou são escuras). É onde o Pit Wall mais convence. |
| Marca | `URACE` em vermelho `#C4321F` + "Command Center" em condensado; "OPERATIONS · ORLANDO" em mono | fica intacta. |
| Vermelho da marca | usado com parcimônia: contador do menu, barra do item ativo, anel do "hoje" | **fica raro.** O brief é explícito: sem excesso de vermelho. Vermelho = marca e "agora"; **nunca** = erro. |
| Verde-petróleo `#1F5F63` (accent) | botão primário, links, seleção | fica como a cor de **ação**. |
| Estados | ok `#2C7A54` · warn `#9C6B12` · crit `#A8352A` · info `#2F5D9E`, cada um com "wash" | ficam; ganham ícone e nome, porque hoje dependem só de cor em vários lugares. |
| Raio | 3px | fica. Canto reto é o que dá a cara técnica. |
| Terminologia | português direto, sem jargão de software ("Precisa de atenção", "Só abertas", "esperando você") | fica. É um ativo. |
| Regra de 09/09 | "cada link no seu item, nunca uma fila de links no topo" | fica como lei. |

### As telas, uma a uma (o que a pessoa veio fazer × o que a tela mostra)

**Shell (menu + topo).** Menu lateral escuro com 5 grupos e 18 entradas; topo com busca
⌘K, sino e avatar. *Problemas:* o menu é uma lista plana — "Manual dos marcadores" é
sub-item do Gmail mas outros sub-fluxos não são; não há "onde estou" além do item aceso;
o estado do sistema (integrações, sincronia, IA rodando) não aparece em lugar nenhum fixo
— a pessoa tem de ir ao Dashboard para saber se o espelho é de hoje. O sino repete o que
"Precisa de atenção" já mostra.

**Dashboard.** 6 KPIs + 3 KPIs + atenção + integrações + sincronia. *3 segundos:* a pessoa
vê nove números do mesmo tamanho e não sabe qual importa. "Ações da IA hoje" tem o mesmo
peso que "Vencidos". Integrações e sincronia são duas tabelas que dizem quase a mesma
coisa. O botão "Sincronizar agora" fica no cabeçalho, longe da informação de que o espelho
está velho. **Aqui é onde o Pit Wall tem de nascer**: uma faixa de estado (o que está
rodando, o que está velho, o que está quebrado), um bloco "agora" (hoje na pista, o que
precisa de gente), e o resto abaixo.

**Precisa de atenção.** Boa: nível por barra colorida, fatos do item sem abrir nada, balão
"Instruir a IA". *Problemas:* o nível está só na cor da barra e num chip — sem ícone;
os botões de ação ficam na mesma linha que o link de origem e o chip, e "Ocultar" tem o
mesmo peso visual que "Abrir cliente"; filtros por nível são tabs, mas contam tudo em um
único "Itens".

**Clientes.** Tabela densa e útil (próximo serviço com HOJE/AMANHÃ, waiver, e-mails sem
resposta). *Problemas:* três linhas de ferramentas antes da tabela (filtros; "unir",
"puxar histórico", texto explicativo; duplicados) — a tabela começa abaixo da dobra;
"Varrer plataformas" ao lado de "Novo cliente" com o mesmo peso; a explicação "Puxa todas
as tarefas…" é um parágrafo no meio da barra de ferramentas.

**Card do cliente.** Cabeçalho forte (nome, status, idade, contatos), 5 KPIs, "Dados
completos" fechado, 9 abas. *Problemas:* 9 abas são muitas — "Linha do tempo" e
"Serviços/Waivers/E-mails/Invoices" são a mesma história em cortes diferentes; a
banner de risco (serviço sem waiver) está certa e é o único lugar onde a hierarquia
está clara. O menu "⋯" com "Buscar no Gmail e DocuSign" esconde uma ação que o dono usa.

**Asana.** Calendário/quadro/lista, modal da tarefa com IA. Depois de 16/09 o quadro abre
com abertas e recentes no topo. *Problemas:* as colunas TUESDAY…SUNDAY têm o mesmo peso
que RACES e Finished Services; o card não mostra o cliente com destaque nem se falta
waiver/invoice — o que o pit wall mostraria ("pronto para a pista?").

**DocuSign.** Tabela por envelope, abas, busca e Internos (16/09). *Problemas:* o status
depende do chip (texto ajuda); "Signatário / Cliente-piloto" em duas colunas com
sub-linhas explicando o vínculo — bom para auditoria, pesado para o dia a dia.

**Gmail.** Três colunas como um cliente de e-mail, marcadores com contagem, sugestão da
IA por thread. É a tela mais "ferramenta" do painel e funciona. *Problemas:* dois botões
✦ ("Triar" e "Só sugerir") disputam a atenção; o texto do cabeçalho explica a rotina a
cada visita.

**AI Command.** Conversa por pessoa, ações como cartões com prévia e aprovação, ✦ de
sugestões (16/09). *Problemas:* a mensagem enviada mostra o **prompt inteiro** com o
contexto técnico (CLIENTE: {...}, WAIVERS NO ESPELHO: []) — a pessoa lê JSON; o cartão
de ação mistura 3 chips (sistema, política, status) do mesmo tamanho; "Aprovar e enviar"
é o botão mais importante do sistema e é `sm`.

**Aprovações / Atividade / Automação / Integrações / Auditoria / Políticas / Usuários.**
Consistentes entre si (page-h + Section + tabela). Automação tem um bom padrão (regra =
título + o que faz + ligada/desligada). Integrações repete o cabeçalho `h1` em cada
sistema (5 títulos grandes numa página).

**Login.** Meia página escura com o anel vermelho decorativo, formulário limpo. Fica;
só ganha o mesmo tratamento de foco e feedback do resto.

### Inconsistências encontradas (o que o design system tem de resolver)

1. **Estado só por cor.** `Chip` tem `dot` opcional, mas nenhum ícone; a barra `.lv` da
   atenção é só cor. Daltônico não distingue HIGH de MEDIUM.
2. **Três jeitos de dizer "esperando":** `PENDING`, `esperando você`, `PROPOSED`,
   `aguardando confirmação`. E status crus em inglês vazando na tela (`ACTIVE`,
   `completed`, `open`, `PROPOSED`).
3. **Botões sem escala clara.** `primary` teal e `btn` neutro; "danger" existe em duas
   versões (preenchido e contorno). Botões de ação primária aparecem em `sm` onde
   importam (Aprovar) e em tamanho cheio onde não importam (↻).
4. **Cabeçalho de página** (`page-h`) tem título + subtítulo explicativo de 1–2 frases em
   toda tela. A explicação é útil na primeira vez e ruído na centésima.
5. **Foco de teclado** só existe no `.input`. Botões, links do menu, linhas clicáveis e
   chips-botão não têm `:focus-visible`.
6. **Alvos de clique:** `.ic` (🗑, ↻) tem ~24px; `.lchip` e `.tabs button` são pequenos
   no celular.
7. **Feedback:** o `toast` some em 5 s e não tem ícone nem título; sucesso e erro só
   diferem pela cor de fundo.
8. **Mobile:** o menu vira gaveta (bom), o Gmail empilha (bom), mas tabelas de 8 colunas
   só rolam de lado; KPIs viram uma coluna de 9 cartões; o quadro do Asana rola de lado
   sem indicação.
9. **Densidade sem hierarquia:** `card` + `card-h` + `h2` iguais para "Precisa de atenção"
   (nível 1) e "Sincronia" (nível 4).

### O que já funciona bem (e não se mexe)

- ⌘K com busca + "perguntar à IA" — é o comando do pit wall.
- `.att` (item de atenção com barra de nível, fatos e ações) — a melhor peça do sistema.
- Banners de risco no card do cliente ("Serviço em HOJE sem waiver assinada").
- Confirmação em modal (`Perguntar`) no lugar do diálogo do navegador.
- "HOJE / AMANHÃ / em N d" na coluna de próximo serviço.
- Cada link externo junto do item (`SysLink`).
- Tema escuro pronto e bem resolvido.

---

## ETAPA 2 — Direção visual

**Identidade atual + Pit Wall moderno + SaaS premium.** Em uma frase: *o painel passa a
se comportar como uma tela de race control — estado no topo, prioridade à esquerda,
número grande só onde a decisão depende dele — sem mudar a cara que ele já tem.*

O que muda, e por quê:

1. **Uma faixa de estado no topo de toda tela ("race control bar").** Sincronia (há quanto
   tempo), integrações (quantas ok / o que caiu), IA (rodando? esperando aprovação?),
   e o relógio da operação. É o "tudo sob controle" pedido: a pessoa não precisa ir ao
   Dashboard para saber se o espelho é de hoje. Substitui o sino, que só repetia a
   atenção.
2. **Hierarquia em quatro níveis, em código.** Título de página menor e mais quieto;
   KPIs com dois tamanhos (decisão × contexto); seções com dois pesos (`Section` nível 1
   com barra de cor à esquerda, nível 2 sem). O subtítulo explicativo vira um "?" que abre
   sob demanda — nível 4.
3. **Linguagem de estado com ícone + cor + texto.** Um único mapa: `ok ●`, `atenção ▲`,
   `crítico ✕`, `em andamento ◐`, `esperando ○`, `feito ✓`, `desligado —`. Chip ganha o
   glifo; a barra de nível da atenção ganha o glifo no topo. Nada depende só de cor.
4. **Botões com uma escala só.** `primary` (a ação da tela, 1 por contexto), `default`,
   `quiet` (ghost), `danger` (sempre contorno, preenche no hover). Ação que envia algo
   para fora (invoice, waiver, e-mail) ganha o ícone `↗` no rótulo — "isso sai da empresa".
5. **Números como telemetria.** Onde o número decide (hoje na pista, vencidos, esperando
   aprovação), ele é grande, tabular, com a tendência ou o "desde quando" embaixo. Onde
   o número só informa (ações da IA hoje), ele é pequeno e à direita.
6. **Micro-interações de precisão, não de espetáculo.** Transição de 120 ms em hover/
   foco; barra de progresso fina no topo durante sincronia/triagem; o toast ganha ícone,
   título e uma barra de tempo; o `spin` continua. Nada de brilho, glassmorphism ou
   gradiente. `prefers-reduced-motion` respeitado.
7. **Foco e alvo.** `:focus-visible` com anel de 2 px na cor de ação em tudo que é
   clicável; alvo mínimo de 36 px em botões-ícone; chips-botão com padding maior.
8. **Mobile repensado, não encolhido.** KPIs em grade 2×N com o número menor; tabelas
   principais (clientes, envelopes) viram lista de cartões abaixo de 700 px, com as 3
   informações que decidem; o quadro do Asana mostra a coluna do dia por padrão com
   setas.
9. **Vermelho só para a marca e para "agora".** Erro é `crit` (terracota), não vermelho
   da marca. O anel de "hoje" e a barra do item de menu ativo continuam.

O que **não** muda: fontes, paleta, raio, tema escuro, terminologia, estrutura de rotas,
nenhuma API. O backend não sabe que houve redesign.

---

## ETAPA 3 — Design system (o que entra em `tokens.css`)

Padrões, cada um com o problema que resolve:

- **Escala tipográfica fixa:** 11 / 12.5 / 14 / 16 / 20 / 28 / 40, mono para número.
- **Espaçamento em 4 px:** 4, 8, 12, 16, 24, 32. Cartões com 16; listas com 12.
- **Superfícies:** `paper` (fundo) → `surface` (cartão) → `surface-2` (cabeçalho/hover)
  → `surface-3` (pressionado). Régua `rule` e `rule-strong`.
- **Estado:** `ok / warn / crit / info / run / wait / off`, cada um com cor, wash e glifo.
  Componente `Status` (ícone + texto) substitui `Chip` onde o chip dizia estado.
- **Botão:** `btn` (default) · `primary` · `quiet` · `danger` · tamanhos `sm` (28 px) e
  normal (36 px). Todo botão com `:focus-visible` e `:active`.
- **Cartão:** `card` · `card.lead` (nível 1, barra à esquerda) · `card.quiet` (nível 3).
- **KPI:** `kpi` (grande, decide) · `kpi.sm` (contexto). Sempre rótulo em condensado,
  número tabular, rodapé em texto.
- **Tabela:** cabeçalho pegajoso, zebra sutil, linha clicável com `›` à direita.
- **Tabs / sub-tabs:** uma só peça; contagem em mono.
- **Formulário:** rótulo condensado, `input` com foco, erro inline abaixo do campo
  (`.field.err`), ajuda em `small muted`.
- **Estados de tela:** `Loading` (esqueleto), `Empty` (título + próxima ação), `Error`
  (o que aconteceu + tentar de novo). Iguais em todas as telas.
- **Feedback:** `toast` com ícone, título opcional e barra de tempo; `Banner` com ícone.
- **Modal:** cabeçalho fixo com título + fechar; corpo rola; rodapé com ações à direita.
- **Tooltip:** `title` nativo continua (é acessível); nada custom.
- **Movimento:** `--t: 120ms`, `--ease: cubic-bezier(.2,.7,.2,1)`; barra de progresso
  `.progress` de 2 px.

---

## ETAPA 4 — Redesign, por impacto

Ordem: **Shell + faixa de estado → Dashboard → Precisa de atenção → AI Command (mensagem
e cartão de ação) → Clientes + card → Asana (quadro) → DocuSign/Gmail → o resto.**

Cada tela responde às perguntas do brief no commit: o que a pessoa veio fazer, qual é a
ação principal, o que sai, o que sobe, o que desce para "sob demanda".

## ETAPAS 5 e 6 — Revisão e refinamento

Com o painel rodando local (banco de demonstração + Chromium), telas em 1440, 1024 e 390
px, no claro e no escuro, antes e depois. O que confundir, muda. O que não agrega, sai.

---

## O que foi feito na primeira rodada (16/09)

Comparação feita com o painel rodando local (banco de demonstração fictício, Chromium),
em 1440 e 390 px, claro e escuro, antes e depois. Nenhuma API mudou; o backend não sabe
que houve redesign.

**Design system (`tokens.css`, `ui.tsx`):** tokens de movimento (120 ms) e de alvo
(36 px); `:focus-visible` em tudo que é clicável; `prefers-reduced-motion`; botões numa
escala só (`primary` · padrão · `quiet` · `danger` só contorno); **`Status`** (cor +
glifo + nome em português: ✓ ◐ ○ ▲ ✕ —) no lugar do chip cru em inglês; `Chip` com
glifo; `Kpi` grande (`lead`, decide) e pequeno; **`Strip`** (fita de contexto);
**`PageHeader`** (título quieto, ação à direita, explicação atrás do "?");
**`Progress`** (barra de 2 px no topo durante sincronia/triagem); toast com ícone, título
e barra de tempo; banner com ícone; tabela `rsp` que vira lista de cartões no celular;
`hide-md`; `clamp2`.

**Shell:** a faixa **race control** sob a busca, em toda tela — Espelho (há quanto
tempo), Sistemas (n/n e quem caiu), Atenção (itens e críticos), IA (o que espera você),
relógio. Cada item leva para onde se resolve. O sino saiu (repetia a atenção). Contador
do menu: vermelho da marca só quando há crítico; âmbar para o resto. Topo pegajoso
inteiro (busca + faixa).

**Dashboard:** 4 números que decidem (Pista hoje · Precisa de gente · Esperando você ·
Waivers abertas), fita com 6 de contexto, atenção (6 primeiros) à esquerda, uma tabela
só de Sistemas à direita (integração + sincronia juntas).

**Precisa de atenção:** nível com glifo nos chips e nas tabs; "Instruir a IA" primeiro,
"Abrir cliente" ao lado, "ocultar" quieto; título da seção diz a ordem.

**AI Command:** a mensagem da pessoa mostra **só o que ela escreveu** (o contexto
técnico fica atrás de "ver o que a IA recebeu"); instrução vinda de um item ganha a
etiqueta "✦ instrução em: …"; cartão de ação com título, estado com glifo, linha de
sistema · política, aviso "sai da empresa: aprovar = enviar" e o **Aprovar e enviar ↗**
em tamanho cheio; borda à esquerda por estado (esperando/feita/falhou).

**Clientes:** uma barra só; Varrer/Unir/Puxar histórico atrás do ⋯; status e waiver com
glifo; tabela vira cartões no celular; coluna "Último" some abaixo de 1300 px.

**Asana:** quadro marca a coluna de hoje (barra na cor da marca), cartão mostra QUEM em
condensado, HOJE/amanhã, subtarefas e "✓ waiver"; Finished Services apagado.

**DocuSign / Gmail / Integrações / Aprovações / Automação / Corridas / Auditoria /
Políticas / Usuários / Conta:** mesmo cabeçalho (com estado da integração ao lado do
título), tabelas responsivas onde há tabela principal, um ✦ primário só, Integrações em
cartões compactos com o motivo do erro em português e os detalhes técnicos fechados.

### O que ficou para a segunda rodada

- Card do cliente: 9 abas → agrupar (Linha do tempo · Serviços e waivers · Dinheiro ·
  IA); "Buscar no Gmail e DocuSign" sair do ⋯.
- Gmail em celular: lista e leitura em duas telas, não empilhadas.
- Kommo (Chat/Funil): mesmo tratamento do cabeçalho e dos estados (ainda usa `page-h`
  próprio dentro do `.mail`).
- Login: foco e feedback já valem pelo design system; sem mudança visual.
- Ícones: continuam glifos de texto (✓ ▲ ✕ ○ ◐ ✦ ↗); se um dia entrar um set de ícones,
  entra por aqui, num lugar só.

## Referência de movimento (16/09): inspora.design, categoria Motion

O dono mandou usar `https://www.inspora.design/?category=Motion` como referência. O domínio
está **bloqueado pelo proxy** do ambiente de trabalho; pela busca, é um arquivo curado de
trabalho visual e a categoria Motion são peças animadas (transições de produto,
micro-interações, motion de marca). Sem ver as peças que ele tem em mente, entrou só a
camada que o brief já pedia — *velocidade, precisão, resposta; nada que distraia*:

- entrada de página e de listas em 220–240 ms com escalonamento de 30 ms por item;
- número de KPI e da fita **conta até o valor** em 400 ms (telemetria chegando, não pulando);
- sublinhado das tabs desliza; toast entra de baixo; modal sobe 6 px;
- cartão e KPI clicável levantam 1 px no hover, com a borda na cor de ação;
- glifo ◐ pulsa enquanto algo roda; tudo desligado em `prefers-reduced-motion`.

Pendente: ele mandar 3–6 capturas ou gravações das peças do inspora que quer de referência,
para calibrar curva, duração e o que mais merece movimento.
