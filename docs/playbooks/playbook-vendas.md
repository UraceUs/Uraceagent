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
> Atualizado em 14/10/2026 (#204: invoice fora da tabela só com o gerente, depósito na venda manual,
> card de irmão, retorno vencido em Precisa de atenção, confirmação do chat pelo Claude).
> Painel: https://ops.urace.us/ops/

---

## Sumário

1. Para quem é e como usar
2. O funil da URACE no Command Center
3. Achar ou criar o cliente certo
4. Oportunidade e venda: abrir, ligar, fechar, reenviar, o seu Google Calendar
5. Agendamentos do site: carrinho, pagamento no Stripe e a loja do site
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
5. Preço só da tabela (Rate Card ou Agendamentos do site › Serviços e preços). Não sabe? Pergunte.
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
PEDIDO NO SITE  área do cliente → Agendamentos do site › Agendamentos (/ops/site), "pendente"
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
- Se a família tem conta no site, o card do irmão também pode nascer em **Agendamentos do site ›
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
| Anotação interna | **Guardar anotação** | `POST /sales/{id}/note` |
| Editar a ficha | — (pela IA ou API) | `PATCH /sales/{id}`: o corpo **precisa** levar `name` |
| Mover etapa | — | `POST /sales/{id}/stage` |
| Marcar perdido | **Perdido** | `POST /sales/{id}/stage` com `etapa: PERDIDO` e `motivo` |

Os retornos vencidos ou de hoje somam no contador de vendas do menu e aparecem na Agenda de vendas.
Os **vencidos** também aparecem em **Precisa de atenção** ("retorno(s) de venda atrasado(s)", com o
link para a Agenda de vendas).

### 4.4 Preço: de onde vem

Preço nunca é de memória. A ordem (`brain/00_SYSTEM/PARAMETROS.md`):

1. o valor que o dono passar (vence tudo);
2. a **Rate Card** (planilha no Drive; serviço: aba Academy; corrida: aba Racing team);
3. invoice anterior do mesmo serviço e cliente (dizendo que reaproveitou);
4. catálogo do QuickBooks (defasado, só referência).

Para sessão do site, o preço está em **Agendamentos do site › Serviços e preços** (`GET /ops/api/site/servicos`).
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

- **Não cobre duas vezes.** `step/qbo` **cria e envia outra invoice**. Só use quando a linha do
  QuickBooks estiver como **falhou**. Se estiver "feito", a invoice já saiu.
