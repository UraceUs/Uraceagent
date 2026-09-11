---
tipo: sistema
tipo_info: RULE
fonte: Italo Silveira
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Tipos de informação

[[URACE]] · [[Protocolo de aprendizado]] · [[Conflitos e lacunas]] ·
[[Escalonamento]]

> **O erro que esta nota existe para impedir:** uma frase dita de
> passagem virar regra permanente. Toda informação do cérebro tem um
> **tipo**, e o tipo decide o peso que ela tem.

## Os oito tipos

| `tipo_info` | O que é | Como a IA trata |
|---|---|---|
| **FACT** | fato verificável, lido da fonte | usa direto · **exige `fonte` e `data`** |
| **DECISION** | escolha feita por um humano | vale até ser revogada por outra decisão |
| **RULE** | regra permanente da operação | **manda** — só muda por decisão explícita |
| **PROCESS** | como um trabalho é feito, passo a passo | segue na ordem |
| **PREFERENCE** | gosto, tom, jeito de fazer | segue, mas **não trava** trabalho |
| **CONTEXT** | circunstância de um momento | **NUNCA vira regra** sozinha |
| **OPEN_QUESTION** | pergunta feita, sem resposta ainda | põe em stand-by, não deduz |
| **UNKNOWN** | a IA não sabe e não tem onde procurar | **escala** — ver [[Escalonamento]] |

## A regra de promoção

**CONTEXT não sobe sozinho.** Uma coisa dita num dia entra como
`CONTEXT`. Vira `RULE` **só quando um humano disser que é regra** — e
essa promoção é registrada como uma nota em `08_DECISOES`.

Isso vale ao contrário também: `RULE` só cai por outra `DECISION`. A IA
nunca revoga regra por conta própria.

## O frontmatter mínimo

Toda nota de conhecimento carrega:

```yaml
tipo_info: FACT | DECISION | RULE | PROCESS | PREFERENCE | CONTEXT | OPEN_QUESTION | UNKNOWN
fonte: quem disse, ou de onde foi lido
data: AAAA-MM-DD
responsavel: Italo Silveira | Eduardo Resende
status: ativo | review_required | needs_human_confirmation | superado
```

`status` explicado:

| status | Significa |
|---|---|
| `ativo` | vale hoje, pode usar |
| `review_required` | provavelmente desatualizado, **conferir antes de usar** |
| `needs_human_confirmation` | há **conflito** — ver [[Conflitos e lacunas]] |
| `superado` | foi substituído; fica pelo histórico, **não se usa** |

## Onde a tipagem é obrigatória

Decisão do dono (31/08): **notas novas nascem tipadas**, e a tipagem
retroativa vale para **processo, sistema e decisão** — onde confundir
contexto com regra causa dano real.

As ~50 fichas de entidade (cliente, corrida, fornecedor, local) **ficam
como estão**: são cadastro, não regra.

## Nunca guardar

**Credencial, senha, token ou chave não entram no cérebro** — em nota
nenhuma, de tipo nenhum. Ver [[Etapa de conexão]] para onde elas moram.
