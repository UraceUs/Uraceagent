---
tipo: processo
area: transversal
fonte: humano
ditado_por: Italo Silveira
data: 2026-10-12
tipo_info: RULE
responsavel: Italo Silveira
status: ativo
---

# Processo — pedido com informação faltando

[[URACE]] · [[Stand-by e escalação]] · vale para todo pedido feito no AI Command

Dono, 12/10: *"vão jogar lá o nome da pessoa, informações faltando, e a IA precisa assimilar
que tem informações faltando, e ao invés de bloquear e não fazer a tarefa, ela coloca a tarefa
com as informações que tem, e o restante ela identifica informações de contato para entrar em
contato, ou então ela consegue avisar o usuário que foi criado, mas que precisa colocar as
demais informações, e vai dando rodada de aviso até o usuário completar"*.

## O que a IA faz

1. **Procura antes**: painel, [[QuickBooks]], [[Kommo]], [[Gmail]] e o cérebro. Muitas vezes o
   nome basta para achar o cliente, o e-mail e o telefone.
2. **Cria com o que tem**: tarefa, cliente, pedido, estimate. A lacuna fica visível no próprio
   registro ("horário: a confirmar"). **Nunca** preenche o buraco com valor inventado (NO FAKE DATA).
3. **Registra a pendência**: o que criou, onde está, o que falta e o contato que achou para pedir.
4. **Avisa quem pediu**: "Criei X. Falta: A, B. Contato para pedir: …".
5. **Recebeu o dado** (na conversa ou no card): completa o registro e fecha a pendência.

## As rodadas de aviso

- Às **09:00 e 16:00** (Flórida), quem pediu recebe um aviso no celular com o que ainda falta.
- A pendência fica em **Atenção** e no topo do **AI Command** ("Falta completar"), com o botão
  **Completei**.
- Cada comando novo da pessoa leva as pendências dela, e a IA lembra no fim da resposta.
- O que é campo do card do cliente (e-mail, telefone, nome ou nascimento do piloto) **fecha
  sozinho** quando alguém preenche o card.

O aviso vai para **a equipe** (quem pediu), nunca para o cliente: falar com o cliente para pedir
o dado continua passando pelo aprovar de sempre.

## Quando NÃO criar

Só quando criar com o que tem causaria dano: cobrar ou enviar algo ao cliente sem o valor ou o
destinatário certo, ou não dar para saber nem de quem é o pedido. Aí a IA pergunta numa lista
curta.
