---
tipo: decisao
data: 2026-09-16
fonte: dono (cinco pedidos com as telas na mão)
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-16 — Piloto não é serviço; documento interno tem aba; a IA age dentro da tarefa

[[Asana]] · [[DocuSign]] · [[Triagem de e-mail]] · [[D-2026-09-04 - O que e cliente, ativo, e um card por pessoa]]

Cinco pedidos do dono no mesmo dia, olhando as telas do painel. Cada um virou regra.

## 1. O nome do piloto não é o nome do serviço

> *"A IA não identificar o nome do piloto com o nome do serviço; saber diferenciar. E
> em algumas ocasiões contextuais identificar o `_` ou `-` como um espaçador."*

O que ele viu: na aba do DocuSign, o signatário Matthew Hubbard ligado ao "piloto"
**`Elliott Hubbard_Summer Camp 2026 1/4`**, e William Fatutta ao
**`Mike Fattuta_Professional Coach Rotax`**. O card do cliente tinha o título da tarefa
inteiro como nome de gente.

A causa era uma linha: `_nome_valido()` **validava** o texto (achava uma pessoa nele)
mas **devolvia o texto inteiro**. E `pessoa_do_titulo()` rejeitava "Mike
Fattuta_Professional Coach Rotax" porque procurava palavra de corrida (*rotax*) no
título todo, não na parte da pessoa.

A regra, agora em código e na skill do Asana:

- o que vem **antes do primeiro separador** é a pessoa; o resto é serviço;
- separadores: `_`, `|`, hífen **com** espaço;
- hífen **colado** é contextual: separa só quando o que vem depois é serviço ou tem
  número (`Elliott Hubbard-Summer Camp 2026` → Elliott Hubbard); `Jean-Luc Picard` e
  `Ana-Maria Souza` continuam sendo um nome só;
- `[n/t]` no fim, ou `1/4` solto, é a contagem da sessão.

E uma régua nos cards já espelhados: `limpar_nomes_de_servico()` roda em toda sincronia
e deixa só a pessoa. Nada apagado, nada inventado — o serviço continua na tarefa.

## 2. Documento interno não é waiver de cliente

> *"Adicionar campo de busca nas waivers, uma aba separada para documentos internos que
> tenham como o e-mail `support@urace.us`."*

Carta de emprego, invite letter, contrato de marketing — tudo passa pelo DocuSign, e o
`support@` é signatário. Isso aparecia misturado aos envelopes de waiver, como "não
vinculado", e contava como "waiver em aberto" no Dashboard.

Regra: envelope em que o **`support@urace.us` é um dos signatários** é **documento
interno**. Vai para a aba *Internos*, com o assunto do envelope como nome; nunca é
ligado a cliente (a não ser à mão); não entra em "waivers em aberto", não vira aviso de
atenção. O espelho guarda `subject` e `internal`. E a busca vale em todas as abas:
signatário, e-mail, piloto, responsável, menor, assunto.

## 3. A IA dentro de cada tarefa

> *"Adicionar instruir a IA dentro de cada tarefa do Asana, para ela tomar ações
> dentro e para aquela tarefa."*

O modal da tarefa ganhou a caixa **✦ IA nesta tarefa**. O que vai para a IA é o que o
modal mostra: gid, título, coluna, data, cliente, piloto, subtarefas (com gid e
estado), descrição, e o contexto do cliente. A instrução manda a IA agir **nessa tarefa
e só nela** — comentar, concluir subtarefa, anexar, mover — sempre com aquele gid, e
diz que criar outra tarefa não é por esse caminho. A resposta abre no AI Command como
qualquer comando; as travas do MCP (Matt tasks, ADM URACE) seguem valendo.

## 4 e 5. O quadro abre só com o que falta, mais recente no topo

> *"Visualização de quadro do Asana mostrar somente as que ainda não foram concluídas.
> Mostrar em ordem as que ainda não foram completadas e mais recentes."*

O quadro abria em "Abertas e concluídas", em ordem de data crescente — coluna cheia de
serviço riscado de 2023 e o de hoje lá embaixo. Agora abre em **Só abertas**; o
seletor continua lá para quem quiser o histórico. A ordem, no quadro e na lista: **o que
não foi concluído primeiro; dentro de cada grupo, a data mais recente no topo; sem data
vai para o fim.** O calendário não muda.