- **Invoice esperando o gerente** não sai por `step/qbo`: a resposta é 409 ("A invoice espera o
  gerente conferir o valor…"). Avise a gerência (seção 4.6.1).
- `step/waiver` reenvia pelo DocuSign; as travas de waiver válida e envelope aberto continuam.
- Para corrigir o e-mail de uma waiver que já saiu, use o reenvio da waiver
  (`POST /waivers/{id}/resend` com o e-mail novo), não um envio novo.
- `step/cliente?irmao=true` cria o card de irmão quando o passo parou porque o card do contato era
  de outro piloto.

#### 4.6.1 Liberar invoice (gerente e dono)

A ficha da oportunidade mostra **"Invoice esperando o gerente conferir o valor"**, com o valor da
venda e o preço da tabela. O item também aparece em **Precisa de atenção** ("Invoice da venda de …
esperando você conferir o valor").

- Quem vende vê o aviso e "Só o gerente ou o dono libera."
- O gerente (ou o dono) clica **Liberar invoice**: a janela mostra serviço, **valor da venda**,
  **preço da tabela (catálogo)**, a diferença e o depósito. **Liberar invoice de $…** cria e envia a
  invoice pelo QuickBooks. Se o serviço ainda não tem item no catálogo, escolha o item ali.
- API: `POST /ops/api/sales/{id}/invoice/liberar` com `{"valor": <o valor da venda>}` (papel
  **Gerente**). Se o valor da venda mudou, a resposta é 409 e nada sai. Fica na auditoria
  (`sales.invoice.release`) com o valor, o preço da tabela e quem liberou.

#### 4.6.2 Cobrar só o depósito

Venda fechada sem o depósito (fechada antes de 14/10, ou com a invoice desligada) e o serviço pede
depósito: a ficha mostra **"Depósito ainda não cobrado"** com o botão **Cobrar só o depósito**
(Operador). Sai uma invoice só com a linha "Security deposit", no valor do catálogo.

- API: `POST /ops/api/sales/{id}/deposit` (Operador).
- Não cobra duas vezes; com a invoice principal esperando o gerente, o depósito vai junto quando ela
  for liberada; serviço sem depósito responde "não pede depósito no catálogo".

### 4.7 A IA dentro da oportunidade

Na ficha há a caixa **Falar com a IA** ("ela age nesta oportunidade: registrar, agendar, waiver,
invoice, fechar"). Ditar funciona. O que ela pode fazer e quem aprova:

| Ação | Política (padrão do código, revisada pelo dono em 21/09) |
|---|---|
| registrar ligação, marcar retorno, anotar, criar tarefa | executa sozinha |
| enviar waiver | executa sozinha (as travas do DocuSign continuam) |
| mover etapa, fechar a venda | espera alguém confirmar (o Operador pode) |
| enviar invoice | espera confirmação, e **só gerente ou administrador** decide; fora da tabela, recusa se quem decide não é gerente |

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

## 5. Agendamentos do site

Tela: **Agendamentos do site › Agendamentos** (`/ops/site`). Rotas em `/ops/api/site/…`.

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

### O que o Aceitar faz (código: `providers/cobranca_agenda.py`)

1. **Invoice:** o preço gravado no agendamento + o **depósito**, quando o serviço tem depósito
   (configurado em Serviços e preços). A linha do depósito diz que é devolvido em até 5 dias úteis
   se não houver incidente. **Não cobra duas vezes**: se o agendamento já tem invoice, não cria outra.
2. **Contrato (Academy):** cliente com contrato não paga de novo; a sessão conta no contrato. Acima
   do limite do mês, cobra.
3. **Waiver:** se o piloto não tem waiver válida no dia da sessão, sai pelo DocuSign. Com a waiver
   nativa ligada, o cliente assina na área do cliente.
4. **Confirma sozinha** quando a invoice aparece paga e a waiver está em dia.
5. **Lembrete ao cliente** por e-mail 3 dias e 1 dia antes, dizendo o que falta.
6. Falhou algo (sem card, sem cliente no QuickBooks, serviço sem item)? O motivo fica escrito no
   agendamento e o painel tenta de novo (a invoice, até 3 vezes).

Cliente com contrato e waiver em dia: o pedido **confirma sozinho** assim que é marcado.

### Duas chaves da agenda (só leitura para quem vende)

| Chave | Onde | Quem muda | Efeito |
|---|---|---|---|
| **Confirmar sozinho** (`auto_confirm`) | Disponibilidade | Gerente | o pedido já nasce **confirmado**, sem passar pelo Aceitar. Nesse caso o painel **não** gera invoice nem waiver para ele: confira pagamento e waiver por fora |
| **Venda automática** (`auto_sell`, #164) | Disponibilidade | **só Administrador** | o pedido não espera o Aceitar: na hora, o card do piloto é garantido, o cliente no QuickBooks é achado ou criado, invoice + depósito + waiver saem, e o cliente recebe e-mail com o que falta e outro quando confirma |

Na venda automática, o card só é ligado sozinho a um card que existe com **duas provas**: o e-mail
confirmado da conta é o do card **e** o nome do piloto é o do card. Fora disso nasce card novo
marcado "POSSÍVEL DUPLICADO" para a equipe conferir e unir.

**Plano mensal pelo site** (#169, Academy e Boost): o cliente compra o plano, a primeira
mensalidade sai na hora e as outras ficam agendadas no dia 1. Nada é cobrado sem a venda
automática ligada.

### 5.1 Carrinho do site e pagamento no Stripe (#236)

Dono, 14/10: *"o sistema de carrinho e checkout ... usando o Stripe"*; *"quando a pessoa selecionar
o serviço, selecionar a data, já vai com aquele serviço e o preço que está lá"*; *"O depósito de
segurança ele é cobrado em venda manual ou automática"*; *"Todo mundo agora precisa de conta no site"*.

**O que o cliente faz** (site novo, em inglês; o carrinho e as páginas do pedido também em português, #248):

1. Na página do Arrive and Drive escolhe o kart, o dia e o turno e toca em **Add to cart** (o preço
   mostrado é o do serviço do painel com o nome do kart). Na reserva da área do cliente
   (`/ops/portal/reserve`) também há **Add to cart**. Na loja, **Add to cart** ao lado do **Buy now**.
   **Toda compra pede a conta do site** (#248, dono 14/10: *"Para a pessoa conseguir comprar com a gente,
   ela tem que criar a conta dela lá no site da URACE"*): **Buy now** sem conta leva para entrar (ou criar
   a conta) e volta para o produto.
   > **O nome do serviço tem de ter o nome do kart** (#253, dono 15/10, com o print da tela de reserva
   > mostrando um serviço de teste já escolhido: *"remova esse produto d teste quando for para essa
   > pagina ja vai com o produto pré selecionado"*). Quem chega do site com um kart só vê
   > pré-selecionado o serviço de **Agendamentos do site › Serviços e preços** cujo **nome contém o nome
   > do kart** (Baby Kart, 4-stroke, 2-stroke, Adult Shifter) — por exemplo "Arrive and Drive 2-stroke".
   > Nenhum serviço com o nome do kart: a reserva **não escolhe nada** (nunca um serviço que não é do
   > kart) e a tela avisa que esse kart não está aberto para reserva online agora, com o contato.
   > Nenhum serviço **ativo**: o site e a reserva dizem que a reserva online está fechada e mandam falar
   > com a gente, em vez de mostrar um botão que não leva a nada. No calendário do site o botão diz o
   > que falta: "Pick a day to continue" sem dia, "Pick a time to continue" com o dia e sem turno; dia
   > com um turno só aberto já vem com o turno escolhido.
2. O ícone do carrinho no topo mostra quantos itens há. Em **`/cart/`** ele vê as linhas, o depósito e
   o total. **Sessão pede a conta do site** (Sign in / Create account, e volta para o carrinho) e o
   **piloto** de cada sessão (um piloto só já vem escolhido). Produto sozinho também pede a conta (#248).
   No topo do carrinho e das páginas do pedido há a chave **English / Português** (as bandeiras, como no
   painel); a escolha fica guardada no navegador.
3. **Checkout** abre o Stripe com **todas** as linhas e, para cada sessão com depósito, a linha
   "Refundable security deposit". Paga, volta para `/cart/thanks/` com a **página do pedido** (abaixo).

**Atenção ao atender (#252):** na página do Arrive and Drive existem **dois botões** e eles levam a
**dois pagamentos diferentes** — **Add to cart** leva ao carrinho e a pessoa paga no **Stripe** na
hora; **Continue to booking** leva à área do cliente e a pessoa paga a **invoice do QuickBooks** mais
a waiver. O texto embaixo dos botões só explica o caminho da invoice. Se o cliente ligar dizendo que
"já pagou" ou que "recebeu uma invoice", confira primeiro por qual dos dois ele entrou:
Agendamentos do site › **Pedidos do site** mostra o que veio pelo Stripe; a invoice aparece no card.
A comparação completa dos dois sites está em
`docs/site-publico/comparacao-urace-us.md`.

**Regras que o sistema garante** (código: `providers/carrinho.py`):

| Regra | Como |
|---|---|
| preço é do sistema | o servidor recalcula preço (Serviços e preços / catálogo da loja), depósito e vaga; o navegador só manda as escolhas |
| preço do dia | o pedido guarda o preço e o depósito do dia da compra; mudar o preço depois não muda o pedido |
| vaga | confere ao montar o carrinho, no checkout (o Checkout do Stripe expira em 31 min) e **de novo no pagamento** |
| conta e piloto | **toda compra pede a conta do site**; o e-mail da conta vai para o Stripe e é o dos avisos; só pilotos da própria conta, com o cadastro em dia (medidas e dados do responsável) |
| card certo | a sessão vai para o card do **piloto**; o produto, para o card ligado à **conta** (Contas de clientes) ou, sem ele, pela regra da loja (e-mail **e** nome) |
| idioma | o pedido guarda o idioma em que a pessoa comprou (EN/PT): os e-mails dela saem nele e o Stripe abre nele; os avisos da equipe são sempre em português |
| uma vez só | o webhook do Stripe e a página de obrigado não marcam nem vendem duas vezes |
| cancelado / expirado / pagamento não passou | nada é marcado nem vendido; a vaga **não fica presa** (a sessão só entra na agenda quando o pagamento entra) |

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
outro cliente); ligue em **Agendamentos do site › Contas de clientes**.

- **Try again** abre um checkout novo com as **mesmas escolhas** (produto, opção, quantidade; serviço,
  dia, turno, piloto). O servidor recalcula **preço, depósito e vaga** na hora: se o preço mudou, vale o de
  hoje; se a vaga acabou ou o cliente não está logado na conta do pedido, ele cai no carrinho com as
  escolhas de volta e o carrinho mostra o porquê (e pede para entrar).
- **Restore cart** põe as escolhas de volta no carrinho do navegador (junto do que já estiver lá, sem
  duplicar) e o cliente confere e paga pelo **Checkout** de sempre.
- O pedido novo fica ligado ao antigo ("refeito do pedido #N"); pago o novo, a página do antigo aponta
  para ele e não oferece pagar de novo.
- O e-mail que não saiu (Gmail fora do ar) a rodada de 15 min tenta de novo, sem repetir o que já saiu.

**Onde a equipe vê:** **Agendamentos do site › Pedidos do site** (`/ops/site/pedidos`) lista todos os
pedidos do carrinho e da loja em **todo** estado (pago, processando o pagamento, pagamento não passou,
checkout expirou, no checkout), com filtro, quem, o quê, o total, se o aviso por e-mail saiu (e se a
pessoa comprou em português), e os botões
**Página do pedido ↗** e **Copiar o link**: é esse link que você manda ao cliente que liga perguntando do
pedido. No detalhe da venda, o cartão **Pedido do site #N** também tem os dois botões. **Quem vende**, no
e-mail "Site · PAGAMENTO FALHOU" ou "Site · CHECKOUT EXPIROU": o cliente já recebeu o botão (Try again /
Restore cart) no e-mail da conta, e um contato ajuda a fechar; se o aviso disser "sem e-mail do cliente"
(pedido antigo, de antes da conta obrigatória), ligue e mande o link.

**O que aparece para a equipe quando o pedido é pago:**

- **Agendamentos do site:** a sessão entra **aceita e paga** (chip "pago no site · pedido #N"); não sai
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

**O catálogo mudou?** O catálogo da loja do site é um arquivo do sistema
(`command_center/vitrine/dados/produtos.json`). Produto que falta, preço errado ou foto trocada **não
se arruma pela tela**: abra uma issue para o Claude, com o endereço do produto no `urace.us`.
Em 15/10 entrou assim o **OTK Magnesium Wheels Set MXC - 130mm, 210mm** ($838.95), que estava no
site de hoje e faltava no catálogo novo.

### Contas de clientes (Agendamentos do site › Contas de clientes)

Quem cria conta no site precisa estar ligado ao card certo. Cada driver tem o seu card.

| Ação | Rota | Papel |
|---|---|---|
| ligar a conta a um card | `POST /site/contas/{conta}/vincular` | Operador |
| ligar um driver a um card | `POST /site/drivers/{driver}/vincular` | Operador |
| criar card para a conta | `POST /site/contas/{conta}/criar-cliente` | Operador (recusa se já existe cliente com o mesmo e-mail ou telefone) |
| criar card para um driver | `POST /site/drivers/{driver}/criar-cliente` | Operador (recusa se já existe card com o nome do driver: vincule a ele. O e-mail repetido dos irmãos não bloqueia) |
| desligar | `…/desvincular` | Gerente |

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
| refazer um passo | `POST /ops/api/sales/{id}/step/{passo}` | — (`passo`: cliente, qbo, waiver, asana, kommo; `cliente` aceita a consulta `{"irmao": true}`) | Operador | **sim** |
| cobrar só o depósito | `POST /ops/api/sales/{id}/deposit` | — | Operador | **sim** |
| liberar invoice fora da tabela | `POST /ops/api/sales/{id}/invoice/liberar` | `{"valor": 0}` (o valor da venda, conferido) | **Gerente** | **sim** |
| card de irmão | `POST /ops/api/clients` | `{"name": "Responsável Exemplo", "pilot_name": "Irmão Exemplo", "pilot_dob": "2016-05-09", "irmao_de": 123}` | Operador | não |
| tarefa de serviço no Asana (modelo oficial) | `POST /ops/api/tasks` | `{"client_id": 123, "pilot_name": "Piloto Exemplo", "responsible": "Responsável Exemplo", "email": "cliente@exemplo.com", "phone": "+1 407 555 0100", "dob": "2014-05-10", "product": "Test Drive", "category": "4 stroke", "due_on": "2026-10-24"}` | Operador | **sim** |
| enviar waiver avulsa | `POST /ops/api/waivers/send` | `{"template": "parental", "signer_name": "Responsável Exemplo", "signer_email": "cliente@exemplo.com", "service": "Test Drive", "client_id": 123}` | Operador | **sim** |
| reenviar waiver (corrigir e-mail) | `POST /ops/api/waivers/{id}/resend` | `{"email": "novo@exemplo.com"}` | Operador | **sim** |
| aceitar pedido do site | `POST /ops/api/site/agendamentos/{id}/aceitar` | `{}` | Operador | **sim** |
| recusar pedido do site | `POST /ops/api/site/agendamentos/{id}/recusar` | `{"nota": "texto que o cliente vai ler"}` | Operador | **sim** |
| cancelar sessão | `POST /ops/api/site/agendamentos/{id}/cancelar` | `{"nota": "…"}` | Operador | **sim** |
| confirmar sem pagamento e waiver | `POST /ops/api/site/agendamentos/{id}/confirmar` | `{}` | **Gerente** | **sim** |
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
   (`step/{passo}`).
3. Passo com `ok: null` e "invoice esperando o gerente conferir o valor": não refaça. Avise a
   gerência; ela usa **Liberar invoice** (seção 4.6.1).
4. Faltou o depósito? **Cobrar só o depósito** (seção 4.6.2).
5. Nunca chame `close` de novo numa venda que já tem `closing`.

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
3. Agendamentos do site › Agendamentos › Esperando confirmação.
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
| **Não cobrar duas vezes** | antes de fechar, olhe `closing`; `step/qbo` só para passo que falhou; agendamento com invoice não gera outra; o depósito sai uma vez por venda (`closing.deposito_cobrado`) |
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
| E-mail "Site · PAGAMENTO FALHOU: pedido #N" | o meio de pagamento que confirma depois não passou; nada foi cobrado e a vaga está livre. Agendamentos do site › Pedidos do site › **Copiar o link** e mande ao cliente (ele toca em **Try again**); sem e-mail no Stripe, ligue (seção 5.1) |
| Cliente diz "o site não deixa comprar sem conta" | regra do dono (#248): toda compra no site pede a conta. Mande criar em **Create account** (o botão leva e volta para o produto ou o carrinho) |
| Cliente pergunta "e o meu pedido?" | Agendamentos do site › Pedidos do site: ache pelo nome ou e-mail, veja o estado e mande o link da **Página do pedido** |
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
| QuickBooks: "o serviço não tem item no catálogo do QuickBooks: escolha o item na tela de fechar" | escolha o **Item do catálogo** e use **tentar de novo**; se o item não existe, é da gerência |
| Card: "o card com este contato é do piloto …: marque "É irmão"…" | é irmão: `step/cliente?irmao=true` (ou feche de novo marcando "É irmão"); se não for, vincule ao card certo |
| Depósito: "não pede depósito no catálogo" | o serviço não tem depósito em Serviços e preços: é da gerência mudar |
| Passo Kommo "feito", mas com a nota "não achei a etapa 'Closed won' neste funil do Kommo" | o lead não se mexeu: mova a etapa à mão no chat ou avise a gerência |
| Site: "a conta do site ainda não está ligada a um card (Client ID)" | Agendamentos do site › Contas de clientes: ligue o driver ao card certo; o painel tenta a invoice de novo |
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
