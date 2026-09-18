# D-2026-09-18 — As travas respondidas, uma a uma

**Contexto.** Pedi a lista do que estava travado e precisava de ação nossa; ele pediu para
responder dentro de cada tema e respondeu **os 19** numa página própria
(https://claude.ai/artifact/8r2VGLEPKBuoKCg9kjP9UZ). Esta nota é o registro do que ele
decidiu. Cada decisão aqui **substitui** o que estava aberto em [[Conflitos e lacunas]] ou
em [[Problemas]].

## O que ele decidiu

| # | Assunto | Decisão |
|---|---|---|
| C-02 | Terça é dia de serviço? | **É dia de serviço, sim** — a coluna TUESDAY do Asana vale |
| U-04 | Desconto | **Existe em casos raros, com o motivo explicado.** Continua decisão dele, caso a caso |
| U-01 | Cutucar quem não assinou a waiver | **Não.** A IA avisa o dono, como já fazia |
| U-03 | Devolução do security deposit | **A IA prepara, ele devolve** — e avisa peças e serviços a subtrair |
| U-05 | Data do serviço a partir da invoice paga | **Já está na tarefa do Asana** |
| U-06 | Papel do Lucas Azaro | **Marketing / vendas (closer) / comercial** |
| U-08 | "Offsight" | **Não existe: pode esquecer** |
| Azul | Hex oficial da marca | **`#0057B4`** (o painel usava `#1E5BC6`, tirado da foto do kart) |
| Pit Wall | Publicar ou aposentar | **Aposentar: tirar a rota** |
| Agente | `APLICAR=1`? | **Ligar para as rotinas diárias** |
| Vendas | Quem roda a venda de teste | **Outra pessoa** — pelo papel dito em U-06, o Lucas |
| P-04 | US$ 185 mil em dois nomes | **Stand-by por ora** |
| P-07 | Três waivers paradas | **Reenviar as três** |
| P-06 | Catálogo do QuickBooks | **Atualizar pela Rate Card**; item sem Rate Card pega o valor das últimas invoices |
| P-05 | Security deposit | **Primeiro serviço, ou depois que o anterior voltou** (com dedução de peça) |
| C-01 | As 4 células da planilha | **A Rate Card manda sempre** e é mantida no Drive: "sempre consultar lá" |
| P-01/02/03 | Higiene do Asana | **A IA pode arrumar o que for seguro** |
| P-08 | Order Number com URL | **A IA pode extrair o código do link** |
| Deploy | O que está pronto e não no ar | **Ele roda hoje** |

## O que muda no sistema, e o que ainda não

**Entrou no mesmo dia:** o azul oficial em todo o painel (`--accent` `#0057B4`, com
`--accent-ink` claro para texto, porque o azul oficial é escuro demais para ler no preto),
e o script que aposenta o Pit Wall tirando a rota do Caddy com backup e prova.

**Fica esperando trabalho meu, com plano antes:**

- **Catálogo (P-06)** — 896 itens. Não se atualiza preço em massa sem diff revisado: primeiro
  a lista "item · preço hoje · preço novo · de onde veio", ele aprova, e só então aplica.
- **`APLICAR=1`** — antes de ligar, a lista do que o agente passaria a escrever sozinho nas
  rotinas, e o que continua exigindo aprovação. Ligar sem essa lista seria ligar no escuro.
- **Higiene do Asana (P-01/02/03)** e **Order Number (P-08)** — "o que for seguro" precisa de
  definição em código: mover serviço concluído, aplicar o modelo de 12 subtarefas, preencher
  campo que o painel já sabe, extrair o código de rastreio do link. Cada uma com política.
- **Rate Card do Drive** — se a planilha é a fonte e muda, o painel deveria **ler de lá**, não
  guardar cópia. Vale virar sincronia, como as outras cinco fontes.

**Não é trabalho de sistema:** reenviar as três waivers (P-07) é um clique cada no painel —
a do Matthew Hubbard precisa da correção do e-mail antes, porque o servidor dele recusou.

[[Command Center]] · [[Italo Silveira]] · [[Conflitos e lacunas]] · [[Problemas]] · [[PARAMETROS]]
