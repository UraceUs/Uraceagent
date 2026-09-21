# Auditoria do cérebro + plano de arquitetura

Pedido do dono em 31/08/2026: transformar o Obsidian num **Cérebro
Central** consultável e atualizável por IA. Ele pediu **auditoria e plano
antes de qualquer alteração**. Este documento é a auditoria e o plano.
Nada foi movido nem reescrito com base nele até aprovação.

---

# PARTE 1 — AUDITORIA

## 1.1 O que já existe no vault

**82 notas · 582 links · 0 links quebrados · 0 notas órfãs ·
~20.700 palavras.** O grafo está saudável (foi arrumado hoje).

| Pasta | Notas | Estado |
|---|---|---|
| `00_SYSTEM` | 1 | só `PARAMETROS` — **é o ponto único de alteração e funciona** |
| `10_PROCESSOS` | 8 | processos ditados pelo dono, bem escritos |
| `20_ENTIDADES` | 50 | clientes (14), corridas (5), equipe (5), fornecedores (7), serviços (6), locais (4) + hubs |
| `30_DIARIO` | 2 | 28/08 e 31/08 |
| `40_SISTEMAS` | 6 | Asana, Gmail, QuickBooks, Rate Card, DocuSign, Calendar |
| `90_ARQUIVO` | 12 | era Chase (vendas), corretamente isolada |
| `_dashboards` · `_meta` | 2 | painel e guia |

Notas mais conectadas: QuickBooks (69 links de entrada), Asana (42),
DocuSign (38), PARAMETROS (36). **O centro do grafo está no lugar certo.**

## 1.2 Conhecimento que existe no ambiente e NÃO está no vault

Esta é a maior descoberta da auditoria.

### a) `docs/adminai/` — ~1.100 linhas nunca migradas

| Documento | O que guarda | Já está no vault? |
|---|---|---|
| `operacao-u-race.md` | **regras ditadas pelo dono** sobre colunas, RACES, as 12 subtarefas uma a uma, dados sensíveis, autonomia concedida | **parcial** — só o que virou processo |
| `app-gmail-triagem.md` | **taxonomia real da caixa** (wNews 1.943 · Banks 1.784 · Suits 432 · Travels 1.897 · etc.) e a rotina diária | **parcial** |
| `mapa-asana-4-projetos.md` | GIDs, seções, campos, modelos e **8 inconsistências documentadas** | **duplicado** com `40_SISTEMAS/Asana` |
| `automacao-status-secao.md` | mapa status↔seção, empate pela última alteração, **o gotcha do atraso da busca** | **parcial** |
| `diagnostico-servicos-agosto-2026.md` | **7 problemas reais achados** nos serviços de agosto | ❌ **não está** |
| `descobertas-fase2.md` | sondas da fase 2 | ❌ não está |
| `estado-corridas-2026-08-28.md` | espelho das corridas | parcial |
| `ajustes-asana-2026-08-28.md` | o que foi executado no Asana | ❌ não está |
| `roadmap-plataformas.md` | estado das 4 plataformas | ⚠️ **desatualizado** (ver 1.4) |
| `app-asana-corridas.md` | desenho da aplicação 1 | parcial |
| `parametros-operacionais.md` | **stub apontando para PARAMETROS** | ✅ **é o padrão certo** |

### b) `salesagent/discovery/` — ~16.000 palavras extraídas de chats antigos

`voice-manual-italo.md` · `extracao-pop-comercial-v3.md` ·
`extracao-commercial-os-v4.md` · `extracao-george-qualification-logic.md`
· `extracao-handbook-comercial.md` · `extracao-modo-operante...` ·
`extracao-prompt-treinamento-real.md`

São da era Chase (vendas), **mas contêm fato de empresa** que sobrevive
ao pivot: como a URACE se posiciona, políticas comerciais, a voz do
Italo. Hoje esse material está fora do vault e invisível para a IA.

### c) Uploads

`Italo_AI_Voice_Training_Manual.md` (18 KB) — nunca entrou no vault.

### d) Histórico de conversa

**Uma** sessão de chat neste ambiente (51 MB). Não há outros projetos ou
chats acessíveis daqui — o conhecimento das conversas anteriores só
existe na forma já extraída em `docs/` e `salesagent/discovery/`.

## 1.3 Duplicações reais

