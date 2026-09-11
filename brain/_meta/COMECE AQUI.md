---
tipo: guia
tipo_info: PROCESS
data: 2026-08-31
fonte: interno
responsavel: Italo Silveira
status: ativo
---

# 📖 Comece aqui

Este é o **Cérebro Central da URACE**. Já vem configurado — não há nada
para ajustar.

## Como abrir

**Pelo pacote (.zip):** *Open folder as vault* → a pasta
`URACE-Cerebro`, a que contém `00_SYSTEM`, `40_SISTEMAS` etc.

**Pelo repositório:** *Open folder as vault* → a pasta do repositório
(`Uraceagent`), **não** a `brain/`. Aqui as notas ficam um nível abaixo,
dentro de `brain/`.

⚠️ Abrir o nível errado faz os favoritos e as cores do grafo sumirem — a
configuração vive em `.obsidian/`, e os caminhos dela dependem de onde
está a raiz do vault.

## Onde está cada coisa

| Procurando por | Vá em |
|---|---|
| **[[DocuSign]]**, [[Asana]], [[QuickBooks]], [[Rate Card]], [[Gmail]] | `40_SISTEMAS` |
| Como se faz um trabalho | `10_PROCESSOS` |
| O que foi decidido | `08_DECISOES` |
| O que está quebrado | `13_PROBLEMAS` |
| Clientes, equipe, fornecedores, corridas | `20_ENTIDADES` |
| Valores, prazos, IDs | `00_SYSTEM/PARAMETROS` |
| O que aconteceu em cada dia | `30_DIARIO` |

Mapa completo: [[URACE]]. Estado de hoje: [[Painel do Brain]].

## O DocuSign, especificamente

| O quê | Onde |
|---|---|
| Conta, templates, status, armadilhas | [[DocuSign]] |
| Como a waiver funciona, ponta a ponta | [[Waiver de responsabilidade]] |
| O documento em si | [[Waiver]] |
| As 4 decisões sobre ele | [[D-2026-08-31 - IA envia a waiver]] · [[D-2026-08-31 - Waiver vale um ano]] · [[D-2026-08-31 - Texto do Adult Waiver fica como esta]] · [[D-2026-08-31 - Templates vazios do DocuSign]] |
| As 3 waivers paradas | [[P-07 - Waivers paradas desde junho]] |

## As cores do grafo

🔴 URACE (hub) · 🟡 sistema/parâmetros · 🟢 processos · 🟠 sistemas ·
🔵 entidades · 🟣 empresa · decisões e problemas com cor própria.

O arquivo da era Chase (`90_ARQUIVO`) fica **fora do grafo**. Para vê-lo,
apague o filtro `-path:90_ARQUIVO` na busca do grafo.

## As duas regras ao editar

1. **Valor que muda mora só em [[PARAMETROS]]** — preço, prazo,
   fornecedor, ID. Nenhuma outra nota repete.
2. **Ligue a nota nova com `[[wikilink]]`.** É o link no meio do texto
   que desenha o grafo. Nota sem link é ilha.
