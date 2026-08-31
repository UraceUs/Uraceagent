---
tipo: sistema
tipo_info: RULE
fonte: Italo Silveira
data: 2026-08-31
responsavel: Italo Silveira
status: ativo
---

# Escalonamento — quando a IA para e chama humano

[[URACE]] · [[Tipos de informação]] · [[Conflitos e lacunas]] ·
[[Stand-by e escalação]]

> **A regra que manda: se não souber, NÃO INVENTA.**
> Marca `UNKNOWN`, registra em [[Conflitos e lacunas]] e manda para um
> humano. Preencher lacuna com um padrão plausível é pior que perguntar,
> porque vira regra de fato na próxima vez.

## Para quem

| Humano | Assunto |
|---|---|
| **[[Italo Silveira]]** (`urace@urace.us`) | preço, regra de negócio, autorização de envio, qualquer decisão nova |
| **[[Eduardo Resende]]** | logística, compra e envio, [[Compra e envio\|Shipping Orders]] |

Na dúvida de quem, é o Italo.

## Quando escalar — a lista fechada

1. **`UNKNOWN`** — a informação não está no cérebro e não dá para
   descobrir na fonte.
2. **Conflito** entre duas fontes — registra as duas, **não escolhe**.
3. **Dado de cliente que não bate** — nome, e-mail, valor.
4. **Valor fora do padrão** — muito acima ou abaixo do histórico.
5. **Ação irreversível** sem autorização explícita: enviar, apagar,
   anular, regenerar credencial.
6. **Exceção ao processo** — o caso não se encaixa no que está escrito.
7. **Prazo apertado** com pendência que a IA não resolve sozinha.

## Quando **não** escalar

O dono foi explícito: **a IA não tira dúvida sobre tudo.** Ela tem que
entender. Não escalar quando:

- a resposta está no cérebro (então **leia**);
- dá para descobrir na fonte ([[Asana]], [[QuickBooks]], [[Gmail]],
  [[DocuSign]], [[Rate Card]]) — **esgotar as fontes primeiro**;
- é escolha pequena e reversível dentro do processo;
- já foi perguntado e está em stand-by — **não repetir a pergunta**.

Pergunta vaga ou óbvia queima a confiança do canal.

## O formato

```
PROBLEMA      o que está travado, em uma linha
CONTEXTO      cliente, tarefa, data, valor — com link
INFORMAÇÕES   o que eu já sei e de onde veio
O QUE FOI TENTADO   as fontes que consultei e o que cada uma deu
RECOMENDAÇÃO  o que eu faria, e o que preciso que você confirme
```

Português, direto, sem enfeite. O dono corrige em uma frase; texto longo
atrapalha.

## Perguntar não trava nada

Regra do dono (28/08): **a resposta não vem na hora.** Então a IA:

1. registra a pergunta (comentário na tarefa + [[Conflitos e lacunas]]);
2. põe **aquele item** em stand-by;
3. **segue com o resto do trabalho**;
4. **não repete** a pergunta;
5. **volta a alertar quando o prazo chega** — esta é a única exceção à
   regra de não repetir.

## Quando a resposta chegar

Segue o [[Protocolo de aprendizado]]: classifica o tipo, registra a
fonte e a data, liga com o que já existe, atualiza o que ficou velho,
tira o item de [[Conflitos e lacunas]] — e, se foi uma decisão, cria a
nota em `08_DECISOES`.

**Resposta de humano é conhecimento novo.** Se não for gravada, a
próxima pergunta vai ser a mesma.
