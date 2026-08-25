---
type: system
category: meta
topic: como-usar-o-brain
priority: high
status: active
source: internal
last_updated: 2026-08-25
tags: [meta, schema, regras]
---

# Como o Sales Brain funciona

Este diretório (`brain/`) é a **knowledge base do agente de vendas Chase**
— e, aberto no Obsidian, é a interface humana desse conhecimento. O mesmo
conteúdo, dois leitores:

- **Humanos** (Italo/Eduardo): abrem o repositório no Obsidian, leem,
  editam e aprovam conhecimento. `git push` publica.
- **A IA** (Chase, via ponte): nunca lê estes arquivos direto. Um índice de
  busca (`brain/indexer.py` → SQLite FTS5 no servidor) entrega só os
  trechos relevantes de documentos **aprovados** a cada conversa.

## O schema de frontmatter (obrigatório em todo documento)

```yaml
---
type: sales_knowledge        # ver tabela abaixo
category: objection          # subcategoria livre, minúsculas, sem espaço
topic: preco                 # o assunto específico, 1-3 palavras
priority: high               # high | medium | low
status: active               # ver ciclo de vida abaixo
source: internal             # internal | italo | conversa_real | fonte_externa
last_updated: 2026-08-25     # AAAA-MM-DD, atualizar a cada edição
tags: [vendas, objecao, preco]
aliases: [price, pricing]    # OPCIONAL: palavras-chave em INGLÊS/ESPANHOL
---
```

| Campo | Como o agente usa |
|---|---|
| `type` | Filtro grosso do retrieval. Valores válidos: `system`, `company_knowledge`, `product_knowledge`, `sales_knowledge`, `learning`, `faq` |
| `category` / `topic` | Filtro fino e ranqueamento (um match no topic pesa mais que no corpo) |
| `priority` | Desempate de ranqueamento: `high` sobe, `low` desce |
| `status` | **Só `approved` e `active` entram no índice.** O resto é invisível pro agente |
| `source` | Confiança em conflito (ver política abaixo) |
| `last_updated` | Recência em conflito; documentos velhos podem aparecer no painel de desatualizados |
| `tags` | Busca e navegação no Obsidian |
| `aliases` | **Importante**: o conteúdo é em português, mas leads escrevem em inglês/espanhol. Os aliases entram no índice de busca e fazem a ponte entre idiomas. Todo documento que um lead possa "perguntar" deve ter aliases em EN |

## Ciclo de vida do conhecimento (status)

```
candidate → review_required → approved → active
                                  ↓
                              archived
```

- `candidate` — proposto pelo sistema (learning loop) ou rascunho humano.
  **Não indexado.**
- `review_required` — sinalizado para decisão do Italo/Eduardo. **Não
  indexado.**
- `approved` — revisado e aprovado por humano. **Indexado.**
- `active` — aprovado E confirmado em uso real. **Indexado.** (na prática,
  `approved` e `active` são equivalentes para o agente)
- `archived` — fora de uso. **Não indexado.** Mover para `99_ARCHIVE/` se
  quiser tirar da navegação também.

**O agente nunca muda um status.** Só o extrator de aprendizados grava — e
só com `candidate`. Promover é sempre gesto humano, no Obsidian.

## Política de conflito (quando dois documentos discordam)

O retrieval ordena por: (1) `status` active/approved primeiro → (2)
`priority` maior → (3) `last_updated` mais recente → (4) relevância da
busca. Se ainda assim a resposta ficar ambígua, a regra do agente é a de
sempre: **não inventa** — diz que vai confirmar e escala.

## A regra de ouro herdada do projeto

**Nenhum dado volátil de negócio em prosa retrievável**: preço em número,
link de página, horário de sessão, disponibilidade. Isso vive em
`salesagent/config/*.json` e chega ao Chase por diretiva (`[[price]]`),
imposto pela ponte (portões G1/G8). O Brain guarda posicionamento,
processo, objeções, políticas — o **porquê** e o **como**, nunca o número.
Um documento do Brain que precise citar preço aponta para a fonte:
"o valor vigente está no rate card".

## Como adicionar conhecimento (humano)

1. Criar o `.md` na pasta certa com o frontmatter completo (copiar de um
   vizinho).
2. `status: approved` se você é a autoridade do assunto; `review_required`
   se precisa de outra pessoa.
3. Aliases em inglês se um lead pode perguntar sobre isso.
4. Commit + push (ou botão de sync do plugin Obsidian Git).
5. No servidor, o índice se atualiza no próximo deploy ou ciclo diário —
   ou na hora com `python3 brain/indexer.py`.
