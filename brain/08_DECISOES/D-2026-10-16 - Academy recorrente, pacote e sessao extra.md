---
tipo: decisao
data: 2026-10-16
area: AGENDA
fonte: dono (áudio de 16/10)
issue: "#314"
status: ativo
complementa: "D-2026-08-31 - Sessao extra e mensal do Academy"
---

# Academy recorrente: pacote do mês, sessão extra e vários dias num pedido

**Dono, 16/10:** *"Quando for agendamento direto pelo site de cliente novo, que não for do Kart School, ele
vai pagar pelo Stripe. Quando for cliente do Kart School, que são os nossos clientes prós … esses clientes
pagam pelo QuickBooks. O invoice deles é recorrente. … Academy e Kart School é a mesma coisa. Salva isso na
memória, alimenta o cérebro com tudo isso. Mas sempre que for um cliente desse, que é recorrente, que é
mensal, quando ele for para a área do cliente para ele poder agendar a sessão dele, ele não precisa efetuar
o pagamento, a não ser que as sessões daquele pacote dele, seja um pacote com duas sessões, um pacote com
quatro sessões, se estiver paga, ele não precisa pagar por aquela sessão. Se ele já tiver usado as sessões
daquele pacote dele mensal, aí ele paga uma sessão adicional. Aí a sessão é dividida pelo valor do mensal
dele … ou então usa aqueles valores que eu te passei. Mas normalmente é o valor do mensal dividido para duas
ou quatro sessões … E aí, para esses clientes, é interessante eles terem a oportunidade de marcar mais de um
dia, multi-seleção de dias. Então, se ele quiser marcar para quartas, toda quarta. Ou quartas e sábado dessa
semana, ou então sábado e domingo da outra, ele consegue marcar isso tudo em um book."*

Liga com: [[D-2026-08-31 - Sessao extra e mensal do Academy]] · [[Urace Academy]] · [[Rate Card]]

## O que vale agora

- **Academy = Kart School.** Cliente da Academy com plano mensal é o **aluno recorrente**: paga a mensalidade
  pela invoice recorrente do QuickBooks e marca as sessões na área do cliente.
- **Cliente novo** (não recorrente) que marca pelo site paga no **Stripe** (carrinho) quando o Stripe está
  ligado; com o Stripe desligado, a invoice do QuickBooks continua como antes.
- **Sessão do pacote** (dentro das sessões do mês do plano, 2 ou 4): **não paga** nada na hora de marcar.
- **Sessão extra** (o pacote do mês já foi usado): paga uma sessão adicional, **pelo QuickBooks, nunca pelo
  Stripe**. O aluno recorrente que tenta pôr a sessão no carrinho recebe o aviso para marcar na área dele.
- **Preço da extra**, nesta ordem: o valor configurado no card → o valor do plano → o **mensal do card ÷
  sessões do mês**, em centavos com arredondamento comercial (2.756,90 ÷ 4 = 689,23; 1.378,45 ÷ 2 = 689,23).
  É a mesma regra de [[D-2026-08-31 - Sessao extra e mensal do Academy]]: o pacote sai do mensal.
- **Item do QuickBooks da extra:** já existe, "Academy | Extra session (beyond monthly 4)" (id 892). Vale o
  do card, depois o do plano, depois esse item, achado pelo nome.
- **Vários dias num pedido:** o aluno recorrente escolhe vários dias de uma vez (multi-seleção), com atalhos
  ("toda quarta": o resto deste mês, as próximas 4 semanas ou até uma data, sempre dentro do horizonte da
  agenda; "este fim de semana"; "o próximo fim de semana"). No máximo 12 dias por pedido. Ou entra tudo,
  ou nada. As extras de um mesmo pedido saem **numa invoice só** do QuickBooks.

## As regras que o Claude escolheu (o dono não respondeu ainda)

1. O cliente vê só **"Included in your plan"** ou **"Extra session · $X"** em cada dia; o contador
   (usadas/total) **não** vai para o cliente (como o dono pediu em 01/10).
2. A sessão extra **não leva depósito**: é só o valor da extra.
3. Plano comprado no site só libera as sessões sem custo **depois que a 1ª mensalidade é paga**.
4. Cliente não recorrente na área do cliente paga no Stripe (carrinho) quando o Stripe está ligado; com o
   Stripe desligado, a invoice continua como hoje.
5. As extras de um mesmo pedido saem numa invoice só do QuickBooks.
6. "Toda quarta" oferece o resto deste mês, as próximas 4 semanas ou até uma data, dentro do horizonte da
   agenda; no máximo 12 dias por pedido.
7. O pacote é **por mês** (zera no dia 1), também nos contratos de 6 e 12 meses, como já era.
8. **Pro Racing Driver sem mensal no card não conta como recorrente.**
9. A sessão do pacote cancelada **devolve a vaga do mês** (segue as regras de cancelamento que já existem); a
   invoice de uma extra cancelada vira aviso em **Precisa de atenção** para a equipe anular no QuickBooks. A
   extra do mesmo mês **ainda não cobrada** ocupa a vaga devolvida: na hora de cobrar, vira do plano e não sai
   invoice (o cliente só paga a extra quando já usou as do pacote).

Consequências dessas regras no sistema:
- O dia de um mês que o plano **não cobre** (a recorrência acaba antes) é **sessão avulsa**: o aluno marca pelo
  botão "Book as a regular session" e paga como qualquer cliente (Stripe com ele ligado, senão invoice).
- O aluno marca **com a cotação que viu**: se a última vaga do mês foi ocupada entre ver e clicar, a sessão não
  entra e a tela mostra o rótulo novo antes de ele marcar de novo (nada de extra cobrada sem aviso).
- A extra que nasceu **sem valor** (card sem mensal) é cobrada com o valor que a equipe puser depois no card.
- A invoice única das extras de um pedido conta **uma vez** na receita do painel do Site.

## A confirmar com o dono

- **(a)** Os itens do QuickBooks "Karting School" estão a **US$ 2.656,90** (4T e Mini/Micro 2T) e **US$ 3.056,90**
  (Jr/Sr 2T), diferente dos **US$ 2.756,90** e **3.156,90** de [[D-2026-08-31 - Sessao extra e mensal do Academy]].
  Qual vale? (O sistema usa o mensal **do card** de cada aluno, então a conta da extra segue o que estiver lá.)
- **(b)** O site diz *"Additional sessions $689"*; o cérebro diz **US$ 689,23**. Qual texto fica no site?
- **(c)** O padrão das regras 1 a 9 acima foi escolhido pelo Claude porque o dono não respondeu. Se alguma não
  for assim, muda no painel ou no código e esta nota é atualizada.

## Onde está no sistema

- Regra: `command_center/providers/contrato.py` (`vigente`, `usadas_do_pacote`, `preco_extra`, `item_extra`,
  `alocar`); cobrança: `providers/cobranca_agenda.py`.
- Painel: card do cliente › Mensalidade ("Valor da sessão extra", "Item da sessão extra"); Site › Serviços e
  preços (o plano); Site › Agendamentos (chip "do plano" / "extra $X").
- Playbooks: `docs/playbooks/playbook-vendas.md` (seção 5, "Aluno recorrente") e `playbook-geral.md`.

## Quem decidiu

O dono, em 16/10 (o pedido e as regras de preço). As regras 1 a 9 são o padrão do Claude até o dono responder.
