---
name: urace-obsidian
description: Contrato de escrita no segundo cérebro da URACE (vault Obsidian em brain/). Use sempre que qualquer skill precisar registrar entidade, fato ou decisão — cliente, corrida, serviço, pedido, invoice ou o diário do dia. Define o schema, as chaves externas de dedupe e o que nunca pode ser sobrescrito.
---

# Segundo cérebro da URACE — contrato de escrita

Toda skill escreve aqui. É isto que transforma ação isolada em memória.

## Onde mora o quê

```
brain/
  20_ENTIDADES/
    clientes/<slug>.md        # pessoa/empresa que paga
    corridas/<serie>-<round>.md
    servicos/<AAAA-MM-DD>-<piloto>.md
    pedidos/<numero-do-pedido>.md
  30_DIARIO/<AAAA-MM-DD>.md   # o que a IA fez naquele dia
  09_LEARNINGS/               # conhecimento candidato (revisão humana)
```

## Regra de ouro: espelho não se edita à mão

Nota com `fonte:` diferente de `humano` é **espelho** de um sistema
externo. A verdade está lá fora; a nota é cópia. Nunca editar um espelho
manualmente — corrigir na fonte e re-espelhar.

## Frontmatter obrigatório

```yaml
tipo: cliente | corrida | servico | pedido | invoice
fonte: asana | gmail | quickbooks | calendar | humano
atualizado_em: AAAA-MM-DD
# pelo menos UMA chave externa — é ela que faz o dedupe:
asana_gid: "1216270696569279"
gmail_thread_id: "19ff82b21db3f29b"
qb_customer_id: "44"
numero_pedido: "111-0438885-4250631"
```

**Nunca casar entidade por nome.** "Charlie Marron" e "Charles Andrew
Marron" são a mesma pessoa; "Fabio Delgado" aparece duas vezes com
pedidos diferentes. Nome é rótulo, chave externa é identidade.

## Ligações entre entidades

Use links do Obsidian, não texto solto:
`CLIENTE ← SERVIÇO → CORRIDA` · `CLIENTE → PEDIDO` · `CORRIDA → INVOICE`

```yaml
cliente: "[[clientes/mathias-brouta]]"
corrida: "[[corridas/amr-2026-round-8]]"
```

## O diário (`30_DIARIO/`)

Uma linha por ação com efeito no mundo: o que mudou, onde, por quê e com
que fonte. É o que responde "por que a IA fez isso?" sem depender de log
externo.

```markdown
## 2026-08-28
- [asana] Tyron Brouta 1/3 (gid 1215343715233730): e-mail do responsável
  corrigido para mbrouta@hotmail.fr. Fonte: QuickBooks, invoice
  4YZRN1QWN528NQM ($2.369,93, valor exato da tarefa). Autorizado 28/08.
- [asana] 100 tarefas concluídas movidas das colunas dos dias para
  Finished Services. Conferido por leitura direta.
```

## Nunca sobrescrever

- Fato **confirmado por humano** não é sobrescrito por dedução da IA.
- Conflito entre fontes → **não escolher em silêncio**: registrar as duas
  versões e escalar.
- Dado sensível de cliente (menor de idade, telefone, e-mail do
  responsável) só entra se já estiver na fonte. A IA não enriquece com
  dado de fora sem autorização.

## A forma do grafo — obrigatória em toda nota nova

O dono definiu a forma que o cérebro tem que manter enquanto cresce:
**muitos hubs, cada um com satélites atômicos, e os hubs ligados entre
si.** Regras completas em `brain/00_SYSTEM/Como o cérebro cresce.md`.

O que isso exige de cada nota que você criar:

1. **Uma nota, uma coisa.** Título com "e" quase sempre são duas notas.
2. **Pelo menos 2 links de saída**: um para o hub da área, e pelo menos
   um **lateral**, para outra área. Só o hub faz estrela isolada.
3. **Acima de ~1.800 palavras**, dividir (diário é exceção).
4. **Nunca deixar órfã** — se ninguém linka, não existe para a IA.
5. **Hub é índice, não depósito.** Conteúdo mora no satélite.

Antes de publicar uma leva de notas:

```
python3 adminai/brain_health.py --strict
```

Devolve erro se houver link quebrado, nome duplicado, órfã, nota pouco
ligada ou nota grande demais.
