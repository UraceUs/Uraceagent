# Playbook de vendas do Command Center — URACE

> **Para quem é:** quem vende na URACE (papel **Operador** no painel) e o Claude dessa pessoa,
> conectado ao painel pelo MCP. O mesmo texto serve aos dois: a pessoa lê, o Claude segue.
>
> **Antes deste, o geral:** conexão, papéis, mapa das telas, IA do painel e regras gerais estão em
> [`docs/playbooks/playbook-geral.md`](playbook-geral.md). Aqui só entra o que é de venda.
>
> **De onde saiu:** tudo foi conferido no código (`command_center/api/vendas.py`, `rotas.py`,
> `site_publico.py`, `crm.py`, `sdr.py`, `suits.py`, `mcp_operar.py`, `google.py`, `providers/cobranca_agenda.py`,
> `providers/venda_site.py`, `providers/google_agenda.py`) e nos processos do cérebro (`brain/10_PROCESSOS/`). Quando o código e
> um documento antigo discordam, vale o código, e a diferença está dita.
>
> Atualizado em 17/10/2026 (#313: o quadro de oportunidades, os agendamentos, os pedidos e as contas do site no cartão do
> padrão D). Antes, 14/10/2026 (#204: invoice fora da tabela só com o gerente, depósito na venda manual,
> card de irmão, retorno vencido em Precisa de atenção, confirmação do chat pelo Claude).
> Painel: https://ops.urace.us/ops/

---

## Sumário

1. Para quem é e como usar
2. O funil da URACE no Command Center
3. Achar ou criar o cliente certo
4. Oportunidade e venda: abrir, ligar, fechar, reenviar, o seu Google Calendar
5. Site › Agendamentos: carrinho, pagamento no Stripe e a loja do site (produtos, frete e depósito no painel; estoque do site, 5.3); Security deposit (5.4)
6. CRM (Kommo) e o Robô SDR
7. Suits (macacão)
8. Tabela de operações para a IA
9. Roteiros prontos
10. Regras que nunca mudam
11. Quando algo dá errado

---

## 1. Para quem é e como usar

### Se você é a pessoa que vende

- Leia as seções 2 a 6 uma vez. No dia a dia, use a **seção 9** (roteiros) e a **seção 11**
  (problemas).
- Você pode fazer tudo pelos botões do painel **ou** pedir ao seu Claude. As travas são as mesmas:
  o Claude chama as mesmas rotas que os botões, com o **seu** papel, e a auditoria grava o seu nome.
- Quem vende tem papel **Operador**. Não existe papel "vendas" (decisão do dono, 17/09). O que é de
  gerente ou administrador está marcado em cada tabela.

### Se você é o Claude de quem vende

Cole este arquivo nas instruções do Projeto (claude.ai) ou salve como `CLAUDE.md` na pasta onde o
Claude Code abre. Conexão: playbook geral, seção "Operar pelo Claude (MCP)". Resumo do que importa:

| Ferramenta | Para quê |
|---|---|
| `urace_operacoes` | listar o que **esta pessoa** pode fazer (filtre: `venda`, `agendamento`, `waiver`, `clients`) |
| `urace_api` | executar uma operação (método, caminho, `corpo`, `consulta`, `confirmar`) |
| `urace_clientes`, `urace_cliente` | ler clientes e a ficha de um cliente |
| `urace_kommo_leads`, `urace_kommo_lead`, `urace_kommo_conversa` | ler leads e conversas do Kommo |
| `urace_precos_cobrados` | quanto a URACE já cobrou de cada serviço ou peça (histórico do QuickBooks) |
| `urace_atencao` | o que precisa de gente hoje |

**Bloco de instrução (copie junto, se o Claude não ler o arquivo inteiro):**

```
Você opera o Command Center da URACE como a pessoa que vende (papel Operador).
1. Sempre busque antes de criar: cliente, oportunidade, lead.
2. Nunca invente dado: nome, e-mail, idade, preço, data. Faltou, pergunte.
3. O que vai para fora ou cobra volta primeiro com "precisa_confirmar". Mostre à pessoa
   exatamente o que vai sair (para quem, quanto, qual modelo) e só repita com
   confirmar=true depois de ela dizer "pode mandar".
4. Antes de fechar uma venda, leia GET /ops/api/sales/{id}: se "closing" não for null,
   ela já foi fechada. Não feche de novo: refaça só o passo que falhou.
5. Preço só da tabela (Rate Card ou Site › Serviços e preços). Não sabe? Pergunte.
6. Idade do piloto antes de qualquer waiver: menor de 18 = parental para o responsável.
7. Datas e horas no fuso da Flórida. Na API, mande em UTC com "Z".
8. Resposta ao lead no Kommo: só o texto que a pessoa aprovou, palavra por palavra.
9. Nunca peça senha, token ou PIN. Nunca use Turo nem Hostaway.
```

---

## 2. O funil da URACE no Command Center

### O caminho de uma venda

```
LEAD            Kommo (Instagram, Facebook, WhatsApp, chat do site) · telefone · indicação
  │             └ no painel: Chat do Kommo (/ops/crm/chat) · ligação perdida em Precisa de atenção
  ▼
OPORTUNIDADE    Comercial › Oportunidades (/ops/sales) — ainda NÃO é cliente
  │             Novo → Em conversa → Proposta → Fechamento
  │             cada ligação, retorno e anotação fica na linha do tempo dela
  ▼
FECHAR VENDA    um botão dispara: card do cliente · cliente e invoice no QuickBooks ·
  │             waiver no DocuSign · tarefa no Asana · Kommo em "Closed won"
  ▼
GANHO           a oportunidade vira card de cliente (/ops/clients/{id})
  ▼
PRONTO          invoice paga + waiver assinada → o serviço acontece
```

O cliente também pode marcar sozinho pelo site. Esse caminho é outro (seção 5):

```
PEDIDO NO SITE  área do cliente → Site › Agendamentos (/ops/site/agendamentos), "pendente"
  ▼
ACEITAR         invoice (serviço + depósito, se o serviço pede) e waiver saem sozinhas
  ▼
CONFIRMADA      sozinha, quando a invoice está paga e a waiver em dia
```