| # | Onde | Diagnóstico |
|---|---|---|
| 1 | `docs/adminai/mapa-asana-4-projetos.md` × `40_SISTEMAS/Asana` | mesmo assunto, duas fontes |
| 2 | `docs/adminai/app-gmail-triagem.md` × `Triagem de e-mail` + `Gmail` | idem |
| 3 | `docs/adminai/automacao-status-secao.md` × `Compra e envio` | idem |
| 4 | `20_ENTIDADES/servicos/Karting School` × `Urace Academy` | **o dono disse que é o MESMO serviço renomeado** |

## 1.4 Informação desatualizada ou conflitante

| Assunto | Situação |
|---|---|
| `roadmap-plataformas.md` diz *"QuickBooks: regra de negócio VAZIA"* e *"DocuSign: praticamente vazio"* | **falso hoje** — os dois foram especificados em 31/08 |
| [[Rate Card]]: 4 células da planilha | conflito **registrado e resolvido** — valor válido está no cérebro, planilha espera clique |
| Waiver "vale por temporada" × "1 ano da assinatura" | **resolvido** em 31/08 |
| Texto do Adult Waiver | divergência **conhecida e decidida**: fica como está |

Os três últimos já seguem o padrão que o dono pediu — registrar em vez de
escolher. O primeiro precisa de correção.

## 1.5 O que ele pediu e HOJE NÃO EXISTE

1. **Tipagem semântica** `FACT / DECISION / RULE / PROCESS / PREFERENCE /
   CONTEXT / OPEN QUESTION / UNKNOWN` — hoje tudo é prosa sem tipo.
2. **Notas de decisão próprias** — decisões vivem soltas no diário e no
   histórico do PARAMETROS. Não dá para perguntar "o que foi decidido
   sobre X".
3. **Registro formal de conflito** com `Needs Human Confirmation`.
4. **Protocolo de aprendizado incremental** — o que a IA faz quando
   chega informação nova (comparar, atualizar, ligar, datar, nunca
   apagar em silêncio).
5. **`UNKNOWN` + escalonamento nomeado** a [[Italo Silveira]] /
   [[Eduardo Resende]]. Existe o processo de stand-by, falta a tipagem.
6. **Notas de projeto** — não existe a entidade PROJETO.
7. **Notas de problema** — os 7 problemas do diagnóstico de agosto não
   estão no vault.
8. **Frontmatter consistente** — hoje varia (`tipo:` sozinho em umas,
   schema antigo do Chase em outras).

---

# PARTE 2 — PLANO DE ARQUITETURA

## 2.1 A decisão de estrutura

O dono sugeriu 16 pastas numeradas (`00-INDEX` … `15-ARQUIVO`). O vault
atual tem 6 pastas com 582 links funcionando.

**Recomendação: convergir, não renumerar do zero.** Wikilink no Obsidian
é por nome, então mover arquivo não quebra link — o risco é zero. Mas
renumerar 82 notas só para trocar o rótulo da pasta gera revisão sem
ganho. O que **tem** ganho é criar as categorias que faltam.

Mapa proposto (o número do dono → o que já existe):

| Alvo do dono | Proposta | Situação |
|---|---|---|
| 00 - INDEX | `URACE.md` + `_dashboards` + índices por área | ✅ existe, **falta índice por área** |
| 01 - EMPRESA | **`01_EMPRESA`** | 🆕 **criar** (foi arquivado com o Chase) |
| 02 - PESSOAS | `20_ENTIDADES/equipe` | ✅ existe, **falta responsabilidade e relação** |
| 03 - CLIENTES | `20_ENTIDADES/clientes` | ✅ existe |
| 04 - PROJETOS | **`04_PROJETOS`** | 🆕 **criar** |
| 05 - OPERAÇÕES | dissolvido em processos + sistemas | manter dissolvido |
| 06 - PROCESSOS / 07 - SOPs | `10_PROCESSOS` | ✅ existe — **não separar SOP de processo**, é a mesma coisa aqui |
| 08 - DECISÕES | **`08_DECISOES`** | 🆕 **criar** |
| 09 - REUNIÕES | — | ❌ **não criar**: não há fonte de reunião no ambiente |
| 10 - FORNECEDORES | `20_ENTIDADES/fornecedores` | ✅ existe |
| 11 - FERRAMENTAS | `40_SISTEMAS` | ✅ existe |
| 12 - CONHECIMENTO | `20_ENTIDADES` + `40_SISTEMAS` | manter distribuído |
| 13 - PROBLEMAS | **`13_PROBLEMAS`** | 🆕 **criar** |
| 14 - OPORTUNIDADES | — | ⚠️ fonte fraca (só o brainstorming do ADM URACE) |
| 15 - ARQUIVO | `90_ARQUIVO` | ✅ existe |

