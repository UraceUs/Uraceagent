# Obsidian — guia para Italo e Eduardo (o cérebro do Chase na prática)

> Objetivo: em 15 minutos, você abre o vault, entende o que o Chase sabe,
> e sabe aprovar ou corrigir conhecimento. Sem terminal, sem código.

## 1. Instalar e abrir (uma vez só — o vault já vem pré-configurado)

O repositório já carrega a configuração do Obsidian (`.obsidian/`):
marcadores prontos na barra lateral, plugin de Git embutido (oficial,
"Git" v2.39.0) e sincronização automática ao abrir. Seus únicos passos:

1. Baixe o Obsidian em [obsidian.md](https://obsidian.md) (grátis).
2. Tenha o repositório no computador. Se ainda não tem: instale o
   [GitHub Desktop](https://desktop.github.com), faça login com a conta
   UraceUs e clone `UraceUs/Uraceagent` (botão "Clone").
3. No Obsidian: **Open folder as vault** → a pasta `Uraceagent` inteira.
4. Na primeira abertura, o Obsidian pergunta sobre plugins da comunidade:
   clique em **"Trust author and enable plugins"** (é o plugin de Git que
   já vem no vault — é ele que puxa e publica o conhecimento).

Pronto. Na barra lateral, em **Bookmarks**, já estão: ⭐ Painel do Brain
(sua página inicial), Como o Brain funciona, e este guia.

## 2. O dia a dia (5 minutos por dia)

1. **Sincronizar**: automático — ao abrir o Obsidian, o plugin de Git puxa
   as novidades sozinho (candidatos que o sistema gerou de noite chegam
   assim). Para puxar de novo no meio do dia: `Ctrl/Cmd+P` → "Git: Pull".
2. Abra o **⭐ Painel do Brain** → seção "Aguardando revisão".
3. Para cada candidato em `brain/09_LEARNINGS/` com `status: candidate`:
   - Leia. Edite o texto como quiser (é seu conhecimento, não do sistema).
   - **Aprovar** → mude a linha `status: candidate` para `status: approved`.
     A partir do próximo ciclo, o Chase usa.
   - **Descartar** → mude para `status: archived`.
   - **Na dúvida** → `status: review_required` (fica visível como pendência,
     invisível pro agente).
4. **Publicar**: `Ctrl/Cmd+P` → **"Git: Commit-and-sync"** — commita e
   publica num gesto (a mensagem de commit já vem pronta). O GitHub
   Desktop continua funcionando como alternativa, se preferir.

## 3. Adicionar conhecimento novo

1. Duplique um documento parecido da pasta certa (ex.: uma objeção nova →
   duplicar algo em `brain/02_SALES/`).
2. Edite o conteúdo **em português**.
3. No topo (o bloco entre `---`), ajuste: `topic`, `last_updated` (data de
   hoje), `status: approved` (se você é a autoridade do assunto) e
   `aliases:` com 3–6 palavras-chave **em inglês** que um lead usaria para
   perguntar aquilo (é o que faz a busca funcionar em qualquer idioma).
4. Commit + push.

Regra de ouro: **nunca escreva preço em número, link ou horário** dentro
do Brain — isso vive nas configurações (`salesagent/config/`) e chega ao
Chase por um canal com trava. No Brain vai o "porquê" e o "como", nunca o
número. Detalhes: `brain/_meta/README.md`.

## 4. O que muda o comportamento vs. o que muda o conhecimento

- **Conhecimento** (o que o Chase sabe) → edite o `brain/` como acima.
- **Comportamento** (como o Chase fala, o fluxo A/B/C/D, escalação) →
  `salesagent/instructions/urace-sales-agent.md` — e este exige um passo
  técnico no servidor depois do push (`sync_agent_instructions.sh` +
  restart). Se não estiver confortável, pede pro Claude fazer.

## 5. Perguntas rápidas

**Editei e o Chase ainda não sabe.** O índice atualiza no deploy ou no
ciclo diário (6h de Orlando). Para forçar na hora, no servidor:
`python3 brain/indexer.py`.

**Como sei o que o Chase anda buscando?** No servidor:
`python3 salesagent/tools/show_recent_audit.py --kind brain -n 20` — mostra
cada busca, o que voltou e em quanto tempo. Buscas "sem hits" viram
candidatos automáticos no dia seguinte (buraco de conhecimento apontado
por lead real).

**Posso apagar um documento?** Prefira `status: archived` (mantém o
histórico). Apagar também funciona — o índice se poda sozinho.