E o **carrinho do site** (#236, seção 5.1), que já chega pago:

```
CARRINHO        site novo: sessões da agenda + produtos da loja, com a conta do site e o piloto
  ▼
STRIPE          um checkout só (cartão, Apple Pay, Google Pay), com a linha do depósito de cada sessão
  ▼
PAGO            a sessão entra aceita e paga (falta só a waiver) e a venda entra GANHO em Vendas
```

**O ⓘ do depósito (#282, dono 15/10).** Na reserva, no carrinho e na página do pedido, ao lado do
security deposit, há um ⓘ: no celular abre com o toque, no computador com o mouse em cima. Ele diz:
*"Refundable within 5 business days after your session, as long as there is no damage to the kart. Damage above
the deposit amount may be charged additionally."* O mesmo texto vai no e-mail do pedido e na linha do
depósito no Stripe. Se o cliente perguntar, é isso que vale: devolução em até 5 dias **úteis** depois da sessão (#295, dono 16/10: "business days", como no contrato),
sem dano ao kart; dano acima do depósito é cobrado à parte.

### O que o sistema grava em cada passo

| Passo | Onde | O que fica gravado |
|---|---|---|
| Lead chega no Kommo | Chat do Kommo | conversa espelhada; quem espera resposta fica marcado com ● |
| "Passar para vendas" | botão no chat | oportunidade nova ligada ao lead (`crm_lead_id`), origem = canal |
| Nova oportunidade | Oportunidades › **Nova oportunidade** | ficha + evento "Oportunidade criada"; avisa se o e-mail já é de cliente |
| Ligação | **Registrar ligação** | resultado, minutos, o que foi dito, retorno; a etapa anda sozinha |
| Retorno | **Retorno** ou na ligação | aparece na **Agenda de vendas** (`/ops/sales/agenda`); atrasado em vermelho |
| Fechar venda | **Fechar venda** | cada passo com "feito", "aguardando" ou "falhou"; auditoria `sales.close` |
| Pagamento | QuickBooks → espelho do painel | o espelho sincroniza a cada 15 min |
| Waiver | DocuSign ou área do cliente | `sent` → `completed`. **`delivered` não é assinada** |
| Contato ou pedido pelo site | `/contact/` e a loja | oportunidade origem **Site** + a **campanha** de onde a pessoa veio (#260) |
| Chat do site | balão do Kommo nas páginas públicas (#170) | a conversa vira lead no Kommo, como no site antigo, e aparece no Chat do Kommo; responda por lá |

### As etapas e o que move cada uma

| Etapa | Como chega |
|---|---|
| Novo | ao criar |
| Em conversa | sozinha, na primeira ligação que não é "sem interesse" |
| Proposta | à mão (botão de etapa ou `POST /sales/{id}/stage`) |
| Fechamento | sozinha quando a ligação é "fechou" |
| **Ganho** | **só pelo Fechar venda** (o painel recusa mover à mão para Ganho) |
| **Perdido** | à mão, **com motivo obrigatório** |

No quadro, Ganho e Perdido mostram só os dos últimos 7 dias. **Só minhas / Todas** é filtro de
tela: todo operador vê todas as oportunidades.

**Como o quadro mostra cada oportunidade (#313):** um cartão do padrão D (o mesmo do painel inteiro; o playbook geral,
seção 3, explica). Em cima, a situação: **retorno marcado** (amarelo), **retorno atrasado** (vermelho), **virou
cliente** (verde), **Perdido** (vermelho) ou, sem retorno, a etapa. Depois as iniciais e o nome, a origem (com o ícone
do canal) e as ligações, o serviço e o dia; no **bloco grande, o valor**; embaixo, o retorno (dia, hora e o que fazer) e
o motivo da perda. **Clicar em qualquer lugar do cartão abre a oportunidade.**

---

## 3. Achar ou criar o cliente certo

### Regra de ouro: buscar antes de criar

1. Busque pelo **nome do responsável**, pelo **nome do piloto** e pelo **e-mail**:
   `GET /ops/api/clients?q=…` (ou a busca do topo, ⌘K). A busca procura em nome, piloto e e-mail.
   **Telefone não entra nessa busca**; para telefone, procure o lead no Kommo
   (`urace_kommo_leads` com `texto`).
2. Achou? Use o card que existe. Em todo formulário de inserção à mão, use
   **"Vincular ao cliente"** (dono, 08/10, #158): ele grava o `client_id` e puxa o que o card já tem.
3. Não achou? Crie com **Clientes › + Novo cliente** (`POST /ops/api/clients`). O painel confere
   e-mail, telefone e nome: se a pessoa já existe, **devolve o card dela** ("Esse cliente já
   existia") em vez de duplicar.

### Um card por piloto

- O card é do **piloto**. O **responsável** é quem paga e assina (pai, mãe ou o próprio piloto
  adulto). No QuickBooks o cliente é sempre o responsável, nunca o piloto.
- Irmãos têm o mesmo responsável, e-mail e telefone, mas **cada piloto tem o seu card** (#65).
- O **+ Novo cliente** reconhece "pessoa que já existe" por e-mail ou telefone: com o e-mail do
  irmão, ele devolve o card do irmão. Para o irmão, use o **card de irmão** (#204, dono, 14/10:
  *"sim, é para criar um card de um irmão"*):
  - **Clientes › + Novo cliente › "É irmão de um cliente? Criar card de irmão"**, ou no card do
    irmão: **⋯ › + Card de irmão**;
  - em **"Irmão de — vincular ao cliente"**, escolha o card do irmão que já existe. O responsável,
    o e-mail e o telefone vêm dele; você escreve o **piloto** (e o nascimento);
  - pela API: `POST /ops/api/clients` com `{"pilot_name": "…", "irmao_de": <id do card do irmão>}`.
  O card novo mostra **irmão(s)** no topo, com o link para o outro. Os dois **nunca se unem** (nem
  pela sincronia, nem pelo Unir) e o serviço de um não vai para o outro. Pedir de novo para o mesmo
  piloto devolve o card que já existe.
- Se a família tem conta no site, o card do irmão também pode nascer em **Site ›
  Contas de clientes**, pelo driver (seção 5). A conta no site para cada irmão fica para depois
  (dono, 14/10).
- **Sempre confira o piloto do card** antes de pôr um serviço nele.
- Mover um serviço de um card para outro é do **gerente** (`POST /tasks/{id}/cliente`).
- Unir dois cards (`POST /client-merge`, Operador) só quando são a mesma pessoa. O painel recusa
  unir cards de drivers diferentes do site ou de contas diferentes.

### Menor de idade, responsável e waiver

| Situação | O que vale (código) |
|---|---|
| Piloto **menor de 18** | waiver **parental**, assinada pelo responsável, no e-mail do responsável |
| Piloto **adulto** | waiver **adult**, assinada **pelo próprio piloto** |
| **Idade em branco** no Fechar venda | o painel manda o modelo **adulto** para o e-mail da ficha. Por isso: **preencha a idade sempre** |
| Adulto que não é o responsável | o Fechar venda manda a waiver para o e-mail e o nome da ficha (o responsável). Desligue o passo Waiver e mande a avulsa para o piloto (roteiro R4) |
| Nova tarefa de serviço (`POST /tasks`) | piloto menor **exige** responsável; sem nascimento, exige responsável |
| Pedido do site | a idade é calculada pela data de nascimento **no dia da sessão**; adulto sem e-mail próprio trava a waiver |
| E-mail `@urace.us` | recusado: não é e-mail de cliente |
| Já tem waiver válida | a waiver vale **1 ano** da assinatura. O DocuSign recusa se já houver uma válida ou um envelope em aberto para aquele e-mail. Isso não é erro: é a trava contra mandar duas vezes |
| Cliente VIP | dispensa waiver. A lista está em `brain/00_SYSTEM/PARAMETROS.md` e é a única fonte. A IA não deduz VIP |
| **Convite da waiver por e-mail** (#135) | do card do cliente, aba **Waivers**: vai para o **e-mail do card**. 18+ pela data de nascimento do piloto → o próprio piloto assina (adult); menor → o responsável (parental). A tela mostra nome e e-mail e pede confirmação. Link pessoal, uso único, 72 h, sem conta; código de 6 dígitos no mesmo e-mail na hora de assinar. Precisa da assinatura no próprio sistema ligada. Pela IA (`painel_waiver_convite`), só com aprovação |

---

## 4. Oportunidade e venda

### 4.1 Abrir a oportunidade

**No painel:** Oportunidades › **Nova oportunidade**. Durante a ligação, **só o nome é
obrigatório**; o resto entra depois. Todo campo aceita ditado.

| Campo | Observação |
|---|---|
| Já é cliente? Vincular ao cliente | escolha o card: puxa nome, telefone, e-mail e piloto, e o fechamento cai nesse card |
| Quem decide (responsável) | obrigatório |
| Telefone, E-mail | o e-mail é o destino da invoice e da waiver |
| Origem | Ligação, Instagram, Facebook, WhatsApp, Site, Indicação, Outra |
| Piloto (se for outra pessoa), Idade do piloto | a idade decide a waiver |
| Interesse (serviço), Valor estimado | podem ficar para depois |

**Do chat do Kommo:** botão **Passar para vendas**. Cada toque cria uma oportunidade nova ligada ao
mesmo lead (cliente que volta é negócio novo). Dois toques em menos de 60 segundos devolvem a
mesma.

### 4.2 Registrar a ligação

Botão **Registrar ligação** (`POST /sales/{id}/call`):

| Resultado | Código | A etapa vai para |
|---|---|---|
| Atendeu · fechou | `fechou` | Fechamento, e a tela de Fechar venda abre |
| Atendeu · vai pensar | `pensar` | Em conversa (se estava em Novo) |
| Não atendeu | `nao_atendeu` | Em conversa (se estava em Novo) |
| Sem interesse | `sem_interesse` | não muda; o retorno é limpo |
| Remarcou | `remarcou` | Em conversa (se estava em Novo) |

Junto: minutos, "o que ele falou" (ditado) e o retorno (data, hora e o que fazer).

### 4.3 Retorno, anotação, editar, perdido

| Ação | Botão | Rota |
|---|---|---|
| Marcar retorno | **Retorno** | `POST /sales/{id}/next` |
| Anotação interna | **Guardar anotação** (o campo fica em cima do Histórico, #312) | `POST /sales/{id}/note` |
| Editar a ficha | — (pela IA ou API) | `PATCH /sales/{id}`: o corpo **precisa** levar `name` |
| Mover etapa | — | `POST /sales/{id}/stage` |
| Marcar perdido | **Perdido** | `POST /sales/{id}/stage` com `etapa: PERDIDO` e `motivo` |

Os retornos vencidos ou de hoje somam no contador de vendas do menu e aparecem na Agenda de vendas.
Os **vencidos** também aparecem em **Precisa de atenção** ("retorno(s) de venda atrasado(s)", com o
link para a Agenda de vendas).

### 4.3.1 "De onde veio" — a campanha do contato (#260)

Dono, 15/10: *"sim pfvr"* para medir campanha no site novo. O contato que chega pelo `/contact/` do
site (e o pedido da loja) traz **de onde a pessoa veio** — e isso aparece no card da oportunidade,
na coluna da direita, no quadro **"De onde veio"**:

| O que você lê | O que é |
|---|---|
| origem / mídia / campanha | `utm_source`, `utm_medium`, `utm_campaign`: de onde o clique veio (ex.: `google / cpc / arrive-and-drive`) |
| termo / anúncio | `utm_term`, `utm_content`: a palavra buscada e qual anúncio |
| clique do Google / clique do Meta | `gclid` / `fbclid`: o clique pago em si. Tem um desses, o contato **veio de anúncio pago** |
| id da campanha / id do conjunto | `campaign_id`, `adset_id`: para achar a campanha no gerenciador |
| navegador (Meta) / clique (Meta) | `fbp`, `fbc`: o que o pixel deixou neste navegador |

**Como usar:** veio com `gclid` ou `fbclid`, é dinheiro de anúncio — vale ligar primeiro. O quadro
**não aparece** quando a pessoa chegou direto, pelo Instagram orgânico ou por indicação (aí a
campanha não existe e o sistema **não inventa** nada).

Nada da pessoa entra nesse quadro: é só campanha. Quem explica a medição inteira é o
[playbook geral](playbook-geral.md), seção 6, "Medição de campanha no site".

### 4.4 Preço: de onde vem

Preço nunca é de memória. A ordem (`brain/00_SYSTEM/PARAMETROS.md`):

1. o valor que o dono passar (vence tudo);
2. a **Rate Card** (planilha no Drive; serviço: aba Academy; corrida: aba Racing team);
3. invoice anterior do mesmo serviço e cliente (dizendo que reaproveitou);
4. catálogo do QuickBooks (defasado, só referência).

Para sessão do site, o preço está em **Site › Serviços e preços** (`GET /ops/api/site/servicos`).
Mudar preço é da gerência.

**No Fechar venda, o "Preço da tabela" vem do catálogo, não do valor da venda** (#204). É o preço
do **item do QuickBooks** escolhido em **Item do catálogo (QuickBooks)** (a Rate Card atualiza esse
catálogo toda segunda). Sem item escolhido, o painel procura o item com o mesmo nome do serviço, e
depois o serviço do site com esse nome. A lista vem de `GET /ops/api/sales/catalogo`.

### 4.5 Fechar a venda

Botão **Fechar venda** (`POST /sales/{id}/close`). Uma tela: à esquerda o que foi vendido, à direita
a lista do que acontece, cada linha com uma chave para desligar.

**Obrigatório para fechar:** serviço e valor. Sem isso o painel responde "Para fechar, diga o serviço
e o valor."

| Passo | O que faz (código) | Quando falha |
|---|---|---|
| **Card do cliente** (`cliente`) | usa o card vinculado; se não houver, procura pelo mesmo e-mail ou telefone (entre irmãos, o do piloto da venda); se não achar, cria. Nunca duplica. Com **"É irmão"** marcado, cria o card de irmão ao lado do que existe | o card do contato é de **outro piloto** e "É irmão" não está marcado: o passo para (o serviço não cai no card do irmão) |
| **QuickBooks** (`qbo`) | acha o cliente no QuickBooks (pelo e-mail, ou pelo nome se não houver e-mail), cria se faltar, e **cria e envia** a invoice: o valor fechado na linha do **item do catálogo** + o **depósito de segurança**, quando o serviço pede. A invoice vence na data do serviço. Fora da tabela, **não sai**: espera o gerente | QuickBooks fora do ar; serviço sem item no catálogo |
| **Waiver** (`waiver`) | DocuSign: parental se a idade é menor que 18, adulto se não (ou se a idade está vazia), para o nome e e-mail da ficha | sem e-mail; e-mail da URACE; já tem válida ou envelope aberto |
| **Asana** (`asana`) | tarefa no quadro U-RACE com o nome `Piloto_Serviço - data hora` e a data do serviço | Asana fora do ar |
| **Kommo** (`kommo`) | se a oportunidade veio do chat, move o lead para a etapa "Closed won" do funil dele | sem lead: só anota que não havia nada a mover |
| **Tarefa personalizada** | lembrete no painel ou tarefa no Asana, com o texto que você escrever | — |

Regras do fechamento:

- **Valor fora da tabela, ou serviço sem preço de tabela no catálogo:** a venda fecha, os outros
  passos saem, e a **invoice fica esperando o gerente ou o dono conferir o valor** (dono, 14/10:
  *"precisa confirmar o valor da invoice"*). Nada vai ao QuickBooks até lá. Gerente, administrador e
  a conta de acesso livre fecham e a invoice sai direto.
- O **Preço da tabela** não é digitado: vem do catálogo (seção 4.4). O `preco_tabela` mandado pela
  API não decide nada.
- **Depósito de segurança** (dono, 14/10: *"é cobrado em venda manual ou automática"*): quando o
  serviço pede depósito (o mesmo de **Serviços e preços** do site, ex.: Arrive and Drive US$ 400), ele
  entra **na mesma invoice**, na linha "Security deposit", igual à venda automática. A tela mostra o
  valor antes de confirmar.
- **Irmão:** se o card com o mesmo contato é de outro piloto, a tela avisa e traz marcado **"É irmão:
  criar o card de …"**. Desmarque só se o card for mesmo deste piloto.
- Falha de um passo não derruba os outros. A tela vira **acompanhamento**: cada linha diz feito,
  aguardando ou falhou, com **tentar de novo** ao lado do que falhou.
- **Ganho** só quando há card de cliente. Se o passo Card do cliente estiver desligado e não houver
  card vinculado, a oportunidade fica em Fechamento.
- Se você já criou a tarefa de serviço pelo modelo oficial (`POST /tasks`, com subtarefas),
  **desligue o passo Asana** no fechamento. Os dois juntos fazem duas tarefas.

### 4.6 Reenviar a invoice ou a waiver de uma venda

`POST /sales/{id}/step/{passo}`, com `passo` = `cliente`, `qbo`, `waiver`, `asana` ou `kommo`.
É o botão **tentar de novo**.

- **Não cobre duas vezes.** `step/qbo` **cria e envia uma invoice**. Use quando a linha do
  QuickBooks estiver como **falhou** (botão **tentar de novo**) ou desligada no fechamento com o valor
  da tabela (botão **mandar a invoice** na linha da invoice do acompanhamento). Se a invoice já saiu,
  o **sistema recusa** (#310): 409 "A invoice #… desta venda já saiu: não cobramos duas vezes". A
  venda **paga no site** (loja ou carrinho, no Stripe) também: 409 "O pedido #… desta venda foi pago
  no site (Stripe): não cobramos duas vezes". Para corrigir uma invoice que já saiu, fale com a
  gerência.
- **A trava vale de verdade para o botão, a API, o MCP e a IA, ao mesmo tempo** (#310). Quem cobra
  (fechar, Liberar, o passo, a IA, o depósito) marca a venda antes de falar com o QuickBooks; o
  segundo que chega no meio (outra aba, outro gerente, a IA, o MCP) recebe 409 "… está mandando a
  invoice agora" (ou "liberando a invoice", "fechando a venda", "cobrando o depósito", "mandando a
  invoice pela IA"). Espere um instante e recarregue: nada saiu duas vezes.
- **Nenhum passo antes de fechar** (#310): `step/{qualquer passo}` numa venda que ainda não fechou
  responde 409 "Feche a venda antes: os passos saem no fechamento". Feito antes, o fechamento faria
  de novo (e a invoice mandada antes deixava a venda presa).
- **Serviço sem item no catálogo do QuickBooks** (ex.: um serviço do site sem item): o passo falha
  com "o serviço não tem item no catálogo". O **tentar de novo** abre a janela **Mandar a invoice**,
  onde você escolhe o item: no preço da tabela do item, a invoice sai; fora dele, só o gerente ou o
  dono libera (o botão vira **Liberar invoice de $…** para ele). API:
  `POST /sales/{id}/step/qbo?item_id=<id do item>`; o item escolhido fica na venda.
- **Invoice esperando o gerente** não sai por `step/qbo`: a resposta é 409 ("A invoice espera o
  gerente conferir o valor…"). Avise a gerência (seção 4.6.1).
- **Fechar de novo não cobra de novo** (#310): numa venda em que a invoice ou o depósito já saiu (ou
  que o gerente está liberando agora), `POST /close` responde 409 "Venda já fechada…". O que faltou
  sai pelos botões de cada passo.
- Cada invoice mandada por `step/qbo` fica na auditoria (`sales.invoice.resend`), com quem mandou,
  o valor e o número da invoice. Antes de chamar o QuickBooks, cada saída que cobra grava
  `sales.invoice.sending` ("enviando"); o desfecho (a invoice que saiu ou `sales.invoice.failed`) leva
  o mesmo número de tentativa.
- **O QuickBooks não respondeu** (#310, 2ª revisão). Só conta como "nada saiu" o erro que prova isso:
  não conectado, o erro de antes da chamada (cliente, item, número da invoice) e a recusa do
  QuickBooks (HTTP 4xx, menos 408 e 429). Nesses, o botão volta a funcionar. Tempo esgotado, conexão
  caída, 5xx, 408 e 429 não provam: a resposta é 502 "O QuickBooks não respondeu (…): a invoice pode
  ter saído…", a venda fica marcada e o próximo pedido cai na **tentativa que não terminou** (seção
  4.6.3). Ninguém manda outra por cima.
- **Invoice criada, envio falhou**: o QuickBooks criou a invoice e o e-mail não saiu. A venda grava a
  invoice (número e id) e nada cria outra; ela sai de novo só pelo **Reenviar** (seção 4.6.4).
- `step/waiver` reenvia pelo DocuSign; as travas de waiver válida e envelope aberto continuam.
- Para corrigir o e-mail de uma waiver que já saiu, use o reenvio da waiver
  (`POST /waivers/{id}/resend` com o e-mail novo), não um envio novo.
- `step/cliente?irmao=true` cria o card de irmão quando o passo parou porque o card do contato era
  de outro piloto.

#### 4.6.1 Liberar invoice (gerente e dono)

A ficha da oportunidade mostra **"Invoice esperando o gerente conferir o valor"**, com o valor da
venda e o preço da tabela. O item também aparece em **Precisa de atenção** ("Invoice da venda de …
esperando você conferir o valor").

O Liberar também vale para dois casos que antes ficavam sem saída (#310):

- **Invoice desligada pelo closer**, com o valor fora da tabela (ou sem preço de tabela): a ficha
  mostra "Invoice desligada no fechamento, com valor fora da tabela". Não entra em Precisa de
  atenção, porque desligar foi escolha do closer. Se a invoice deve sair, o gerente libera.
- **Fechamento de antes de 14/10** que esperava aprovação: aparece em Precisa de atenção e se libera
  igual.

- Quem vende vê o aviso e "Só o gerente ou o dono libera."
- O gerente (ou o dono) clica **Liberar invoice**: a janela mostra serviço, **valor da venda**,
  **preço da tabela (catálogo)**, a diferença e o depósito. **Liberar invoice de $…** cria e envia a
  invoice pelo QuickBooks. Se o serviço ainda não tem item no catálogo, escolha o item ali.
- API: `POST /ops/api/sales/{id}/invoice/liberar` com `{"valor": <o valor da venda>}` (papel
  **Gerente**; opcionais `"item_id"` e, só para a tentativa que não terminou, `"confirmar": true`).
  Se o valor da venda mudou, a resposta é 409 e nada sai. Fica na auditoria
  (`sales.invoice.release`) com o valor, o preço da tabela e quem liberou.
- **Uma invoice só.** A que já saiu não sai de novo (409 "já saiu"). Dois cliques ao mesmo tempo
  (duas abas, dois gerentes), ou o Liberar junto com a IA, o passo, o fechamento ou o "Cobrar só o
  depósito", mandam uma invoice: o segundo recebe 409 "… está liberando a invoice agora" (ou o que o
  primeiro está fazendo). Se o QuickBooks falhar, nada sai e o botão volta a funcionar. Se ele
  respondeu e a gravação caiu, veja **A tentativa que não terminou** (seção 4.6.3).
- Nada que outro pedido grava no meio se perde (#310): um reenvio de waiver durante o Liberar não
  apaga o "liberada", e o depósito cobrado no meio não sai de novo na invoice.
- **Venda paga no site (Stripe)** não tem Liberar: a ficha mostra "Pago no site (Stripe)." e a
  linha da invoice, "pago no site (Stripe)". O cliente já pagou.
- **Serviço sem item no catálogo**: com o item escolhido na janela, o Liberar também vale para a
  venda que não esperava o gerente (API: `"item_id"` no corpo).
- No acompanhamento do fechamento, a linha da invoice mostra **Liberar invoice** para o gerente e
  "espera o gerente" para quem vende.

#### 4.6.2 Cobrar só o depósito

Venda fechada sem o depósito (fechada antes de 14/10, ou com a invoice desligada) e o serviço pede
depósito: a ficha mostra **"Depósito ainda não cobrado"** com o botão **Cobrar só o depósito**
(Operador). Sai uma invoice só com a linha "Security deposit", no valor do catálogo.

- API: `POST /ops/api/sales/{id}/deposit` (Operador).
- Não cobra duas vezes; com a invoice principal esperando o gerente, o depósito vai junto quando ela
  for liberada; serviço sem depósito responde "não pede depósito no catálogo". Venda paga no site
  (Stripe) responde 409; com o Liberar, o passo ou a IA cobrando no mesmo instante, também (#310).
- A invoice do depósito criada cujo envio falhou aparece como "Invoice do depósito nº … criada, o
  envio falhou", com o **Reenviar** (seção 4.6.4). O depósito já conta como cobrado.

#### 4.6.3 A tentativa que não terminou: "Não saiu: mandar" ou "Saiu: registrar o número"

Quando uma cobrança fala com o QuickBooks e não termina — o QuickBooks não respondeu, ou respondeu e a
gravação caiu —, a venda fica marcada. Nos 10 minutos seguintes a uma queda a resposta é "… está
mandando a invoice agora"; sem resposta do QuickBooks, ou depois desses 10 minutos, é 409 "A tentativa
de *nome* às *hora* de *dia* (…) não terminou: confira no QuickBooks se a invoice saiu". Vale para o
fechar, o Liberar, o passo, o depósito e a IA.

- **Quem vende** vê o aviso e chama a gerência. Não há botão para passar por cima.
- **O gerente (ou o dono)** abre o QuickBooks, procura a invoice do cliente (pelo nome, o valor e a
  hora da tentativa) e volta ao painel. Repete o que estava fazendo (Liberar, tentar de novo, fechar,
  cobrar o depósito); a tela pergunta "A tentativa anterior não terminou" com duas escolhas:
  1. **Não saiu: mandar** — a invoice NÃO está no QuickBooks. O painel manda e grava na auditoria que a
     tentativa antiga foi encerrada por você (`sales.invoice.confirmed`). A chamada leva a mesma
     identificação (`requestid`) da tentativa antiga quando é a mesma cobrança: se ela tinha criado a
     invoice, o QuickBooks devolve a mesma, sem criar a segunda.
  2. **Saiu: registrar o número** — a invoice ESTÁ no QuickBooks. Digite o **Invoice no.** dela e
     **Registrar a invoice**. O painel confere no QuickBooks (só leitura) que ela existe e é do cliente
     desta venda; se o total não bate com o que a tentativa cobrava, ele mostra os dois valores e
     pergunta **Registrar mesmo assim**. Registrada, a linha do QuickBooks fica como feita, com o
     número; a venda sai de Precisa de atenção; nada é cobrado de novo; e fica na auditoria
     (`sales.invoice.registered`).
- Se o fechamento inteiro caiu antes de gravar, o registro grava o fechamento com a invoice; os outros
  passos aparecem como "o fechamento caiu antes de gravar: confira se este passo saiu antes de tentar
  de novo".
- Sem o QuickBooks ligado, o registro é recusado ("Ligue o QuickBooks para conferir"): sem conferir,
  nada é registrado. Número que não existe, ou de outro cliente, também.
- API (gerente): "Não saiu" é `"confirmar": true` no corpo do Liberar e do `close`, ou
  `?confirmar=true` em `step/qbo` e `deposit`. "Saiu" é `POST /ops/api/sales/{id}/invoice/registrar`
  com `{"numero": "…"}` (e `"aceitar_diferenca": true` depois do aviso de valor). É outro `confirmar`,
  não o do MCP: o MCP pede o dele antes, e este vai no `corpo` ou na `consulta`. Quem vende recebe
  403; a IA não confirma nem registra.

#### 4.6.4 Invoice criada, envio falhou: Reenviar

O QuickBooks criou a invoice e o envio por e-mail falhou. A ficha mostra "Invoice nº … criada, o envio
falhou." e a linha do QuickBooks no acompanhamento tem **reenviar**.

- **Reenviar** manda a MESMA invoice pelo QuickBooks (como o lembrete). Nunca cria outra: o passo, o
  Liberar, o fechamento e a IA recusam com 409 "A invoice #… desta venda já foi criada no QuickBooks e
  o envio falhou: reenvie a mesma".
- Se o reenvio também falhar, a invoice continua criada e não enviada: tente de novo mais tarde.
- API: `POST /ops/api/sales/{id}/invoice/reenviar` com `{"invoice": "<id no QuickBooks>"}` (Operador).
  Fica na auditoria (`sales.invoice.send`).

### 4.7 A IA dentro da oportunidade

Na ficha há a caixa **Falar com a IA** ("ela age nesta oportunidade: registrar, agendar, waiver,
invoice, fechar"). Ditar funciona. O que ela pode fazer e quem aprova:

| Ação | Política (padrão do código, revisada pelo dono em 21/09) |
|---|---|
| registrar ligação, marcar retorno, anotar, criar tarefa | executa sozinha |
| enviar waiver | executa sozinha (as travas do DocuSign continuam) |
| mover etapa, fechar a venda | espera alguém confirmar (o Operador pode) |
| enviar invoice | espera confirmação, e **só gerente ou administrador** decide; fora da tabela, recusa se quem decide não é gerente. Só depois de fechar a venda e uma vez (#310): antes do fechamento, com a invoice já enviada ou com a venda paga no site (Stripe), recusa; a que ela manda fica no fechamento. Ela marca a venda como o botão: com alguém cobrando no mesmo instante, recusa; com a tentativa que não terminou, recusa (quem resolve é o gerente, pela tela: "Não saiu: mandar" ou "Saiu: registrar o número"; a IA não registra) |
| fechar a venda de novo | recusa se a invoice ou o depósito já saiu, se a venda foi paga no site (Stripe) ou se alguém está fechando ou cobrando agora (#310) |

A política em vigor de cada ação está em **O que a IA pode fazer** (`/ops/ai/capabilities`); o
administrador muda em Políticas da IA.

O **fechar pela IA da ficha** liga todos os passos e **confere o preço da tabela** no catálogo,
como a tela (#204). Fora da tabela (ou sem preço de tabela), a invoice fica esperando o gerente,
mesmo que quem confirmou a ação seja Operador; com o gerente confirmando, sai. O depósito entra
igual. Confira serviço, valor, idade e e-mail na ficha antes de confirmar.

### 4.8 O seu Google Calendar (#220)

Dono, 14/10: *"conectar ao Google Calendar e aí coloca um login com o Google, que aí ele consegue
logar com a conta dele do Google"*. Cada pessoa de vendas liga o **próprio** Google Calendar, com
**qualquer conta Google** (não precisa ser @urace.us), e funciona nos dois sentidos.

**Conectar (uma vez):**

1. **Agenda de vendas** (`/ops/sales/agenda`) ou **Minha conta** (`/ops/account`) › cartão
   **Google Calendar** › **Conectar ao Google Calendar**.
2. Abre a tela do Google: escolha a conta, confira que o acesso à **agenda** está marcado e toque
   em **Permitir** (ou **Continuar**).
3. Você volta à Agenda de vendas com o aviso **"Google Calendar conectado."** e o cartão mostra
   **Conectado como** a conta escolhida.

Botão cinza com o texto *"O gerente ainda não configurou o acesso ao Google…"*: falta o passo da
gerência (abaixo). Não há nada a fazer do seu lado até lá.

**O que vai para o Google (Painel → Google):**

| No painel | No seu Google Calendar |
|---|---|
| retorno marcado numa oportunidade **sua** (ligação, **Retorno**, IA da ficha, editar a ficha) | evento **"URACE · o que fazer: nome"**, 30 minutos, no horário da Flórida, com o link da oportunidade |
| mudou a data ou o "o que fazer" | o **mesmo** evento muda |
| perdido, sem interesse, venda fechada ou o retorno foi limpo | o evento que o painel criou **sai** |
| oportunidade passou para outra pessoa | sai do seu calendário e vai para o da outra pessoa (se ela tiver conectado) |

- Telefone e e-mail do cliente **não** vão para o Google: só o nome, o que fazer, o serviço e o link.
- Retorno só com a data (sem hora) vira evento de dia inteiro.
- O painel só mexe no evento que **ele** criou (guarda o id). Compromisso que você marcou no Google
  nunca é alterado nem apagado. Mude a data **no painel**: mudar o evento do painel direto no
  Google não volta para a oportunidade, e o painel acerta o evento de novo.
- Caiu a internet ou o Google: a venda segue normal, o cartão mostra o erro e o painel tenta de novo
  sozinho a cada 15 minutos. **Sincronizar agora** força na hora.

**O que volta (Google → Painel):** a Agenda de vendas mostra os **seus** compromissos do Google dos
próximos 7 dias, só leitura, com a etiqueta **Google** (hora, título; **livre** quando o evento não
deixa você ocupado). Retorno que cai em cima de um compromisso ocupado ganha a etiqueta
**conflito no Google**. Ninguém mais vê a sua agenda: nem gerente, nem a IA.

**Desconectar:** cartão Google Calendar › **Desconectar**. O painel revoga o acesso no Google e
apaga o seu token; os eventos que já estão no seu calendário ficam lá (apague à mão se quiser).
Conectar e desconectar ficam na auditoria (`google.connect`, `google.disconnect`), com a conta
Google, nunca com o token.

**Só pelo navegador, pela própria pessoa.** A IA, o Claude pelo MCP e a chave de API não conectam
nem desconectam (resposta 403). Mecânico e coach não têm o cartão.

#### Para a gerência: ligar o Google Calendar na VPS (uma vez)

O painel usa um **cliente OAuth do tipo "Aplicativo da Web"** do Google Cloud (o cliente que a VPS
já usa para o Gmail é do tipo Desktop e **não** serve aqui). O segredo fica só na VPS: nunca no
chat, no repositório ou em e-mail.

1. Em https://console.cloud.google.com, no projeto da URACE (ou num novo), **APIs e serviços ›
   Biblioteca** › ative a **Google Calendar API**.
2. **APIs e serviços › Tela de consentimento OAuth** (no console novo: **Google Auth Platform ›
   Branding / Público-alvo / Acesso a dados**):
   - Tipo de usuário: **Externo** (é o que deixa entrar qualquer conta Google, não só @urace.us).
   - Nome do app: **URACE Command Center**; e-mail de suporte e do desenvolvedor: o da URACE.
   - Domínio autorizado: **urace.us**. Página inicial: `https://ops.urace.us/ops/`.
     Política de privacidade: `https://ops.urace.us/legal/privacy.html`; termos:
     `https://ops.urace.us/legal/eula.html`.
   - Escopos: `openid`, `.../auth/userinfo.email` e `https://www.googleapis.com/auth/calendar.events`.
3. **Credenciais › Criar credenciais › ID do cliente OAuth** › tipo **Aplicativo da Web**:
   - Nome: `Command Center - Agenda de vendas`.
   - **URIs de redirecionamento autorizados:** `https://ops.urace.us/ops/api/google/callback`
     (exatamente assim, sem barra no fim).
   - Criar › **Fazer download do JSON**. O arquivo começa com `{"web": {...`.
4. Copie o arquivo para a VPS **pelo terminal** (nunca pelo chat) e proteja:
   ```
   scp client_secret_*.json ubuntu@<vps>:~/.urace/google-web-credentials.json
   ssh ubuntu@<vps> 'chmod 600 ~/.urace/google-web-credentials.json'
   ```
   Outro caminho? Ponha `CC_GOOGLE_WEB_CREDENTIALS=/caminho/do/arquivo.json` no
   `~/.urace/adminai.env`. O painel lê o arquivo a cada pedido: **não precisa reiniciar**.
5. O cofre precisa estar ligado (`CC_COFRE_CHAVE` no `adminai.env`): os tokens de cada pessoa são
   cifrados com essa chave. Sem ela, o cartão diz que falta.
6. Abra a Agenda de vendas: o botão **Conectar ao Google Calendar** fica azul.

**Testing ou publicado?** Na tela de consentimento, o "Status de publicação":

| | **Em teste (Testing)** | **Em produção, sem verificação** |
|---|---|---|
| Quem entra | só os e-mails cadastrados em **Usuários de teste** (até 100) | qualquer conta Google |
| Aviso na tela do Google | "O Google não verificou este app", com **Continuar** | **"O Google não verificou este app"**: a pessoa clica em **Avançado › Acessar URACE Command Center** |
| Validade da conexão | **7 dias**: depois o Google recusa a renovação e o cartão pede **Conectar de novo** | não expira sozinha (só se a pessoa revogar, trocar a senha ou ficar 6 meses sem usar) |
| Limite | 100 usuários de teste | 100 contas no total enquanto o app não for verificado |

Para a equipe de vendas (poucas pessoas), **publicar sem verificação** é o caminho prático: cada um
vê o aviso uma vez. A verificação do Google (para tirar o aviso e o limite) pede vídeo e revisão do
escopo `calendar.events` e só vale a pena se o número de contas crescer.

---

## 5. Site › Agendamentos

Tela: **Site › Agendamentos** (`/ops/site/agendamentos`; o resumo do site com as métricas fica em **Site › Painel do site**, `/ops/site`). Rotas em `/ops/api/site/…`.

### Os estados de um pedido

| Estado | O que quer dizer |
|---|---|
| `pendente` | o cliente pediu; a vaga está segura; ninguém aceitou ainda |
| aceita · esperando pagamento e waiver | `pendente` com "aceito": invoice e waiver já saíram |
| `confirmada` | pago (ou sessão do contrato) **e** waiver em dia |
| `recusada` | a equipe recusou (o cliente vê a nota) |
| `cancelada` | a equipe ou o cliente cancelou |

Regra do dono (05/10): **a sessão só é confirmada depois do pagamento e da waiver assinada.**
**Nada cancela sozinho**: sem pagamento ou waiver, a equipe decide.

### Quem faz o quê

| Botão | Rota | Papel | O que acontece |
|---|---|---|---|
| **Aceitar** | `POST /site/agendamentos/{id}/aceitar` | Operador | cria e envia a invoice no QuickBooks e a waiver; confirma sozinha quando pagar e assinar |
| **Recusar** | `…/{id}/recusar` (com `nota`) | Operador | o cliente vê a nota na área do cliente |
| **Cancelar** | `…/{id}/cancelar` | Operador | vale para pendente ou confirmada |
| **Confirmar mesmo assim** | `…/{id}/confirmar` | **Gerente** | confirma sem esperar pagamento e waiver |

O Operador **não** confirma direto: a resposta é "Confirmar sem esperar pagamento e waiver é do
gerente. Use Aceitar."

**Como a tela mostra cada pedido (#313, o cartão do padrão D):**

- **Em cima, a pílula do estado:** *esperando confirmação* (amarelo), *aceita · esperando pagamento e waiver* (azul),
  *confirmada* (verde), *recusada* (vermelho), *cancelada* (cinza).
- **Quem:** as iniciais e o nome do **piloto**, a idade, o **Responsável** (quando é outra pessoa) e o serviço com o preço.
- **O bloco grande:** o **dia** (ex.: *Sáb 18/10*) e o **turno**.
- **A barra "Pronto para confirmar"** (aceita, paga e waiver em dia: 3 de 3), só depois do Aceitar.
- **A lista:** o pagamento (*pago no site · pedido #N*, *invoice enviada*, *invoice não saiu*), a waiver, o pacote do
  aluno ou o contrato do mês, o **card do cliente** (ou *driver ainda sem card*), a tarefa do Asana, o e-mail e o
  telefone, a nota do cliente, os erros em vermelho e de onde veio (pelo site, campanha).
- **Os botões, embaixo:** **Recusar** (contorno vermelho) e **Aceitar** (azul) lado a lado; **Confirmar mesmo assim**
  (gerente) na linha de baixo; a confirmada que ainda vai acontecer tem **Cancelar**.

### O que o Aceitar faz (código: `providers/cobranca_agenda.py`)

1. **Invoice:** o preço gravado no agendamento + o **depósito**, quando o serviço tem depósito
   (configurado em Serviços e preços). A linha do depósito diz que é devolvido em até 5 dias úteis
   se não houver incidente. **Não cobra duas vezes**: se o agendamento já tem invoice, não cria outra.
2. **Aluno recorrente (Academy / Kart School, #314):** a sessão já nasce marcada como **do plano** ou
   **extra** (chip na lista: "do plano" ou "extra $689.23 · invoice …", com o pacote do mês ao lado, que
   só a equipe vê). A do plano não cobra nada. A **extra** (acima do pacote do mês) vai numa invoice do
   QuickBooks com o **item da sessão extra** (no QuickBooks: "Academy | Extra session (beyond monthly 4)")
   e o **valor da extra, sem depósito**. Veja "Aluno recorrente" logo abaixo.
3. **Waiver:** se o piloto não tem waiver válida no dia da sessão, sai pelo DocuSign. Com a waiver
   nativa ligada, o cliente assina na área do cliente.
4. **Confirma sozinha** quando a invoice aparece paga e a waiver está em dia.
5. **Lembrete ao cliente** por e-mail 3 dias e 1 dia antes, dizendo o que falta.
6. Falhou algo (sem card, sem cliente no QuickBooks, serviço sem item)? O motivo fica escrito no
   agendamento e o painel tenta de novo (a invoice, até 3 vezes).

Cliente com contrato e waiver em dia: o pedido **confirma sozinho** assim que é marcado (a sessão do plano).

### Aluno recorrente: pacote do mês e sessão extra (#314)

Dono, 16/10: *"Quando for cliente do Kart School … pagam pelo QuickBooks. O invoice deles é recorrente …
ele não precisa efetuar o pagamento, a não ser que as sessões daquele pacote dele … Se ele já tiver usado
as sessões daquele pacote dele mensal, aí ele paga uma sessão adicional."* Academy e Kart School são a
mesma coisa.

- **Quem é recorrente:** o card do **piloto** tem contrato (plano mensal, valor mensal ou sessões por mês).
  Plano comprado no site só vale **depois da 1ª mensalidade paga**. Plano cuja recorrência acabou não vale
  mais. Pro Racing Driver sem mensal no card **não** é recorrente. Piloto do site sem card ligado ainda não
  é recorrente: ligue o card (Contas do site) antes de ele marcar.
- **Pacote do mês:** as sessões por mês do card (sem número, 4). Zera no dia 1, também nos contratos de 6
  e 12 meses. A sessão extra e a paga no Stripe **não** ocupam vaga. Cancelar uma do pacote (pelas regras
  de cancelamento de sempre) devolve a vaga do mês.
- **Preço da extra**, nesta ordem: o **Valor da sessão extra** da Mensalidade do card → o do **plano**
  (Site › Serviços e preços) → o **mensal do card ÷ sessões do mês**, em centavos com arredondamento
  comercial (2.756,90 ÷ 4 = 689,23; 1.378,45 ÷ 2 = 689,23).
- **Item da extra**, nesta ordem: o do card → o do plano → o item "Extra session" do QuickBooks.
- **O cliente vê** só "Included in your plan" ou "Extra session · $689.23" em cada dia. O contador
  ("2 de 4 no mês") fica com a equipe (dono, 01/10).
- **"Confirmar sozinho"** confirma a do plano, mas **não** confirma a extra: ela espera a invoice e a waiver.
- **Extra cancelada** com a invoice aberta vira aviso em **Precisa de atenção**: anule a invoice (ou tire a
  linha dela) no QuickBooks.
- **Vaga devolvida antes da cobrança:** se o cliente cancela uma do pacote e a extra do mesmo mês ainda não foi
  cobrada, na hora de cobrar a extra passa a ser do plano (sem invoice). Em pedido de vários dias, a invoice
  leva só as que continuam extra.
- **Extra sem valor** (card sem mensal e sem "Valor da sessão extra"): fica escrito no agendamento "sem valor da
  sessão extra". Ponha o valor na Mensalidade do card e clique **Aceitar** de novo: a invoice sai com o valor
  novo, que fica gravado na sessão.
- **No card, "acima do contrato"** conta o que passou do pacote e as extras do mês. A sessão paga no Stripe e
  a avulsa não entram nem na vaga nem em "acima".
- **Onde se combina:** card do cliente › Mensalidade (gerente): "Valor da sessão extra" (vazio mostra a
  conta que vale) e "Item da sessão extra".

**Vários dias num pedido** (dono, 16/10: *"se ele quiser marcar para quartas, toda quarta. Ou quartas e sábado
dessa semana, ou então sábado e domingo da outra, ele consegue marcar isso tudo em um book"*). Na área do
cliente (**Book sessions**, `/portal/book`), o aluno recorrente:
- toca nos dias do calendário (marca e desmarca) ou usa os atalhos **Every Wed** (e os outros dias que a agenda
  abre), com **Repeat until**: o fim deste mês, as próximas 4 semanas ou até uma data, sempre dentro do que a
  agenda mostra; **This weekend** e **Next weekend**. Atalho sem dia aberto avisa ("No open days that weekend.");
- escolhe o **Session type** antes: sem ele, a tela diz "Pick the session type above to see what is included";
- vê em cada dia o turno (manhã, tarde, dia todo) e o rótulo do servidor: **Included in your plan** ou **Extra
  session · $689.23**; o resumo mostra "3 included · 2 extras" e, ao lado, "$1,378.46";
- marca **no máximo 12 dias** por pedido; **ou entram todos, ou nenhum**: um dia que lotou no meio do caminho
  volta para o cliente escolher outro, sem marcar os demais. Se a vaga ou o preço mudou entre ver e marcar, a
  tela pede para revisar;
- num dia que o plano **não cobre** (a recorrência acaba antes daquele mês, como no último mês de um contrato de
  6 ou 12 meses), o dia diz isso e tem o botão **Book as a regular session**: abre a marcação de um dia, paga
  como a de qualquer cliente (**Add to cart**, no Stripe, com o Stripe ligado; senão **Request session** e a
  invoice). "Back to my plan days" volta para os vários dias.

Na lista da equipe, cada sessão do pedido tem o chip **"pedido de vários dias #n"**. **Aceitar** uma delas
aceita o **pedido inteiro**: as extras saem numa **invoice só** do QuickBooks (uma linha por sessão extra,
item e valor da extra, sem depósito), a waiver sai uma vez, e o cliente recebe **um** e-mail com todos os dias,
o que é do plano e o que é extra. Com a venda automática ligada, isso acontece sozinho na hora.
- O cliente acompanha em `/portal/sessions/group/<n>`: os dias, a invoice das extras, a waiver e a confirmação.
  Paga a invoice, todas as extras do pedido ficam pagas. No painel do Site, essa invoice entra **uma vez** na
  receita (não uma vez por dia).
- A lista de sessões do cliente (My sessions) vem em páginas de 50 ("Show more sessions").

**Um dia pela Reserva do site** (`/portal/reserve`): o aluno recorrente não vê preço cheio, depósito nem total;
a etapa 4 mostra "Included in your plan" ou "Extra session · $689.23". Se a última vaga do mês foi ocupada entre
ver e clicar (outra aba, uma tarefa de treino no Asana), a sessão **não** é marcada: a tela avisa "Your booking
changed…", mostra o rótulo novo e só então libera o botão. O dia fora do plano vira sessão avulsa (carrinho ou
invoice), como acima.

### Duas chaves da agenda (só leitura para quem vende)

| Chave | Onde | Quem muda | Efeito |
|---|---|---|---|
| **Confirmar sozinho** (`auto_confirm`) | Disponibilidade | Gerente | o pedido já nasce **confirmado**, sem passar pelo Aceitar. Nesse caso o painel **não** gera invoice nem waiver para ele: confira pagamento e waiver por fora. A **sessão extra** do aluno recorrente nunca nasce confirmada: espera a invoice e a waiver (#314) |
| **Venda automática** (`auto_sell`, #164) | Disponibilidade | **só Administrador** | o pedido não espera o Aceitar: na hora, o card do piloto é garantido, o cliente no QuickBooks é achado ou criado, invoice + depósito + waiver saem, e o cliente recebe e-mail com o que falta e outro quando confirma. #314: o **cliente novo** paga no Stripe pelo carrinho do site (sem o Stripe, invoice + depósito); o **aluno recorrente** tem a sessão do plano sem custo e a extra numa invoice do QuickBooks, sem depósito |

Na venda automática, o card só é ligado sozinho a um card que existe com **duas provas**: o e-mail
confirmado da conta é o do card **e** o nome do piloto é o do card. Fora disso nasce card novo
marcado "POSSÍVEL DUPLICADO" para a equipe conferir e unir.

**Plano mensal pelo site** (#169, Academy): o cliente compra o plano, a primeira
mensalidade sai na hora e as outras ficam agendadas no dia 1. Nada é cobrado sem a venda
automática ligada.

### O que o site vende, pelo nome (#254)

Dono, 15/10: *"o kart school se tornou Urace academy, e o professional coaching se tornou o arrive and
drive"*. Na página de programas (`novo.urace.us/services/`) ficam sete: **Arrive and Drive**, **URACE
Academy**, Intensive Training Camp, Racing Team, Birthday Party, Corporate Events e Group Events (mais
o Sim 2 Grid, que abre em 1/11/2026). **Kart School** e **Professional Coaching** não existem mais como
programa.

| O cliente pede | Venda | Página |
|---|---|---|
| Kart School, aula mensal, kart school | **URACE Academy** (mensal, 4 sessões) | `/academy/` |
| Professional Coaching, coaching, treino avulso | **Arrive and Drive** (diária) e, se quiser coach na pista, **Lead and Follow** | `/services/arrive-and-drive/` |

Os endereços antigos (`/services/kart-school/` e `/services/professional-coaching/`) redirecionam
sozinhos para a página que herdou: link velho de cliente ou de anúncio continua abrindo. No painel, o
**produto da tarefa** não mudou de nome (*Urace Daily*, *Academy*, *Lead and Follow*, *Arrive and
Drive*… — seção 8): mudou o nome do programa no site, não o do quadro.

Preço, sempre da **planilha de preços** do dono (15/10, #273). A taxa de pista **não** está incluída:
é paga direto à pista.

- **Diária** (Arrive and Drive / dia de Academy): kart próprio $500 · Baby Kart $719 · 4 stroke $719 ·
  2 stroke $819 · Adult Shifter $899.
- **Lead and Follow** é um **add-on do dia de treino** — Arrive and Drive ou Academy — e no site vale só
  **$769 por dia de treino** (dono, 15/10). O pacote de 5 e o last-minute não são oferecidos no site.
- **Academy, mensal sem contrato (4 sessões)**: Baby Kart e 4 stroke **$2.756** ($689 a sessão) · 2 stroke
  **$3.156** ($789) · kart próprio $1.800 ($450 a sessão extra) · kart próprio + mecânico $1.200 ($300).
- **Contrato de 6 meses** (27 sessões, 4%, entrada de 33% e 5 parcelas): 4 stroke **$17.858,88**
  (entrada $5.893,43, parcelas de $2.393,09) · 2 stroke **$20.450,88** ($6.748,79 e 5 × $2.740,42).
- **Contrato de 12 meses** (54 sessões, 8%, entrada de 20% e 11 parcelas): 4 stroke **$34.229,52**
  (entrada $6.845,90, parcelas de $2.489,42) · 2 stroke **$39.197,52** ($7.839,50 e 11 × $2.850,73).
- **Fora do OKC**: Academy +$250 (hotel, comida e transporte).

Os planos de 3 meses, o de 6 meses a 5% e o **URACE Boost** saíram do site: não estão na planilha.

**Na reserva do site** (#279, dono 15/10):
- **Lead and Follow** é uma caixinha ao lado do kart: *Add Lead and Follow (+$769)*. Vai para o carrinho
  como linha própria, é pago no Stripe junto com a sessão, e a sessão agendada mostra nas notas
  "+ Lead and Follow (add-on, US$ 769.00, paid)" — é por aí que a equipe sabe que aquele dia tem coach na
  pista. O preço é o do painel (*Site › Serviços e preços*, serviço de tipo add-on); desativar
  o serviço tira a caixa do site.
- **Own kart — $500** é a 5ª opção (4 anos ou mais, qualquer categoria), **sem depósito**. O cartão e o
  carrinho avisam: *o kart tem de chegar à pista com no mínimo 2 dias de antecedência para checagem e
  manutenção*. Quem compra kart próprio pelo site: confirme a data de entrega do kart com o cliente.
- **Convidado**: o passe varia de **$15 a $22** e é cobrado direto pela pista — não é da URACE.

### 5.1 Carrinho do site e pagamento no Stripe (#236)

Dono, 14/10: *"o sistema de carrinho e checkout ... usando o Stripe"*; *"quando a pessoa selecionar
o serviço, selecionar a data, já vai com aquele serviço e o preço que está lá"*; *"O depósito de
segurança ele é cobrado em venda manual ou automática"*; *"Todo mundo agora precisa de conta no site"*.

**Quem paga no Stripe e quem paga no QuickBooks** (#314, dono 16/10: *"Quando for agendamento direto pelo site
de cliente novo, que não for do Kart School, ele vai pagar pelo Stripe. Quando for cliente do Kart School … esses
clientes pagam pelo QuickBooks"*):

| Cliente | Onde marca | Como paga |
|---|---|---|
| **Novo** (sem plano), Stripe ligado | site, Reserva (`/portal/reserve`) ou Book a session | **carrinho do site (Stripe)**: o último botão é **Add to cart**, com o piloto já escolhido |
| **Novo**, Stripe desligado | os mesmos | invoice do QuickBooks (serviço + depósito), como antes |
| **Aluno recorrente** (Academy / Kart School) | área do cliente (Book sessions; um ou vários dias) | sessão do plano: nada; **extra: invoice do QuickBooks**, sem depósito |

O carrinho **recusa** a sessão de piloto com plano mensal vigente: a linha fica vermelha com "has a monthly
plan: book this session in your account" e o link **Book it in your account**; o checkout não abre no
Stripe. A sessão extra nunca vai para o Stripe.

**O que o cliente faz** (site novo, em inglês; o carrinho e as páginas do pedido também em português, #248):

1. Na página do Arrive and Drive escolhe o kart, o dia e o turno e toca no **único botão** da agenda
   (#262, dono 15/10: *"sim um caminho somente levando para o carrinho"*): ele diz o que falta
   ("Pick a day to continue" sem dia, "Pick a time to continue" com o dia e sem turno) e, com tudo
   escolhido, vira **Add to cart · $<preço> + $<depósito> deposit**, põe a sessão no carrinho e leva
   para `/cart/`. O preço mostrado é o do serviço do painel. Na reserva da área do cliente
   (`/ops/portal/reserve`) também há **Add to cart**. Na loja, **Add to cart** ao lado do **Buy now**.
   **Toda compra pede a conta do site** (#248, dono 14/10: *"Para a pessoa conseguir comprar com a gente,
   ela tem que criar a conta dela lá no site da URACE"*): **Buy now** sem conta leva para entrar (ou criar
   a conta) e volta para o produto.
   > **O serviço aponta o kart pelo campo "Kart do site"** (#263, dono 15/10: *"o mais lógico é ir com o
   > produto que foi selecionado na mesma página que selecionou a data e daí clicar no add to cart"*).
   > Em **Site › Serviços e preços**, cada serviço de sessão tem o seletor **Kart do
   > site** (Baby Kart · 4-stroke · 2-stroke · Adult Shifter, ou "não é do site"). É esse campo — e não
   > mais o nome — que liga o serviço ao kart da página: foi o casamento por nome que fez um serviço
   > chamado "teste" aparecer pré-selecionado como se fosse o produto. Os quatro serviços
   > ("Arrive and Drive Baby Kart", "… 4-stroke", "… 2-stroke", "… Adult Shifter") já vêm cadastrados,
   > com os preços da Rate Card (719 · 719 · 819 · 899) e o depósito de US$ 400; **o painel manda** no
   > preço (mudar ali muda o site).
   > **Desativar o serviço tira aquele kart da página**: em vez de deixar na tela um produto que não dá
   > para comprar, o kart sai da lista. Nenhum serviço ativo: o site e a reserva dizem que a reserva
   > online está fechada e mandam falar com a gente. Dois serviços ativos com o mesmo "Kart do site"
   > é ambíguo — o site não escolhe por ninguém e o kart também sai; deixe **um** serviço por kart (o painel,
   > desde o #312, não deixa criar, trocar para o kart ocupado nem reativar o segundo).
   > **O cartão do kart no site também é do painel** (#297, dono 16/10: *"alterar o valor, alterar o nome,
   > alterar as coisas ali pelo Command Center"*). No mesmo serviço: **Nome no site** (o que o cartão mostra),
   > **Linha de baixo no site** (ex.: *Ages 7+*), **Aviso no cartão** e **O cliente traz o próprio kart**.
   > Vazio volta ao texto de sempre. O "Kart do site" continua sendo a chave: mudar o nome no site não
   > desliga nada. **Kart novo:** no seletor "Kart do site", escolha **Novo kart…** e dê um nome curto
   > (ex.: *Rental 2-stroke Pro*); salvo, ele entra na página do Arrive and Drive com o preço e o depósito
   > daquele serviço. No Lead and Follow, o **Nome no site** e a **Descrição** são o que a caixa da reserva mostra.
   > **Serviço novo** (#312, dono 16/10: *"um botão de adicionar novo serviço e a gente escolhe em qual página que
   > esse serviço vai estar"*): **Adicionar serviço**, em cima da lista, pergunta **"Em qual página do site?"** e,
   > no Arrive and Drive, **Kart (reserva online)** ou **Add-on do dia (Lead and Follow)**; na Academy, **Plano
   > mensal** ou **Cartão de preço**; no Pro Team e no For Beginners, o cartão de preço; ou **Só na área do
   > cliente** (sessão sem kart). A tela mostra o que já está na página hoje. No kart, o seletor só deixa escolher
   > kart sem serviço ativo (os outros aparecem com o serviço de hoje) ou **Novo kart…**; com o add-on já ativo, o
   > segundo não se cria. Cada serviço da lista diz onde aparece no site hoje (**no site: Arrive and Drive · kart
   > 4-stroke**) ou, em vermelho, por que está **fora do site**. A trava vale também no card de edição, no
   > **Reativar** e no servidor (API e Claude): *"O kart … já é vendido por "…": … Desative aquele antes ou escolha
   > outro kart."* — desative o serviço de hoje daquele kart primeiro.
   > **Teste de checkout de US$ 1:** no serviço do kart, desmarque **Security deposit obrigatório**, ponha preço
   > **1** e depósito **0**; reserve, pague (o Stripe cobra US$ 1,00 de verdade) e **volte o preço, o depósito e
   > marque Obrigatório de novo** logo depois (veja 5.4); o estorno sai pelo Stripe.
2. O ícone do carrinho no topo mostra quantos itens há. Em **`/cart/`** ele vê as linhas, o depósito e
   o total. Toda compra pede a conta do site (#248), e **o próprio carrinho cria a conta** (#305, dono
   16/10: *"ao invés de ter o botão de seguir e create account … ela vai ter que preencher as informações
   dela … Quando for para o checkout, já cria a conta dela"*):
   - **Logado:** o carrinho mostra o nome e o e-mail da conta e o **piloto** de cada sessão (um piloto só
     já vem escolhido), como antes.
   - **Sem conta:** em vez de "Sign in / Create account", o carrinho pede **os dados dele** ali mesmo:
     nome completo, data de nascimento, e-mail, país e telefone, endereço (nos EUA, com estado e ZIP), **quem vai
     pilotar** (com uma sessão: *eu* ou *outra pessoa*, só o nome; com duas ou mais: **o nome do piloto de cada
     sessão**, para o serviço de um filho nunca cair no card do outro), **senha e confirmação** (8+ caracteres, as
     duas iguais) e o aceite dos **termos e da privacidade** (os links abrem em outra aba). No **Checkout**, a conta nasce sozinha, ele já fica logado e vai ao
     Stripe. Quem já tem conta toca em *Already have an account? Sign in*; se o e-mail já tiver conta, o
     carrinho avisa e mostra o *Sign in*.
   - **Piloto incompleto não trava mais** (decisão do dono, 16/10: *"com lembretes pelo email ate
     completar as informações"*): a linha avisa *"After payment, we'll email you a link to add … "*, ele
     paga e completa as medidas e a experiência depois, na área do cliente. O **responsável** continua
     precisando dos dados completos.
   No topo do carrinho e das páginas do pedido há a chave **English / Português** (as bandeiras, como no
   painel); a escolha fica guardada no navegador.
3. **Checkout** abre o Stripe com **todas** as linhas e, para cada sessão com depósito, a linha
   "Refundable security deposit". Paga, volta para `/cart/thanks/` com a **página do pedido** (abaixo).

**Um caminho só, e o Stripe é o único pagamento do site (#262, dono 15/10).** A página do Arrive and
Drive tem **um** botão, ele leva ao carrinho, e o texto embaixo conta esse caminho: *carrinho → conta
→ Stripe → waiver*. O "Continue to booking" saiu do site público, e com ele a promessa da invoice do
QuickBooks. **A invoice do QuickBooks continua existindo para a venda feita pela equipe** — o que
mudou é só o que o site público oferece. Se o cliente ligar dizendo que "recebeu uma invoice", é
venda da equipe (a invoice aparece no card); o que veio pelo site está em Site ›
**Pedidos do site** (Stripe). A comparação completa dos dois sites está em
`docs/site-publico/comparacao-urace-us.md`.

**Afiliados: encerrado (#262, dono 15/10: "encerra").** Não existe programa de afiliados. Quem chegar
por `/affiliate-account/` (ou pelos outros endereços do SliceWP que o urace.us publicava) cai em
`/contact/`. Se alguém perguntar por comissão de indicação, não existe programa hoje — anote o
contato e passe para o dono.

**Regras que o sistema garante** (código: `providers/carrinho.py`):

| Regra | Como |
|---|---|
| preço é do sistema | o servidor recalcula preço (Serviços e preços / catálogo da loja), depósito e vaga; o navegador só manda as escolhas |
| preço do dia | o pedido guarda o preço e o depósito do dia da compra; mudar o preço depois não muda o pedido |
| vaga | confere ao montar o carrinho, no checkout (o Checkout do Stripe expira em 31 min) e **de novo no pagamento** |
| conta e piloto | **toda compra pede a conta do site** (logado, ou criada no próprio carrinho, #305); o e-mail da conta vai para o Stripe e é o dos avisos; só pilotos da própria conta; o responsável com os dados completos; o piloto pode estar incompleto (completa depois, com lembrete) |
| conta criada no carrinho | o carrinho é conferido **antes** (vaga, serviço, produto e o mesmo piloto em duas sessões no mesmo horário): carrinho que não fecha não cria conta; a conta e os pilotos entram juntos ou nada entra; o mesmo nome em duas sessões é o mesmo piloto, e o nome do titular é ele mesmo; limite de 10 tentativas por hora por conexão (no IPv6, por bloco /64) e 100 contas novas por hora no total; só JSON do próprio site (outro site não cria conta); se o Stripe falhar depois, a conta fica e ele tenta de novo já logado |
| card certo | a sessão vai para o card do **piloto**; o produto, para o card ligado à **conta** (Contas de clientes) ou, sem ele, pela regra da loja (e-mail **e** nome) |
| idioma | o pedido guarda o idioma em que a pessoa comprou (EN/PT): os e-mails dela saem nele e o Stripe abre nele; os avisos da equipe são sempre em português |
| uma vez só | o webhook do Stripe e a página de obrigado não marcam nem vendem duas vezes |
| cancelado / expirado / pagamento não passou | nada é marcado nem vendido; a vaga **não fica presa** (a sessão só entra na agenda quando o pagamento entra) |

**Os e-mails da conta (#305).** Todos com a identidade da URACE (faixa preta com a marca, botão vermelho,
endereço e telefone no rodapé), em inglês ou português, conforme o idioma da pessoa:

| E-mail | Quando | O que tem |
|---|---|---|
| **Welcome to URACE: your account is ready** | na hora em que a conta nasce, no carrinho **ou** na tela de cadastro da área do cliente | login (o e-mail), **a senha que ela criou** (decisão do dono, 16/10: *"Mandar a senha no e-mail"*), o número de cliente (ou "chega por e-mail assim que o card estiver pronto"), o botão para a área do cliente e o link do *esqueci a senha* |
| **Your URACE customer ID: N** | quando o **card** do piloto nasce (a sessão paga cria ou liga), ou quando a equipe liga a conta de quem comprou só produto: o número é o **card interno** (dono, 16/10) | o piloto, o número de cliente e o login; uma vez por piloto. Se a equipe unir um card duplicado ou religar o piloto, sai de novo com o número certo (*"changed: this is the right one"*). Contas de antes do #305 não recebem de surpresa |
| **Almost there: complete …'s profile** | sessão **paga** com o piloto incompleto | o que falta (altura, peso, peito, cintura, experiência…) ou, com as medidas vencidas, *revise e salve as medidas*, e o botão para *Drivers*; **um a cada 24 h**, até completar, no máximo 7 (o 7º diz que é o último), e só enquanto a sessão não passou nem foi cancelada. Completou, a contagem zera para a próxima vez |
| **Reset your URACE password** | *Forgot password?* na área do cliente | o link de uso único que vale 30 min |

A senha só passa pela memória do servidor na hora do cadastro: vai no e-mail e o banco guarda só o hash (a cópia
do e-mail fica, como todo e-mail mandado, na pasta Enviados da conta que envia). Se o Gmail falhar, o servidor tenta
de novo na hora; continuando fora, a conta fica (a pessoa entra normalmente), o erro fica na conta e as boas-vindas
saem depois **sem a senha** (com o link do *Forgot password?*), no máximo uma vez por hora, até 7 dias. Em
**Site › Contas de clientes** a conta mostra *"O e-mail de boas-vindas não saiu"* com o motivo, e a auditoria
registra. Toda
boas-vindas tem a linha *"Didn't create this account? Choose a new password at … (that signs out every other device)
and reply to this email or call…"*: se alguém criou a conta com o e-mail de outra pessoa, a dona do e-mail troca a senha
(isso derruba a sessão de quem criou) e avisa; a equipe fecha a conta.

**Uma página para cada resultado do pagamento** (#245, dono 14/10: *"monte páginas para cada um no
site"*). Todo pedido do site (carrinho **e** loja de um produto) tem um **link pessoal**,
`/order/<código>/`, que não dá para adivinhar (link mexido = página não encontrada). A página mostra o
que o Stripe disse (em inglês ou português, na chave do topo) e **os dados do cliente da conta** (#248:
nome, e-mail, telefone, endereço, pilotos do pedido e a entrega), além dos itens e valores.

**Aviso sempre** (#248, dono 14/10: *"o cliente e a equipe precisam da confirmação de pagamento sempre e
deixar isso também registrado no card do cliente no Command Center"*): em **todo** resultado, um e-mail
para o cliente, um aviso para `support@` e um registro na **Linha do tempo do card** ("Pagamento no site",
com o valor e o botão **Página do pedido ↗**). Um de cada por resultado por pedido, nunca dois:

| O Stripe avisou | A página diz | O cliente recebe por e-mail (com o link da página) | A equipe |
|---|---|---|---|
| `checkout.session.completed`, pago | **Payment confirmed** / *Pagamento confirmado*: itens, total, depósito, dados do cliente, o que vem a seguir | a confirmação | "Site · PAGO" (ou "Loja · PAGO") |
| `checkout.session.completed`, meio que confirma depois (transferência) | **Payment processing** / *Pagamento em confirmação*: não pague de novo | "We're confirming your payment" / *"Estamos confirmando o seu pagamento"* | **"Site · PROCESSANDO O PAGAMENTO"** (não há venda até pagar) |
| `checkout.session.async_payment_succeeded` | vira **Payment confirmed** | a confirmação | "Site · PAGO"; a venda entra GANHO |
| `checkout.session.async_payment_failed` | **Payment didn't go through** / *O pagamento não foi concluído*: nada foi cobrado; botão **Try again** | "Payment didn't go through" / *"O pagamento não foi concluído"* | **"Site · PAGAMENTO FALHOU"** com o link da página |
| `checkout.session.expired` | **Checkout expired** / *O checkout expirou*: nada foi cobrado; botão **Restore cart** | "Your checkout expired" / *"O seu checkout expirou"* (no e-mail da conta) | **"Site · CHECKOUT EXPIROU"** |

O registro no card vai para o card do **piloto** (sessão) e para o card ligado à **conta** (produto),
cada um só com as suas linhas. Conta ou piloto ainda **sem card** ligado: não registra (nunca no card de
outro cliente); ligue em **Site › Contas de clientes**.

- **Try again** abre um checkout novo com as **mesmas escolhas** (produto, opção, quantidade; serviço,
  dia, turno, piloto). O servidor recalcula **preço, depósito e vaga** na hora: se o preço mudou, vale o de
  hoje; se a vaga acabou ou o cliente não está logado na conta do pedido, ele cai no carrinho com as
  escolhas de volta e o carrinho mostra o porquê (e pede para entrar).
- **Restore cart** põe as escolhas de volta no carrinho do navegador (junto do que já estiver lá, sem
  duplicar) e o cliente confere e paga pelo **Checkout** de sempre.
- O pedido novo fica ligado ao antigo ("refeito do pedido #N"); pago o novo, a página do antigo aponta
  para ele e não oferece pagar de novo.
- O e-mail que não saiu (Gmail fora do ar) a rodada de 15 min tenta de novo, sem repetir o que já saiu.

**Onde a equipe vê:** **Site › Pedidos do site** (`/ops/site/pedidos`) lista todos os
pedidos do carrinho e da loja em **todo** estado (pago, processando o pagamento, pagamento não passou,
checkout expirou, no checkout), com filtro, quem, o quê, o total, se o aviso por e-mail saiu (e se a
pessoa comprou em português), e os botões
**Página do pedido ↗** e **Copiar o link**: é esse link que você manda ao cliente que liga perguntando do
pedido. Cada pedido é um cartão do padrão D (#313): o estado em cima, quem comprou, o resumo e o contato; no **bloco
grande, o total**, com o nº do pedido e a hora; a lista diz o aviso por e-mail, o **Resolver** e o **Estoque**; embaixo,
**Resolvido** (quando ficou sem estoque), **Página do pedido ↗**, **Copiar o link** e **Venda**. No detalhe da venda, o
cartão **Pedido do site #N** também tem os dois botões. **Quem vende**, no
e-mail "Site · PAGAMENTO FALHOU" ou "Site · CHECKOUT EXPIROU": o cliente já recebeu o botão (Try again /
Restore cart) no e-mail da conta, e um contato ajuda a fechar; se o aviso disser "sem e-mail do cliente"
(pedido antigo, de antes da conta obrigatória), ligue e mande o link.

**O que aparece para a equipe quando o pedido é pago:**

- **Site › Agendamentos:** a sessão entra **aceita e paga** (chip "pago no site · pedido #N"); não sai
  invoice do QuickBooks. Falta só a **waiver**: a nativa o cliente assina na conta; sem ela, sai pelo
  DocuSign na hora. Assinada, confirma sozinha.
- **Vendas:** uma oportunidade **GANHO** (origem Site) **por card**: a sessão vai para o card do
  **piloto** (o que ele já tem, o comprovadamente dele, ou um card novo marcado "possível duplicado"),
  nunca para o card de outro cliente. Dois irmãos no mesmo pedido = duas vendas, uma em cada card.
  Produto da loja segue a regra da loja (e-mail **e** nome batem). Sem card certo, a venda fica em
  **Fechamento** com "vincular à mão". No detalhe da venda, o cartão **Pedido do site #N** mostra
  todas as linhas (serviço, dia, turno, piloto, depósito, produto) e o recibo do QuickBooks.
- **QuickBooks:** um **Sales Receipt** (já pago) `WEB-0000N` com o item do serviço, o item
  "Security deposit" e o item do produto. Falhou (serviço sem item do QuickBooks, item "Security
  deposit" não sincronizado)? Aparece na venda "QuickBooks: registrar a venda à mão" e a rodada de
  15 min tenta de novo.
- **E-mail:** o cliente recebe a confirmação (com o link para assinar a waiver de cada sessão e o link
  da página do pedido) e `support@` recebe o aviso com as linhas e os links de Vendas.

**Vaga que sumiu entre o checkout e o pagamento** (alguém pegou a última vaga enquanto a pessoa
pagava): o pagamento **não se perde**. A sessão **não** entra na agenda (não lota por cima), a linha
fica **"sem vaga"**, o pedido mostra **Resolver:** no detalhe da venda, o aviso para `support@` chega
com "SEM VAGA", e o cliente lê que a equipe vai ligar para remarcar ou devolver. **Quem vende:** ligue,
remarque a sessão pela agenda (ou combine o reembolso no Stripe com o gerente) e anote na venda.

**Depósito de segurança:** cobrado no carrinho (Stripe) e na invoice do Aceitar e da venda automática
(QuickBooks), sempre que o serviço tem depósito em Serviços e preços. É devolvido em até 5 dias úteis
depois da sessão se não houver incidente: a devolução continua sendo feita pela equipe.

### 5.2 Achar um produto na loja do site e mandar o link ao cliente (#261)

Dono, 15/10: *"Busca e filtro na loja… Eu faço — confirma?"* → **"sim"**.

A loja do site novo (`/store/`) agora **acha produto**, do mesmo jeito que a loja de hoje:
busca por texto, filtro de preço, ordenação e páginas. Quem filtra é o **servidor** — a página já
chega pronta, então abre rápido até com internet ruim e **funciona sem JavaScript**.

**O caminho mais curto para mandar o link:**

1. Abra `/store/` e escreva no campo **What are you looking for?** o que o cliente pediu: o nome
   ("magnesium wheel set"), a marca ("OTK"), a peça ("axle") ou o **código do produto** (o SKU, por
   exemplo `MXCKIT`) — o código acha um só.
2. Precisa apertar o preço? **Min price** e **Max price** (em dólar). Quer ver do mais barato ao mais
   caro? **Sort by › Price: low to high**.
3. Achou: abra o produto e **copie o endereço da barra** (`…/store/p/<produto>/`). É esse o link que
   vai para o cliente, no WhatsApp ou no e-mail — ele abre direto na página de comprar.
4. Não achou nada? A loja diz isso e você continua: tire palavra ("magnesium wheel" em vez de
   "magnesium wheel set 130"), abra a faixa de preço, ou veja a **categoria** pelos botões
   (Chassis, Competition karts, Engines, Parts, Tires, Custom kart suits, Official URACE products,
   Programs). A busca também funciona **dentro** de uma categoria.

**O endereço serve de atalho** (dá para montar à mão e mandar):

| O que você quer | Endereço |
|---|---|
| buscar na loja | `/store/?s=magnesium+wheel+set` |
| buscar numa categoria | `/store/parts/?s=axle` |
| faixa de preço | `/store/?min_price=300&max_price=900` |
| do mais barato ao mais caro | `/store/?orderby=price` (ou `price-desc`, `date`) |
| a segunda página | `/store/page/2/` (a categoria também: `/store/parts/page/2/`) |

A página mostra quantos produtos existem ("Showing 1–24 of 70 products"): é o total que veio do
servidor, não um chute. São **24 por página**.

> **Cuidado ao mandar o link:** mande sempre o link **do produto** (`/store/p/…/`), não o link da
> sua busca. O link da busca é só seu (ele fica fora do Google de propósito) e amanhã pode trazer
> outro resultado. E o preço que vale é o que a página do produto mostra — ele vem do catálogo, nunca
> de uma tabela escrita à mão.

**O catálogo mudou?** Desde o #298 os produtos da loja ficam **no banco** e se mudam pelo painel (veja a
5.3). Os 70 produtos que vieram do WooCommerce entraram uma vez, como estavam.

### 5.3 Produtos da loja no painel: preço, fotos, texto, opções, frete, depósito e estoque (#298, #309)

Dono, 16/10: *"nos produtos da loja, colocar o valor de envio, o shipping … o valor do Security Deposit …
que eu consiga alterar … essas funções serão necessárias que sejam ativas permanentemente"*. Decisões:
frete = **valor fixo por produto**; no painel = **tudo do produto**.

**Onde:** Site › **Produtos da loja** (`/ops/site/produtos`). A lista é paginada (30 por
vez), com busca por nome, SKU ou endereço, filtro por categoria e "À venda / Escondidos". Cada produto
abre no próprio endereço (`/ops/site/produtos/<número>`). Ver é do operador; **mudar é do gerente**, e
toda mudança fica na auditoria.

| Campo | O que faz no site |
|---|---|
| **Nome** | o título do produto (em inglês: o cliente lê) |
| **Preço** e **Preço promocional** | o promocional (opcional) é o que se cobra; a loja mostra o cheio riscado. Preço 0 = "Ask for price" |
| **Frete por unidade (US$)** | cobrado no Stripe, numa linha **Shipping**, quando o cliente escolhe **Ship to me**: frete × quantidade. **Vazio** = como antes, a equipe combina e cobra à parte; **0** = frete grátis. Retirar na pista é sempre grátis |
| **Depósito de segurança por unidade (US$)** | vira a linha "Refundable security deposit" no Stripe; 0 = sem depósito |
| **Como vendemos** (#309) | **interno, o cliente nunca vê**: *Dropshipping (o fornecedor envia)*, o padrão de todos, ou *Em estoque (o box envia)*. Veja "Estoque do site", abaixo |
| **Em estoque** | sem estoque, a página diz "Out of stock" e o carrinho não vende. No produto **em estoque com item ligado**, a caixa fica só de leitura e mostra **quanto tem**: quem diz se tem é o estoque. Com opções, a caixa do produto vale para as opções **sem** item ligado (desmarcada, nenhuma delas vende); as ligadas seguem o estoque |
| **Categorias** | em que página da loja o produto aparece |
| **Fotos** | **Subir foto** (do celular ou do computador): sobe em WebP de até 1600 px, **sem a localização do celular**. A primeira é a da loja; ← → mudam a ordem; **Tirar** tira do produto |
| **Resumo** e **Descrição** | o texto da página, com negrito, itálico, lista e subtítulo. O que não for seguro (script, link estranho) o sistema tira ao salvar |
| **Opções (tamanho, cor…)** | cada opção com o seu preço, promocional e estoque; com duas escolhas, separe com " / " (ex.: *Blue / 2*). A loja mostra a faixa de preço |
| **Esconder da loja / Pôr à venda** | esconder **não apaga**: o produto sai da loja, do sitemap e do carrinho, e continua aqui para voltar |

**Produto novo:** em cima da lista (#312), **Novo produto** (nome, preço e categoria) cria o produto **escondido**
e abre a página dele: complete fotos, texto e frete e toque em **Pôr à venda**. O endereço
(`/store/p/<nome-do-produto>/`) sai do nome e não muda depois.

**Mudar o preço ou o frete** vale para as próximas compras; o pedido já feito fica com o valor do dia.
O pedido, o e-mail de confirmação, a página do pedido, a nota da venda e o recibo do QuickBooks (item
**Shipping**) mostram o frete cobrado. Quando parte do pedido tem frete e parte não, o e-mail diz o que já
foi pago e o que a equipe ainda combina.

> **Teste de checkout de US$ 1 na loja:** **Novo produto** com preço **1**, frete **0** e depósito **0**;
> ponha à venda, compre com "Ship to me" (o Stripe cobra US$ 1,00 de verdade) e **esconda o produto logo
> depois**; o estorno sai pelo Stripe.

#### Estoque do site: dropshipping ou em estoque, e quanto tem (#309)

Dono, 16/10: *"a gente seleciona o que que é dropshipping e o que que a gente tem em estoque para poder enviar. Um
marcador para isso lá, e o que tiver em estoque a gente coloca quanto que tem em estoque"*; *"não precisa ficar
aparente essa parte … para os clientes"*.

**Onde:** Site › **Estoque do site** (`/ops/site/estoque`). Um cartão por produto, com o marcador em cima, quanto tem
agora (a soma) e cada opção (tamanho, cor…) com o item do Estoque ligado e **quanto tem em cada local**: *Galpão 5 ·
Pista 3*. Filtros: **Em estoque**, **Dropshipping**, **Em estoque sem item ligado** (falta ligar) e **Sem saldo**
(ligado, mas acabou: o site já mostra "Out of stock"). Busca por nome, SKU ou endereço; a lista é paginada no servidor.
Os links **Estoque do site** e **Ligar em Estoque do site** do produto (Site › Produtos da loja) abrem a lista já
filtrada nele (`/ops/site/estoque/<endereço do produto>`).

| Marcador | Quem envia | O que o site mostra |
|---|---|---|
| **Dropshipping** (o padrão dos 70 produtos) | o fornecedor | segue a caixa **Em estoque** do produto, como antes |
| **Em estoque** | o box | com item ligado, **o estoque diz**: tem pelo menos 1 no Galpão + Pista, vende; zero, "Out of stock" (a opção sem saldo fica desativada). Sem item ligado ainda, segue a caixa |

**Um saldo só.** O produto em estoque (ou cada tamanho dele) liga a **um item do Estoque** do box: o mesmo número do
Balcão, da contagem e de Compras (receber a compra dá entrada). Conta o que é **da URACE** no **Galpão** e na **Pista**;
o trailer de corrida fica fora, e peça de cliente guardada nunca vai para o site. Um item vende no site por um produto
só.

**Passo a passo (gerente):**
1. No cartão, **Passar a em estoque** (ou, no produto, *Como vendemos* → *Em estoque*). O painel pergunta antes,
   dizendo o que muda no site; **Cancelar** não muda nada.
2. Em cada opção, **Ligar**: escolha o **item do estoque** (a lista sugere pelo nome do produto, 12 por página, com
   *Anteriores* e *Próximas*; o item que já vende por outro produto aparece desligado; uma busca nova solta o item
   escolhido, para nada ser ligado sem estar na tela) ou **Criar item** a partir do produto (nome, prateleira, tamanho
   e o preço do Balcão, opcional: o preço do site continua no produto).
3. **A contagem é de um local só.** Escolha **Onde** (Galpão ou Pista) e preencha **Quanto tem no Galpão agora** (ou
   *na Pista*) com o que tem **naquele local**, nunca a soma dos dois: a lista mostra cada local (*Galpão 5 · Pista
   3*). Item **novo** (Criar item) ou que **nunca foi contado**: a contagem é obrigatória (ligar sem contar mostraria
   "Out of stock"). Item que **já tem saldo**: o campo já vem com o saldo do local escolhido e é **opcional**; deixe
   como está e toque em **Ligar** (o saldo não muda), ou mude só se acabou de contar aquele local. Kart usado e motor
   (número de série) contam as unidades, uma a uma, pelo Estoque.
4. Depois, **Contar** (operador também) acerta o saldo de **um local** quando a mão contar de novo: o campo vem com o
   saldo do local escolhido. **Desligar do produto** (gerente) tira a ligação sem mexer no item, no saldo nem no
   histórico.
5. **Mudar o nome de uma opção** ligada (em Site › Produtos da loja, *M* vira *Medium*) leva a ligação junto: a opção
   continua vendendo só o que o box tem. Se o sistema não souber qual opção virou qual (o nome de várias mudou de uma
   vez por outro caminho que não a tela), ele recusa e diz o que fazer: mude uma por vez, ou desligue antes. **Tirar**
   uma opção ligada, ou dar opções a um produto ligado inteiro, também pede **desligar antes** (a ligação ficaria
   solta e prenderia o item, que vende por um produto só).
6. **Passar a dropshipping** um produto que ainda tem ligação: o cartão continua mostrando o item ligado, com
   **Desligar**. Até desligar, o item não liga a outro produto (no Ligar ele aparece *ligado a X (dropshipping)*).

**A venda paga sai do estoque sozinha.** No pagamento (o aviso do Stripe ou a página de obrigado, o que chegar
primeiro), o produto em estoque sai do item ligado, uma vez só (*venda · site*, com o número do pedido no histórico):
**Ship to me** sai primeiro do Galpão; **retirada** sai primeiro da Pista. O razão do estoque continua batendo. O que
saiu aparece no pedido em Site › Pedidos do site (**Estoque:** *baixou 1 do estoque (Galpão 1)*), no e-mail da equipe e
na venda; no kart usado e no motor, com o **serial** da unidade que saiu (*série: SN-…*): separe exatamente essa.

**Sem saldo na hora de pagar** (duas pessoas pagaram a última unidade, o Balcão vendeu antes, a contagem estava
errada): o pagamento **não cai**. Sai o que tinha e o pedido fica com **"Resolver: sem estoque: … pediu 2, tinha 1"** em
Site › Pedidos do site, no e-mail da equipe (*· SEM ESTOQUE* no assunto) e no Painel do site (*Pagos sem estoque*).
Separe o que tem, confira a prateleira, conte e combine com o cliente (prazo ou devolução pelo Stripe). Resolvido, toque
em **Resolvido** no pedido (operador também): o "sem estoque" sai do *Resolver* do pedido e do *Pagos sem estoque* do
Painel do site; a frase continua na linha do pedido e na auditoria (`store.stock.resolved`). Saldo com fração (0,5 no
Galpão + 0,5 na Pista) vende 1 no site e a baixa tira 0,5 de cada local.

**O cliente nunca vê** o marcador nem a quantidade: só "Out of stock" quando acaba. Se ele pedir mais do que o box tem,
o carrinho e o Buy now dizem *"We don't have that many in stock right now…"*, sem o número; no carrinho, a frase sai
em **todas** as linhas daquele produto e opção (somadas), para o carrinho não mostrar onde o saldo acaba. Com produto
em estoque, o checkout do Stripe vale 31 minutos (a última unidade não fica presa num checkout esquecido).

**Não faz:** pedido sozinho em Compras quando o dropshipping vende (a equipe pede ao fornecedor como antes); devolver ao
estoque quando há estorno no Stripe (dê **entrada** com o motivo "devolução" no Estoque).

### Contas de clientes (Site › Contas de clientes)

Quem cria conta no site precisa estar ligado ao card certo. Cada driver tem o seu card.

Cada conta é um cartão do padrão D (#313): **vinculada** (verde) ou **sem vínculo** (amarelo) em cima, as iniciais, o
nome, o e-mail e o telefone. A lista mostra os **pilotos**, a **sugestão** do painel (com o motivo: mesmo e-mail,
telefone…) ou o card já ligado. Embaixo: **Vincular a este** (a sugestão) ou **Criar cliente** (sem sugestão); para
outro card, escolha em **Outro cliente** e toque em **Vincular**. Na conta ligada, os drivers ficam numa lista, cada um
com a ação na linha (**Vincular a este**, **Criar card**, **Desvincular**).

| Ação | Rota | Papel |
|---|---|---|
| ligar a conta a um card | `POST /site/contas/{conta}/vincular` | Operador |
| ligar um driver a um card | `POST /site/drivers/{driver}/vincular` | Operador |
| criar card para a conta | `POST /site/contas/{conta}/criar-cliente` | Operador (recusa se já existe cliente com o mesmo e-mail ou telefone) |
| criar card para um driver | `POST /site/drivers/{driver}/criar-cliente` | Operador (recusa se já existe card com o nome do driver: vincule a ele. O e-mail repetido dos irmãos não bloqueia) |
| desligar | `…/desvincular` | Gerente |

### 5.4 Security deposit: devolver pelo Stripe e mudar o valor cobrado (#317)

Dono, 16/10: *"fazer o reembolso de cada security deposit e alterar o valor do security deposit para ser cobrado no
site … só clicar no botão e fazer o refund … Sempre conseguindo alterar o valor que vai ser reembolsado."*

**Onde:** Site › **Security deposit** (`/ops/site/deposito`). Ver é do Operador; devolver, conferir e mudar o valor
são do Gerente.

**Devolver um depósito (passo a passo):**

1. Filtro **Retidos** (o padrão). Ache o cliente pelo nome, e-mail, piloto ou nº do pedido.
2. No cartão, confira a sessão, o piloto e o que **segue retido**.
3. Em **Valor a devolver**, deixe o total ou escreva só uma parte. Por exemplo, devolve 300 e segura 100 de um dano
   pequeno. Escreva o **motivo** (opcional; fica na auditoria e no cartão).
4. **Devolver pelo Stripe** → confirme. O Stripe devolve no cartão que pagou. Não dá para desfazer.
5. O cartão passa a **Devolvido em parte** ou **Devolvido**, com quem devolveu e quando.

Regras:

- Parcial vale, e mais de uma vez no mesmo depósito. Nunca passa do que segue retido.
- Dois cliques, ou duas pessoas ao mesmo tempo, **não** devolvem duas vezes.
- **"Devolução pendente":** a resposta do Stripe não chegou. O valor fica reservado. Toque em **Conferir no
  Stripe** depois de alguns minutos: ele acerta sozinho, ou devolve o valor ao "retido" se nada chegou ao Stripe.
- **Conferir no Stripe** mostra também quanto o pagamento já teve devolvido no total, inclusive o que alguém devolveu
  direto no painel do Stripe. Isso **não** é descontado do depósito: confira antes de devolver de novo.
- Só o que foi pago no site (carrinho ou Buy now) aparece aqui. Depósito cobrado em invoice do QuickBooks é
  devolvido no QuickBooks, como sempre.
- O QuickBooks não muda sozinho com a devolução do Stripe.
- Stripe em **modo teste** (chave de teste): a tela avisa e nada de dinheiro de verdade sai.

**Mudar o valor cobrado no site** (em cima, em **Valor cobrado no site**):

- Cada sessão (serviço) e cada produto com depósito têm o seu valor. Mude e toque em **Salvar**. Vale para as
  **próximas** compras; o pedido já pago fica com o valor do dia.
- Para testar o checkout com valor baixo: ponha **1**, teste, e **volte ao valor normal** (ex.: 400). Para testar
  **sem** depósito (o teste de US$ 1 do dia 16/10), desmarque **Obrigatório** antes de zerar, e marque de novo depois.
- **Obrigatório** (também em Serviços e preços, como **Security deposit obrigatório**): marcado, a sessão nunca sai sem
  o depósito. O serviço não salva com o depósito zerado, o carrinho recusa a sessão ("This session can't be paid
  online right now") e a invoice da equipe não sai. Serviço novo já nasce com a caixa marcada e pede o valor.

| Ação | Rota | Papel |
|---|---|---|
| ver os depósitos (paginado) | `GET /site/depositos?estado=retidos\|devolvidos\|todos&q=` | Operador |
| devolver | `POST /site/depositos/{pedido}/reembolsar` (`item_id`, `valor`, `nota`) | Gerente |
| conferir no Stripe | `POST /site/depositos/{pedido}/conferir` | Gerente |
| valor cobrado | `GET /site/depositos/valores` · `PATCH /site/depositos/valor` (`tipo`, `id`, `valor`, `obrigatorio`) | Gerente para mudar |

---

## 6. CRM (Kommo) e o Robô SDR

### O chat do Kommo no painel (`/ops/crm/chat`)

| Para | Botão | Rota | Papel |
|---|---|---|---|
| ver as conversas (mais recente no topo; ● espera resposta) | — | `GET /crm/inbox` | todos |
| ver tudo do lead | Dados do lead | `GET /crm/leads/{id}/detail` | todos |
| responder no canal do lead | **Enviar no chat** | `POST /crm/leads/{id}/reply` | Operador |
| anotar (não vai para o cliente) | **Anotar no lead** | `POST /crm/leads/{id}/note` | Operador |
| marcar tag | **+ tag** | `POST /crm/leads/{id}/tags` | Operador |
| mudar etapa (move no Kommo) | Etapa no funil | `POST /crm/leads/{id}/stage` | Operador |
| ligar ao card do cliente | — | `POST /crm/leads/{id}/link` | Operador |
| virar oportunidade | **Passar para vendas** | `POST /sales/from-lead/{id}` | Operador |
| sincronizar o Kommo | Sincronizar | `POST /crm/sync` | Gerente |

O `{id}` dessas rotas é o número do lead **no painel**, não o id do Kommo.

Como a resposta sai: pelo bot da conta no canal do lead, **como mensagem do bot**, com o seu texto
(limite do Kommo). Se o bot não está esperando, a mensagem entra na fila e o painel insiste a cada
meio minuto. Se em 15 minutos não sair, vira nota no lead e acende o aviso. O que o lead escreveu
antes de o chat ser ligado fica só no Kommo.

**Regra para o Claude:** pelo MCP, toda escrita em `/crm/…` (responder, anotar, etapa, tags,
ligar ao card) pede `confirmar` (#204), como o resto do que vai para o Kommo. O Claude **só responde
ao lead com o texto que a pessoa aprovou, palavra por palavra**, e só move etapa ou marca tag depois
de a pessoa dizer qual.

### O Robô SDR (`/ops/sdr`)

O robô de vendas no Kommo. Três níveis:

| Nível | Lê | Escreve no Kommo (etapa, tag, nota, tarefa) | Responde ao lead |
|---|---|---|---|
| **Observar** | sim | não: só registra o que faria | não |
| **Organizar** | sim | sim | não: gente responde |
| **Atender** | sim | sim | sim |

| O quê | Quem |
|---|---|
| ver o nível, as instruções, os relatos e as decisões do robô | todos |
| **relatar** um erro do robô ("o robô respondeu errado", "preço errado", "ignorou o lead", "outro") | **qualquer pessoa logada** (`POST /sdr/relatos`) |
| escrever ou arquivar uma **instrução** para o robô | Gerente (`POST /sdr/instrucoes`) |
| resolver um relato | Gerente |
| **mudar o nível** | **só Administrador** (`PUT /sdr`) |

- Instrução vale acima da persona do robô, com duas exceções fixas: **o preço vem da tabela** e as
  **travas de segurança**. Instrução não muda preço.
- Horário de atendimento humano mostrado no painel: seg–sex, 8h–18h (Orlando).
- Viu o robô errar? Relate com o lead (id ou nome) e o que aconteceu. Quem cuida do robô resolve.

---

## 7. Suits (macacão)

O guia completo é [`docs/suits-guia-do-lucas.md`](../suits-guia-do-lucas.md). Para venda, só isto:

- Pedido de macacão vive em **Suits · Alpha Line** (`/ops/suits`), Operador ou acima.
- **"Não é pedido de suit"** (#195): tira das listas e da ponte de e-mail um pedido que não é de
  macacão (`POST /suits/{id}/descartar`, motivo opcional). Nada é apagado: dá para restaurar em
  Descartados.
- **"IA neste pedido"** (#198, entregue em 13/10): chave no topo do pedido
  (`POST /suits/{id}/ia` com `{"ligada": false}`). Desligada, a IA não responde, não manda e-mail e
  não altera nada naquele pedido; e-mail novo aparece na linha do tempo para a equipe.

---

## 8. Tabela de operações para a IA

### Como chamar

```
urace_api(metodo="POST", caminho="/ops/api/sales/{id}/call", corpo={...})
```

- Troque `{id}` pelo número. Parâmetros de busca vão em `consulta`, nunca na URL.
- **Confirmação** (coluna "Confirma"): a primeira chamada **não executa**. Ela devolve
  `precisa_confirmar: true` e o que vai fazer. Mostre à pessoa (para quem, quanto, qual modelo,
  qual data), espere o "pode mandar" e chame de novo, igual, com `confirmar: true`.
- Papel insuficiente: a resposta diz "isto é do papel MANAGER ou acima". Não tente outro caminho:
  avise a pessoa.
- **Datas:** o painel mostra tudo no fuso da Flórida, mas `proximo_em` e `quando` vão em **UTC com
  "Z"**. Converta: Flórida = UTC−4 até 31/10/2026 e UTC−5 a partir de 01/11/2026.
  Exemplo: 20/10/2026 às 10h na Flórida = `2026-10-20T14:00:00Z`.
- `service_date` e `due_on` são só a data: `AAAA-MM-DD`.

Os corpos abaixo são **exemplos fictícios**. Não copie nomes nem e-mails daqui para um registro real.

### Ler

| Para | Método e caminho | Exemplo | Papel |
|---|---|---|---|
| achar cliente | `GET /ops/api/clients` | consulta `{"q": "sobrenome"}` | todos |
| ficha do cliente | `GET /ops/api/clients/{id}` | — (invoices só aparecem para gerente e acima) | todos |
| quadro de vendas | `GET /ops/api/sales/board` | consulta `{"minhas": true}` | todos |
| agenda de retornos | `GET /ops/api/sales/agenda` | consulta `{"minhas": true}` | todos |
| uma oportunidade | `GET /ops/api/sales/{id}` | — (olhe `oportunidade.closing`; venda do site: `pedido` traz as linhas, `pedido.atencao` o que resolver) | todos |
| pedidos do site | `GET /ops/api/site/agendamentos` | consulta `{"status": "pendente"}` | Operador |
| serviços e preços do site | `GET /ops/api/site/servicos` | — | Operador |
| estoque do site (marcador, item ligado, quanto tem) | `GET /ops/api/site/estoque` | `q`, `modo` (todos · estoque · dropshipping · sem_item · sem_saldo), `limit`/`offset` | Operador |
| produtos da loja (preço, frete, depósito, estoque) | `GET /ops/api/site/produtos` · `GET /ops/api/site/produtos/{id}` | `q`, `categoria`, `estado` (ativos · escondidos), `limit`/`offset` | Operador (mudar: Gerente, `PATCH /ops/api/site/produtos/{id}`) |
| conversas do Kommo | `GET /ops/api/crm/inbox` | — | todos |
| waivers | `GET /ops/api/waivers` | — | todos |
| estado do robô SDR | `GET /ops/api/sdr/painel` | — | todos |
| o seu Google Calendar conectado? | `GET /ops/api/google/status` | — | Operador |
| os seus compromissos do Google | `GET /ops/api/google/events` | consulta `{"de": "2026-10-20", "ate": "2026-10-27"}` (dias da Flórida, até 62) | Operador |

### Fazer

| Para | Método e caminho | Corpo de exemplo (fictício) | Papel | Confirma |
|---|---|---|---|---|
| criar cliente | `POST /ops/api/clients` | `{"name": "Responsável Exemplo", "pilot_name": "Piloto Exemplo", "pilot_dob": "2014-05-10", "email": "cliente@exemplo.com", "phone": "+1 407 555 0100"}` | Operador | não |
| abrir oportunidade | `POST /ops/api/sales` | `{"name": "Responsável Exemplo", "email": "cliente@exemplo.com", "phone": "+1 407 555 0100", "pilot_name": "Piloto Exemplo", "pilot_age": 12, "service": "Test Drive", "source": "Ligação", "client_id": 123}` | Operador | não |
| oportunidade a partir do lead | `POST /ops/api/sales/from-lead/{lead}` | — | Operador | não |
| editar a ficha | `PATCH /ops/api/sales/{id}` | `{"name": "Responsável Exemplo", "pilot_age": 12}` (`name` é obrigatório) | Operador | não |
| registrar ligação | `POST /ops/api/sales/{id}/call` | `{"resultado": "pensar", "minutos": 6, "texto": "vai falar com a família", "proximo_em": "2026-10-20T14:00:00Z", "proximo_que": "confirmar a data"}` | Operador | não |
| marcar retorno | `POST /ops/api/sales/{id}/next` | `{"quando": "2026-10-20T14:00:00Z", "o_que": "retorno"}` | Operador | não |
| anotar | `POST /ops/api/sales/{id}/note` | `{"texto": "prefere manhã de sábado"}` | Operador | não |
| mover etapa | `POST /ops/api/sales/{id}/stage` | `{"etapa": "PROPOSTA"}` ou `{"etapa": "PERDIDO", "motivo": "distância"}` | Operador | não |
| itens do catálogo (preço da tabela) | `GET /ops/api/sales/catalogo` | consulta `{"q": "daily"}` | todos | não |
| **fechar a venda** | `POST /ops/api/sales/{id}/close` | `{"service": "Test Drive", "service_date": "2026-10-24", "service_time": "09:00", "amount": 0, "item_id": "id do item do catálogo", "pilot_name": "Piloto Exemplo", "pilot_age": 12, "email": "cliente@exemplo.com", "irmao": false, "passos": {"cliente": true, "qbo": true, "waiver": true, "asana": true, "kommo": false}, "extras": [{"titulo": "avisar o instrutor", "onde": "painel", "quando": "2026-10-23"}]}` (`0` = troque pelo valor real; o preço da tabela vem do item) | Operador | **sim** |
| refazer um passo | `POST /ops/api/sales/{id}/step/{passo}` | — (`passo`: cliente, qbo, waiver, asana, kommo; só depois de fechar; `cliente` aceita a consulta `{"irmao": true}`; `qbo` aceita `{"item_id": "id do item"}` e, só o gerente, `{"confirmar": true}` para a tentativa que não terminou) | Operador | **sim** |
| cobrar só o depósito | `POST /ops/api/sales/{id}/deposit` | — (consulta `{"confirmar": true}` só para a tentativa que não terminou, gerente) | Operador | **sim** |
| liberar invoice fora da tabela | `POST /ops/api/sales/{id}/invoice/liberar` | `{"valor": 0}` (o valor da venda, conferido; opcionais `"item_id"` e `"confirmar": true`) | **Gerente** | **sim** |
| reenviar a invoice criada cujo envio falhou (a mesma) | `POST /ops/api/sales/{id}/invoice/reenviar` | `{"invoice": "id no QuickBooks"}` | Operador | **sim** |
| a invoice saiu: registrar o número (tentativa que não terminou) | `POST /ops/api/sales/{id}/invoice/registrar` | `{"numero": "Invoice no."}` (depois do aviso de valor, `"aceitar_diferenca": true`) | **Gerente** | **sim** |
| card de irmão | `POST /ops/api/clients` | `{"name": "Responsável Exemplo", "pilot_name": "Irmão Exemplo", "pilot_dob": "2016-05-09", "irmao_de": 123}` | Operador | não |
| tarefa de serviço no Asana (modelo oficial) | `POST /ops/api/tasks` | `{"client_id": 123, "pilot_name": "Piloto Exemplo", "responsible": "Responsável Exemplo", "email": "cliente@exemplo.com", "phone": "+1 407 555 0100", "dob": "2014-05-10", "product": "Test Drive", "category": "4 stroke", "due_on": "2026-10-24"}` | Operador | **sim** |
| enviar waiver avulsa | `POST /ops/api/waivers/send` | `{"template": "parental", "signer_name": "Responsável Exemplo", "signer_email": "cliente@exemplo.com", "service": "Test Drive", "client_id": 123}` | Operador | **sim** |
| reenviar waiver (corrigir e-mail) | `POST /ops/api/waivers/{id}/resend` | `{"email": "novo@exemplo.com"}` | Operador | **sim** |
| aceitar pedido do site | `POST /ops/api/site/agendamentos/{id}/aceitar` | `{}` | Operador | **sim** |
| recusar pedido do site | `POST /ops/api/site/agendamentos/{id}/recusar` | `{"nota": "texto que o cliente vai ler"}` | Operador | **sim** |
| cancelar sessão | `POST /ops/api/site/agendamentos/{id}/cancelar` | `{"nota": "…"}` | Operador | **sim** |
| confirmar sem pagamento e waiver | `POST /ops/api/site/agendamentos/{id}/confirmar` | `{}` | **Gerente** | **sim** |
| contar o item ligado a um produto do site | `POST /ops/api/site/estoque/{produto}/contar` | `{"variacao": "M", "qty": 3, "local": "sede"}` | Operador | **sim** |
| ligar produto (ou opção) ao estoque | `POST /ops/api/site/estoque/{produto}/ligar` | `{"variacao": "", "item_id": 12, "contagem": 2, "local": "pista"}` (`contagem` é o que tem **naquele local**; opcional se o item já tem saldo) | **Gerente** | **sim** |
| marcar "sem estoque" do pedido como resolvido | `POST /ops/api/site/pedidos/{id}/estoque-resolvido` | `{}` | Operador | **sim** |
| responder lead no Kommo | `POST /ops/api/crm/leads/{id}/reply` | `{"text": "texto aprovado pela pessoa"}` | Operador | **sim** |
| mover etapa no Kommo | `POST /ops/api/crm/leads/{id}/stage` | `{"stage_id": "…"}` | Operador | **sim** |
| marcar tag no Kommo | `POST /ops/api/crm/leads/{id}/tags` | `{"tags": ["…"]}` | Operador | **sim** |
| anotar no lead | `POST /ops/api/crm/leads/{id}/note` | `{"text": "…"}` | Operador | **sim** |
| ligar lead ao card | `POST /ops/api/crm/leads/{id}/link` | `{"client_id": 123}` | Operador | **sim** |
| relatar erro do robô | `POST /ops/api/sdr/relatos` | `{"tipo": "respondeu_errado", "texto": "…", "lead_ref": "id do lead"}` | todos | não |
| IA num pedido de suit | `POST /ops/api/suits/{id}/ia` | `{"ligada": false}` | Operador | não |
| acertar agora os retornos no Google da pessoa | `POST /ops/api/google/sync` | — | Operador | não |

Conectar e desconectar o Google Calendar (`/ops/api/google/connect`, `/disconnect`) **não** são da
IA: é a pessoa, no navegador (seção 4.8).

`product` aceita: Urace Daily, Lead and Follow, Academy, Corrida, Arrive and Drive, Summer Camp,
Test Drive. `category` aceita: Using Own Kart, Baby Kart, 4 stroke, 2 stroke, Adult Shifter, F4.
A data não pode cair numa segunda-feira (o quadro não tem coluna).

### Só gerente ou administrador

| O quê | Papel |
|---|---|
| confirmar pedido do site sem pagamento e waiver | Gerente |
| mudar preço, depósito ou item do QuickBooks de um serviço do site | Gerente |
| mudar o marcador da loja (dropshipping · em estoque), ligar e desligar produto ao estoque | Gerente |
| abrir e fechar a agenda, bloquear datas, "Confirmar sozinho" | Gerente |
| ver invoices e QuickBooks | Gerente |
| aprovar invoice proposta pela IA; **Liberar invoice** fora da tabela ou sem preço de tabela | Gerente / dono |
| mover serviço de um card para outro | Gerente |
| instruções do robô SDR, resolver relato | Gerente |
| ligar a venda automática, mudar o nível do robô SDR | Administrador |

---

## 9. Roteiros prontos

### R1. Lead do Kommo quer marcar

1. No chat, leia a conversa (`GET /crm/leads/{id}`).
2. **Passar para vendas** (`POST /sales/from-lead/{id}`).
3. Busque o cliente (seção 3). Se já existe, edite a ficha com o `client_id`.
4. Pergunte o que falta: piloto, **idade**, e-mail, serviço, data.
5. Confira o preço na tabela.
6. Registre a ligação ou a conversa (`call` com `fechou` quando fechar).
7. **Fechar venda**, com o **item do catálogo** e o passo Kommo ligado. Confirme com a pessoa.
8. Veja o acompanhamento: tudo "feito"? Responda ao lead (texto aprovado) dizendo que a invoice e a
   waiver estão no e-mail.

### R2. Ligação de alguém novo

1. **Nova oportunidade** com o nome (só ele é obrigatório) e origem "Ligação".
2. Dite o que a pessoa falou.
3. **Registrar ligação** com o resultado e o retorno.
4. Vai pensar? O retorno aparece na Agenda de vendas no dia marcado.

### R3. Cliente que já é da casa quer outro serviço

1. Ache o card (seção 3).
2. **Nova oportunidade › Vincular ao cliente**: os dados vêm do cadastro e o fechamento cai nesse card.
3. Confira se a waiver do piloto ainda vale (1 ano da assinatura). Se vale, desligue o passo Waiver.
4. Feche com o item do catálogo. Fora da tabela, a invoice espera o gerente.

### R3b. Irmão de quem já é cliente

1. Ache o card do irmão (seção 3).
2. **Clientes › + Novo cliente › "É irmão de um cliente?"** (ou no card do irmão, **⋯ › + Card de
   irmão**). Em "Irmão de — vincular ao cliente", escolha o card do irmão; escreva o piloto.
3. Abra a oportunidade com **Vincular ao cliente** no card novo. Ou, no Fechar venda, deixe marcado
   **"É irmão: criar o card de …"** quando a tela avisar que o card do contato é de outro piloto.

### R4. Piloto menor de idade, ou adulto que não é quem paga

- **Menor:** preencha a idade. Nome e e-mail da ficha são do **responsável**. O Fechar venda manda
  a waiver **parental** para o responsável.
- **Adulto que não é o responsável:** no Fechar venda, **desligue o passo Waiver**. Depois envie a
  avulsa para o piloto: `POST /waivers/send` com `template: "adult"`, nome e e-mail **do piloto** e
  `client_id` do card do piloto.

### R5. Pedidos do site esperando

1. `GET /site/agendamentos` com `status: pendente` (ou o item "sessão(ões) pedida(s) pelo site
   esperando confirmação" em Precisa de atenção).
2. Para cada um: piloto com card? Idade? Serviço e preço certos?
3. **Aceitar**. A tela diz: "Aceita: invoice e waiver enviadas", "Aceita e já confirmada (contrato +
   waiver em dia)" ou "Aceita, mas falta resolver: veja no agendamento".
4. Faltou algo? Leia o erro escrito no agendamento e use a seção 11.
5. Não dá para atender a data? **Recusar** com nota para o cliente.

### R6. A venda fechou, mas faltou um passo

1. `GET /sales/{id}` e leia `oportunidade.closing.passos`.
2. Para cada passo com `ok: false`, corrija a causa (e-mail, integração) e use **tentar de novo**
   (`step/{passo}`). Invoice que falhou por "o serviço não tem item no catálogo": o **tentar de novo**
   pede o item (`step/qbo?item_id=…`). Invoice desligada no fechamento com o valor da tabela:
   **mandar a invoice**.
3. Passo com `ok: null` e "invoice esperando o gerente conferir o valor": não refaça. Avise a
   gerência; ela usa **Liberar invoice** (seção 4.6.1).
4. Faltou o depósito? **Cobrar só o depósito** (seção 4.6.2).
5. Nunca chame `close` de novo numa venda que já tem `closing`. Se a invoice ou o depósito já saiu, o
   sistema recusa (409 "Venda já fechada…").
6. 409 "A tentativa de … não terminou: confira no QuickBooks se a invoice saiu": é da gerência
   (seção 4.6.3: "Não saiu: mandar" ou "Saiu: registrar o número").
7. "Invoice nº … criada, o envio falhou": **Reenviar** (seção 4.6.4), nunca o passo.

### R7. Waiver voltou ou foi para o e-mail errado

1. Ache a waiver (`GET /waivers` ou a ficha do cliente).
2. `POST /waivers/{id}/resend` com o e-mail certo. O painel corrige o signatário e reenvia.
3. Assinada na área do cliente não tem envelope: não se reenvia.

### R8. A pessoa desistiu

`POST /sales/{id}/stage` com `{"etapa": "PERDIDO", "motivo": "…"}`. Sem motivo o painel recusa.

### R9. O robô SDR respondeu errado

Robô SDR › **Relatar**, com o tipo, o que aconteceu e o lead. Para mudar o comportamento, peça uma
instrução à gerência.

### R10. Abertura do dia de vendas

1. Agenda de vendas: retornos de hoje e atrasados.
2. Chat do Kommo: conversas com ●.
3. Site › Agendamentos › Esperando confirmação.
4. Precisa de atenção: retorno de venda atrasado, ligação perdida, waiver parada, pedido do site,
   invoice de venda esperando o gerente.

### Frases para dizer ao seu Claude

| Você diz | O Claude faz |
|---|---|
| "Quais retornos eu tenho hoje?" | `GET /sales/agenda` com `minhas` |
| "Abre uma oportunidade para [nome], veio do Instagram, piloto de 12 anos" | busca o cliente; cria a oportunidade |
| "Registra que a pessoa vai pensar e me lembra quinta às 10h" | `call` com `pensar` e `proximo_em` em UTC |
| "Fecha a venda da oportunidade 45: Test Drive, dia 24, preço da tabela" | lê a ficha, confere idade e e-mail, monta o fechamento, mostra e espera o "pode mandar" |
| "O que faltou no fechamento da 45?" | lê `closing.passos` e diz o que falhou e por quê |
| "Reenvia a waiver da 45" | `step/waiver`, mostra e espera o "pode mandar" |
| "Tem pedido do site esperando?" | `GET /site/agendamentos` com `pendente` |
| "Aceita o pedido 12" | mostra o que vai sair (invoice, depósito, waiver) e espera o "pode mandar" |
| "Passa o lead da conversa com [nome] para vendas" | acha o lead no inbox e chama `from-lead` |
| "Responde no chat: [texto]" | mostra o texto exato e só envia depois do "pode mandar" |

---

## 10. Regras que nunca mudam

| Regra | Na prática |
|---|---|
| **Não cobrar duas vezes** | antes de fechar, olhe `closing`; `step/qbo` só para passo que falhou; agendamento com invoice não gera outra; o depósito sai uma vez por venda (`closing.deposito_cobrado`). O sistema trava (#310): invoice que já saiu (ou venda paga no site, no Stripe) não sai de novo pelo passo, pelo Liberar nem pela IA; fechar de novo é recusado; duas saídas ao mesmo tempo (botão, API, MCP, IA) mandam uma só; a tentativa que não terminou só passa com o gerente conferindo no QuickBooks |
| **Invoice fora da tabela só com o gerente** | o preço da tabela vem do catálogo; fora dela (ou sem preço), quem libera é o gerente ou o dono, vendo o valor |
| **Nunca serviço de um cliente no card de outro** | confira o piloto do card antes de vincular; irmão tem card próprio (card de irmão); mover serviço é da gerência |
| **NO FAKE DATA** | não invente nome, e-mail, idade, data, preço. Faltou, pergunte. Ausência é informação |
| **Preço e prazo só do sistema** | Rate Card, Serviços e preços, ou o dono. Não prometa data, vaga, desconto ou condição que o painel não mostre. O robô SDR não diz "reserva confirmada" nem "garanto sua vaga" |
| **Nunca pedir senha no chat** | nem senha, token, PIN ou chave. O login é pelo navegador |
| **Fuso da Flórida** | tudo em America/New_York; na API, UTC com "Z" |
| **Não usar Turo nem Hostaway** | para nada |
| **O que vai para fora espera a pessoa** | invoice, waiver, e-mail, Asana, aceitar pedido: `confirmar=true` só depois do "pode mandar" |
| **Waiver certa** | idade decide o modelo; o signatário é o responsável (menor) ou o próprio piloto (adulto); `delivered` não é assinada |
| **Tudo fica na auditoria** | com o seu nome. Não há como apagar |

---

## 11. Quando algo dá errado

| Sintoma (o que aparece) | O que fazer |
|---|---|
| "este acesso é só de leitura" | conecte o Claude de novo e marque **"Também operar o painel como você"** |
| "isto é do papel MANAGER ou acima; você é OPERATOR" | é da gerência: peça a quem tem esse papel |
| "… não existe no painel (veja urace_operacoes)" | caminho errado: rode `urace_operacoes` com uma palavra-chave |
| "caminho inválido: passe a consulta em 'consulta'" | tire o `?…` da URL e mande em `consulta` |
| "Para fechar, diga o serviço e o valor." | preencha serviço e valor |
| Venda do site com **Resolver:** "a vaga sumiu entre o checkout e o pagamento" | o cliente já pagou: ligue, remarque a sessão (ou combine o reembolso com o gerente) e anote na venda (seção 5.1) |
| Venda do site em **Fechamento** com "vincular à mão" | pago no carrinho sem card certo: ache o card (seção 3) e ligue a venda a ele |
| E-mail "Site · PAGAMENTO FALHOU: pedido #N" | o meio de pagamento que confirma depois não passou; nada foi cobrado e a vaga está livre. Site › Pedidos do site › **Copiar o link** e mande ao cliente (ele toca em **Try again**); sem e-mail no Stripe, ligue (seção 5.1) |
| Cliente diz "o site não deixa comprar sem conta" | regra do dono (#248): toda compra no site pede a conta. No **carrinho**, ele preenche os dados e a senha ali mesmo e a conta nasce no Checkout (#305); no **Buy now** da loja, o botão **Create account** leva e volta para o produto |
| Carrinho diz "An account with this email already exists" | o e-mail já tem conta: ele toca em **Sign in** (no próprio aviso) e volta ao carrinho logado; esqueceu a senha, *Forgot password?* |
| Cliente diz "não recebi a senha" / "não recebi o número de cliente" | a senha vai no e-mail de boas-vindas (procure no spam: *Welcome to URACE*); o número de cliente chega num **segundo** e-mail quando o card do piloto nasce (no pagamento). Sem e-mail nenhum: *Forgot password?* na área do cliente manda o link para criar outra |
| Cliente diz "recebo e-mail todo dia para completar o piloto" | é o lembrete do #305 (sessão paga com o piloto incompleto): para assim que ele completa as medidas e a experiência em *Drivers*, ou depois de 7 lembretes |
| Cliente pergunta "e o meu pedido?" | Site › Pedidos do site: ache pelo nome ou e-mail, veja o estado e mande o link da **Página do pedido** |
| "QuickBooks: registrar a venda à mão" numa venda do site | o serviço não tem item do QuickBooks ou o item "Security deposit" não está sincronizado: acerte em Serviços e preços / sincronize; a rodada de 15 min tenta de novo |
| "Ganho é o resultado do Fechar venda…" | use Fechar venda, não o botão de etapa |
| "Perdido exige motivo." | mande `motivo` |
| "Cliente não existe." | o `client_id` está errado: busque de novo |
| Waiver: "sem e-mail do responsável" | complete o e-mail na ficha e use **tentar de novo** |
| Waiver: "e-mail do domínio da URACE não é de cliente" | troque pelo e-mail do cliente |
| Waiver: "RECUSADO (trava 1)… waiver válida" | o signatário já tem waiver de menos de 1 ano: não precisa outra |
| Waiver: "RECUSADO (trava 2)… envelope em aberto" | já existe uma enviada e não assinada: use o reenvio (`/waivers/{id}/resend`) |
| Passo "não conectado: …" (QuickBooks, DocuSign, Asana, Kommo) | integração fora do ar: veja Integrações; quando voltar, **tentar de novo** só nesse passo |
| "invoice esperando o gerente conferir o valor: …" | fora da tabela ou sem preço de tabela: avise a gerência (Liberar invoice); não refaça o passo |
| `step/qbo`: "A invoice espera o gerente conferir o valor…" (409) | mesma coisa: é da gerência |
| `step/qbo` ou Liberar: "A invoice #… desta venda já saiu: não cobramos duas vezes" (409) | a invoice já está com o cliente: não mande outra; correção é da gerência |
| `close`: "Venda já fechada e …: fechar de novo cobraria outra vez" (409) | use os botões de cada passo no acompanhamento |
| "… está liberando a invoice agora" (ou "mandando a invoice", "fechando a venda", "cobrando o depósito", "mandando a invoice pela IA") (409) | outra aba, outro gerente, a IA ou o MCP está cobrando esta venda neste instante: espere e recarregue |
| "Esta venda mudou agora mesmo (outro clique, outra aba ou a IA?): recarregue e confira." (409) | recarregue a ficha e veja o que saiu antes de tentar de novo |
| "A tentativa de … às … não terminou: confira no QuickBooks se a invoice saiu…" (409) | é da gerência (seção 4.6.3): confere no QuickBooks; não saiu, **Não saiu: mandar** (ou `confirmar: true`); saiu, **Saiu: registrar o número** (ou `invoice/registrar`) |
| "O QuickBooks não respondeu (…): a invoice pode ter saído…" (502) | não clique de novo: o próximo pedido cai na tentativa que não terminou; é da gerência conferir |
| "A invoice #… desta venda já foi criada no QuickBooks e o envio falhou: reenvie a mesma" (409) | use **Reenviar** (seção 4.6.4): o passo não cria outra |
| Registrar: "Ligue o QuickBooks para conferir…" (503) | o QuickBooks está desligado em Integrações: sem conferir, nada é registrado |
| Registrar: "A invoice nº … não existe no QuickBooks" ou "… é de outro cliente" (409) | confira o **Invoice no.** no QuickBooks e digite de novo |
| Registrar: "A invoice nº … é de $…, e a tentativa cobrava $…" (409) | confira no QuickBooks; se a invoice é mesmo esta, **Registrar mesmo assim** |
| "Só o gerente ou o dono confirma que a tentativa anterior não mandou a invoice." (403) | quem vende não confirma: avise a gerência |
| "O pedido #… desta venda foi pago no site (Stripe): não cobramos duas vezes" (409) | o cliente pagou no site: não há invoice nem depósito a mandar pelo painel |
| `step/…`: "Feche a venda antes: os passos saem no fechamento…" (409) | feche a venda (**Fechar venda**): os passos saem juntos |
| QuickBooks: "o serviço não tem item no catálogo do QuickBooks: escolha o item na tela de fechar" | use **tentar de novo** e escolha o item na janela (ou `step/qbo?item_id=…`); se o item não existe, é da gerência |
| Card: "o card com este contato é do piloto …: marque "É irmão"…" | é irmão: `step/cliente?irmao=true` (ou feche de novo marcando "É irmão"); se não for, vincule ao card certo |
| Depósito: "não pede depósito no catálogo" | o serviço não tem depósito em Serviços e preços: é da gerência mudar |
| Passo Kommo "feito", mas com a nota "não achei a etapa 'Closed won' neste funil do Kommo" | o lead não se mexeu: mova a etapa à mão no chat ou avise a gerência |
| Site: "a conta do site ainda não está ligada a um card (Client ID)" | Site › Contas de clientes: ligue o driver ao card certo; o painel tenta a invoice de novo |
| Site: "o serviço não tem item do QuickBooks…" | é da gerência: escolher o item em Serviços e preços |
| Site: "… is not open for online booking right now" (reserva do kart) | o serviço com o nome daquele kart não está ativo: ative ou crie em Serviços e preços com o nome do kart (#253) |
| Site: "Online booking is closed right now" | nenhum serviço ativo em Serviços e preços: sem isso não há venda online (e o site manda a pessoa falar com a gente) |
| Site: "o cliente não está no QuickBooks…" | avise a gerência |
| Site: "não achei o item "Security deposit" no QuickBooks…" | avise a gerência (sincronizar o QuickBooks) |
| Site: "o piloto não tem data de nascimento" | o cliente completa o driver na área do cliente, ou peça ao cliente |
| Site: "piloto adulto sem e-mail: ele assina a própria waiver…" | peça o e-mail do piloto e cadastre no driver |
| Site: "Confirmar sem esperar pagamento e waiver é do gerente. Use Aceitar." | use **Aceitar** |
| Chat: "Na fila: o painel insiste…" | espere; em 15 min, se não sair, vira nota no lead e acende o aviso. Use **Enviar de novo** |
| Chat: "Kommo não conectado." | avise a gerência (Integrações) |
| Novo cliente: "Esse cliente já existia: abrindo o card dele." | confira se o card é **do mesmo piloto**. Se for irmão, use **Criar card de irmão** (seção 3) |
| Card de irmão: "este card já é do piloto …: o irmão tem outro nome" | o piloto escrito é o do card de origem: confira o nome do irmão |
| Unir: "Esses dois cards não se unem: …" | são drivers ou contas diferentes do site, ou irmãos: não una |
| Nova tarefa: "A data cai numa segunda-feira…" | escolha outra data |
| Nova tarefa: "Piloto menor de idade: o responsável é obrigatório…" | preencha o responsável |
| Google: botão cinza, "O gerente ainda não configurou o acesso ao Google…" | é da gerência: seção 4.8, "Para a gerência" |
| Google: "O arquivo na VPS é de um cliente OAuth do tipo Desktop…" | a gerência cria um cliente do tipo **Aplicativo da Web** e troca o arquivo |
| Google: "A volta do Google não foi aceita…" | o link venceu (10 min), já foi usado ou abriu em outro navegador: toque em Conectar de novo, no mesmo navegador |
| Google: "O Google não deu a permissão de agenda…" | conecte de novo e deixe marcado o acesso ao Google Calendar |
| Google: "O Google recusou a renovação: conecte de novo." | o acesso expirou (no modo Testing, a cada 7 dias) ou foi revogado: **Conectar de novo** |
| Google: "Esta conta não está na lista de testadores" (tela do Google) | o app está em Testing: a gerência põe o seu e-mail em Usuários de teste, ou publica o app |
| Google: "Error 400: redirect_uri_mismatch" (tela do Google) | o redirecionamento do cliente OAuth não está igual a `https://ops.urace.us/ops/api/google/callback`: é da gerência |