**Pasta vazia não entra.** É regra já registrada no vault e evita que a
IA ache que existe conhecimento onde não há.

## 2.2 As 4 pastas novas

- **`01_EMPRESA`** — quem é a URACE, posicionamento, políticas
  comerciais, endereços, dados fiscais. Fonte: o material da era Chase
  (`Visao Geral URACE`, `Politicas Comerciais`) **reescrito e
  reconfirmado**, não copiado.
- **`04_PROJETOS`** — Administrative AI, e o Chase como projeto encerrado.
- **`08_DECISOES`** — uma nota por decisão, extraídas do diário, do
  histórico do PARAMETROS e desta sessão.
- **`13_PROBLEMAS`** — os 7 do diagnóstico de agosto, mais os achados de
  hoje (waivers paradas, A/R concentrado, células da Rate Card).

## 2.3 Tipagem — o coração do que ele pediu

Frontmatter passa a ter **`tipo_info`**, obrigatório em nota de
conhecimento:

```yaml
tipo_info: FACT | DECISION | RULE | PROCESS | PREFERENCE |
           CONTEXT | OPEN_QUESTION | UNKNOWN
fonte: quem/onde disse
data: AAAA-MM-DD
responsavel: Italo Silveira | Eduardo Resende
status: ativo | review_required | needs_human_confirmation | superado
```

É isso que impede o erro que ele nomeou: **contexto temporário virar
regra permanente**. Uma frase dita num dia entra como `CONTEXT`; só vira
`RULE` quando ele disser que é regra.

## 2.4 As três notas de sistema novas

1. **`00_SYSTEM/Protocolo de aprendizado.md`** — o que a IA faz quando
   chega informação nova: procurar o que já existe, comparar, atualizar
   ou criar, ligar, datar, registrar origem, **nunca apagar em silêncio**.
2. **`00_SYSTEM/Conflitos e lacunas.md`** — o registro vivo de
   divergências (`needs_human_confirmation`) e de `UNKNOWN`. É a lista
   que a IA consulta para saber o que ela **não** sabe.
3. **`00_SYSTEM/Escalonamento.md`** — quando parar e chamar humano, para
   quem ([[Italo Silveira]] ou [[Eduardo Resende]]), em que formato. Junta
   o que hoje está em `Stand-by e escalação` com a tipagem `UNKNOWN`.

## 2.5 Migração do conhecimento não migrado

Para cada documento de `docs/adminai/`: **extrair o conhecimento para
nota atômica no vault** e deixar no lugar do original um **stub
apontando para o vault** — exatamente o padrão que
`parametros-operacionais.md` já usa. Assim nada se perde e some a
duplicação.

O material de `salesagent/discovery/` e o manual de voz **não são
copiados**: o que for fato de empresa ainda válido vira nota em
`01_EMPRESA` com `status: review_required`, para o dono confirmar. O que
for de vendas fica no arquivo.

## 2.6 Ordem de execução

1. As 3 notas de sistema (protocolo, conflitos, escalonamento) — é o
   alicerce.
2. `08_DECISOES` + `13_PROBLEMAS` a partir do que já está registrado.
3. Migrar `docs/adminai/` com stubs.
4. `01_EMPRESA` e `04_PROJETOS`.
5. Tipagem retroativa nas notas existentes.
6. Índices por área + controle de qualidade (links, duplicatas, órfãs,
   nota crítica sem data).

## 2.7 O que eu NÃO vou fazer

- Não apagar nada. Migração é mover + deixar stub.
- Não inventar. Fato sem fonte entra como `UNKNOWN` ou não entra.
- Não escolher lado em conflito — registra os dois e marca
  `needs_human_confirmation`.
- Não criar pasta sem conteúdo real.
- Não guardar credencial, em lugar nenhum do vault.
