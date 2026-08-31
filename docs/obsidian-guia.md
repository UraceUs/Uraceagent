# Abrir o segundo cérebro no Obsidian

O vault já vem configurado no repositório. Não há nada para ajustar.

## 4 passos

1. Instalar o [Obsidian](https://obsidian.md) (grátis).
2. **Open folder as vault** → escolher a pasta do repositório
   (`Uraceagent`), não a `brain/`.
3. Aceitar o plugin **Git** quando ele perguntar (é o que deixa você
   puxar e publicar sem terminal).
4. Abrir **🏁 URACE — comece aqui**, já marcado na barra lateral.

## O que já vem pronto

| Item | Como está |
|---|---|
| **Favoritos** | URACE (hub) · Painel · PARÂMETROS · processos · sistemas · diário |
| **Grafo** | colorido por pasta, arquivo morto escondido, só o cérebro aparece |
| **Nota nova** | cai em `brain/30_DIARIO` |
| **Código escondido** | `salesagent/`, `adminai/` e afins não poluem a barra lateral |
| **Anexos** | vão para `brain/_anexos` |

### As cores do grafo

| Cor | Pasta |
|---|---|
| 🔴 vermelho | `URACE` — o hub |
| 🟡 amarelo | `00_SYSTEM` — parâmetros e comportamento |
| 🟢 verde | `10_PROCESSOS` — como o trabalho é feito |
| 🟠 laranja | `40_SISTEMAS` — Asana, QuickBooks, DocuSign… |
| 🔵 azul | `20_ENTIDADES` — clientes, corridas, equipe |
| 🟣 roxo | `30_DIARIO` — o que aconteceu em cada dia |

O arquivo do Chase (`90_ARQUIVO`) fica **fora do grafo** — é histórico,
não referência. Para vê-lo, apague o filtro `-path:90_ARQUIVO` na busca
do grafo.

## Publicar uma alteração

`Ctrl+P` → **Git: Commit-and-sync**. O plugin puxa antes de enviar.

## As duas regras ao editar

1. **Valor que muda mora só em `PARAMETROS`.** Preço, prazo, fornecedor,
   ID. Mudou lá, mudou no sistema inteiro — nenhuma outra nota repete.
2. **Ligue a nota nova com `[[wikilink]]`.** É o link no meio do texto
   que desenha o grafo, não o frontmatter. Nota sem link é ilha.

Detalhes: **Como o cérebro funciona** (`brain/_meta/README.md`).
