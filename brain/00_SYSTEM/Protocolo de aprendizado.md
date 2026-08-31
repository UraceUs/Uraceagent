---
tipo: sistema
tipo_info: PROCESS
fonte: Italo Silveira
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Protocolo de aprendizado

[[URACE]] · [[Tipos de informação]] · [[Conflitos e lacunas]] ·
[[Escalonamento]]

> O que a IA faz **toda vez** que chega informação nova — de uma
> conversa, de uma sonda num sistema, de um e-mail. O cérebro só serve
> se crescer sem se contradizer e sem perder o que já sabia.

## Os 8 passos

**1. Procurar antes de criar.**
Existe nota sobre isso? Buscar por **nome, apelido e chave externa**
(`asana_gid`, id do [[QuickBooks]], `envelopeId`). Antes de criar
"Cliente X", conferir se já existe `[[Cliente X]]` — e lembrar que
**a conta está no nome do responsável, não do piloto** ([[Clientes]]).

**2. Classificar.** Que `tipo_info` é isso? Ver [[Tipos de informação]].
Na dúvida entre `CONTEXT` e `RULE`, é **`CONTEXT`**.

**3. Comparar com o que já existe.** Três resultados possíveis:

| Resultado | Ação |
|---|---|
| **Confirma** o que já sabíamos | atualizar `data`, reforçar a fonte |
| **Acrescenta** | editar a nota existente, não criar uma segunda |
| **Contradiz** | ⚠️ **não escolher lado** — ver passo 6 |

**4. Atualizar ou criar.** Editar a nota que já existe é melhor que
criar outra. Nota nova só quando o assunto é realmente novo — duas notas
sobre a mesma coisa é o começo da contradição.

**5. Ligar.** Toda nota nova sai com **pelo menos um `[[wikilink]]`**
para o hub da área ou para a nota relacionada. É o link no meio do texto
que desenha o grafo — nota sem link é ilha, e ilha não é conhecimento.

**6. Contradição → registrar, não resolver.**
Se a informação nova contradiz a antiga: **as duas ficam**, marcadas
`status: needs_human_confirmation`, e o caso vai para
[[Conflitos e lacunas]] com as duas versões e suas fontes.
A IA **não escolhe** — quem escolhe é humano.

**7. Datar e creditar.** `fonte`, `data` e `responsavel`, sempre. Fato
sem fonte não entra: entra como `UNKNOWN`, ou não entra.

**8. Nunca apagar em silêncio.** Informação importante que deixou de
valer vira `status: superado` **e fica**, com um link para o que a
substituiu. Deletar é permitido só para erro de digitação e duplicata
óbvia — e mesmo assim, dito no diário.

## Onde o registro fica

Toda rodada de aprendizado deixa **duas marcas**:

1. a nota do conhecimento em si, na pasta certa;
2. uma linha no **diário do dia** (`30_DIARIO`) dizendo o que mudou e
   por quê.

Se a informação veio de um humano decidindo algo, também nasce uma nota
em **`08_DECISOES`**.

"Por que a IA sabe disso?" e "quando ela aprendeu?" têm que ter resposta.

## O que NUNCA entra

- **Credencial, senha, token, chave** — em nota nenhuma.
- **Inferência apresentada como fato.** Se foi dedução, o texto diz que
  foi dedução, e o tipo é `CONTEXT`, não `FACT`.
- **Número que muda** (preço, prazo, valor) fora de [[PARAMETROS]] e
  [[Rate Card]]. As outras notas apontam, não repetem.
