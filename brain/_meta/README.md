---
tipo: meta
atualizado_em: 2026-08-31
---

# Como o cérebro funciona

[[URACE]] · [[Painel do Brain]] · [[PARAMETROS]]

Este diretório (`brain/`) é o **segundo cérebro da URACE**: o que a IA
administrativa sabe sobre a operação. Aberto no Obsidian, é também a
interface humana desse conhecimento — o mesmo conteúdo, dois leitores.

> Este vault era do **Chase**, o agente de vendas, até 28/08/2026. O
> projeto pivotou para o **Administrative AI** e o conteúdo de vendas foi
> para `90_ARQUIVO/vendas-chase/`. Se você achar uma nota falando de
> lead, objeção ou qualificação, ela é histórica.

## As pastas

| Pasta | O que é | Regra |
|---|---|---|
| `00_SYSTEM` | comportamento da IA | **[[PARAMETROS]] é o único lugar de alteração** de valor, prazo, fornecedor e ID |
| `10_PROCESSOS` | como o trabalho é feito, passo a passo | ditado pelo dono; a IA não inventa processo |
| `20_ENTIDADES` | clientes, corridas, equipe, fornecedores, serviços, locais | uma nota por coisa real |
| `30_DIARIO` | o que aconteceu em cada dia | append, nunca reescrever o passado |
| `40_SISTEMAS` | Asana, Gmail, QuickBooks, Rate Card, DocuSign, Calendar | os fatos da conta **e as armadilhas** |
| `90_ARQUIVO` | fora de uso | registro, não referência |
| `_dashboards` · `_meta` | painel e este guia | — |

## As duas regras estruturais

**1. Valor que muda mora só em [[PARAMETROS]].**
Nenhuma outra nota — e nenhuma skill — repete preço, prazo, fornecedor
ou ID. Todas apontam para lá. O dono muda num lugar e o sistema inteiro
acompanha. Toda alteração vira linha no histórico do fim daquela nota.

**2. O que liga o grafo é o wikilink, não o frontmatter.**
`[[Assim]]`. Frontmatter serve para tipo e data; **quem desenha o grafo
é o link no meio do texto**. Uma nota sem wikilink é uma ilha — e ilha
não é conhecimento, é arquivo solto.

## Convenções

- **Chave externa é identidade**, nunca o nome: `asana_gid`, id do
  [[QuickBooks]], `envelopeId` do [[DocuSign]], número do pedido.
  "Charlie Marron" e "Charles Andrew Marron" são a mesma pessoa; o id não.
- **Nome de arquivo é o nome da nota.** Sem dois arquivos com o mesmo
  nome no vault inteiro — o wikilink fica ambíguo.
- **Português, direto, sem enfeite.** É documento de trabalho.
- **Fato vem com fonte.** Se veio de uma sonda, dizer de onde e quando.
  Se não tem fonte, não entra: a IA **escala em vez de deduzir**.

## Como a IA usa isto

As **skills** (em `skills/`, uma por aplicação) carregam o julgamento —
o que fazer, o que nunca fazer, o tom. Elas **não guardam valores**:
leem de [[PARAMETROS]] e dos processos daqui.

Ordem de trabalho da IA, sempre a mesma: **ler o cérebro antes de agir,
escrever nele depois** — comentário na tarefa do [[Asana]] e linha no diário do dia. "Por que a IA fez isso?" tem que ter resposta.

## Como adicionar conhecimento (humano)

1. Criar o `.md` na pasta certa, com frontmatter simples
   (`tipo`, `atualizado_em`).
2. **Ligar com wikilinks** ao que já existe — pelo menos um para o hub
   ou para a nota-índice da área.
3. Se for valor que muda, **não escreva aqui**: coloque em
   [[PARAMETROS]] e aponte.
4. Commit + push, ou o botão de sync do plugin Git do Obsidian
   (`Ctrl+P` → *Git: Commit-and-sync*).
