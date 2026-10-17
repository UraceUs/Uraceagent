# Suits · Alpha Line — guia para operar com o Claude

> **Para quem é:** o Lucas, e o Claude que trabalha com ele.
> **Como usar:** cole este arquivo inteiro nas instruções de um Projeto do Claude (claude.ai ›
> Projetos › Instruções do projeto), ou salve como `CLAUDE.md` na pasta em que você abre o Claude
> Code. A partir daí, o Claude sabe como a aba Suits funciona, o que pode fazer sozinho e o que
> tem de perguntar antes.
>
> Atualizado em 17/10/2026 (issue #313, o cartão novo das listas; antes, #195).

---

## 1. O que é a aba Suits

A aba **Suits · Alpha Line** do Command Center (`https://ops.urace.us/ops/suits`; no menu lateral, na área
**Pedidos e compras**) é onde vive
todo pedido de **macacão de kart personalizado**, do primeiro contato até a entrega. Ela
substituiu o quadro SUITS do Asana, que já foi importado para lá.

O macacão é **100% personalizado**: medidas, design, cores, logos e a posição de cada logo são
feitos para aquele cliente. Nada é padrão. Por isso um pedido só anda quando tem duas coisas:
as **29 medidas** do piloto e o **design** aprovado.

Quem trabalha em cada pedido:

| Papel | Quem é | O que recebe |
|---|---|---|
| Cliente | quem comprou (às vezes o pai ou a mãe do piloto) | boas-vindas, manual de medidas, a arte para aprovar |
| Designer | **Mateus** (`carvalhovisual1@gmail.com`) | **só o design**, com a referência "Suits #id". Nunca nome completo, e-mail, telefone, endereço ou pagamento do cliente |
| Fornecedor | o marcado como **atual** em Fornecedores (hoje o Usman) | o pedido de produção: as 29 medidas e o mockup final |
| A URACE com o cliente | assina como **George** | — |

### Como a tela mostra cada um (#313)

As três listas usam o cartão do painel inteiro (o "padrão D", playbook geral, seção 3):

- **Pedidos:** em cima, a **etapa** (Standby, Awaiting Measurements…) ou *descartado*; as iniciais do piloto, o nome do
  pedido, o produto, a quantidade e o fornecedor; no **bloco grande, o dia do pedido**; embaixo, **IA desligada** e
  quantas **notas** ele tem. Toque em qualquer lugar do cartão para abrir o pedido.
- **Leads:** a situação (*aberto*, *virou pedido*, *perdido*), o nome, o e-mail e o telefone, a nota; embaixo,
  **Virar pedido** (azul), **Perdido**, **Card do cliente** e **Ver pedido**.
- **Fornecedores:** *atual* em verde em cima, se tem FIA, **quantos pedidos** no bloco grande, os dados (contato,
  valor, frete, prazo…) na lista e **Editar** (gerente).

---

## 2. Conectar o Claude ao painel (uma vez)

Você precisa de um **usuário seu no Command Center** com papel **OPERATOR** ou acima. Quem cria é
o dono, na tela **Usuários**. Ninguém manda senha pelo chat.

**No app do Claude (claude.ai, celular ou computador):**
1. Configurações › **Conectores** › **Adicionar conector personalizado**.
2. Nome: `URACE Command Center`. URL: `https://ops.urace.us/ops/mcp`
3. Clique em **Conectar**, entre com o **seu** usuário do painel, deixe marcado
   **"Também operar o painel como você"** e clique em **Autorizar**.

**No terminal (Claude Code):**
```
claude mcp add --transport http urace https://ops.urace.us/ops/mcp
```
Depois, dentro do Claude Code, digite `/mcp`, escolha **urace** e **Authenticate**. Entre com o
seu usuário e marque **"Também operar o painel como você"**.

Sem a caixa marcada, o Claude só lê. Tudo o que ele faz fica na auditoria do painel com o **seu**
nome.

**Ferramentas que aparecem para o Claude:**
- `urace_operacoes`: lista as operações do painel. Filtre com a palavra `suits`.
- `urace_api`: executa uma operação (método, caminho, corpo). É exatamente o mesmo que clicar no
  botão do painel.
- `urace_resumo` e `urace_atencao`: o panorama e o que precisa de gente hoje.

**Confirmação:** o que manda algo para fora (e-mail, rascunho no Gmail, QuickBooks, Asana) não
acontece na primeira chamada. O painel devolve o que vai fazer. O Claude mostra para você e só
repete com `confirmar: true` depois do seu "pode mandar".

---

## 3. As dez etapas

O código entre crases é o que vai no campo `status`.

| # | Etapa | Código | Quando |
|---|---|---|---|
| 1 | Standby | `standby` | pedido criado, esperando o próximo passo |
| 2 | Awaiting Measurements | `awaiting_measurements` | boas-vindas enviadas, esperando as medidas |
| 3 | Design Pending | `design_pending` | pago e com as ideias de design: o designer trabalha |
| 4 | Design Under Client Review | `design_review` | o cliente está olhando a arte |
| 5 | Approved | `approved` | cliente aprovou design e medidas: pode ir para produção |
| 6 | Order sent to supplier | `sent_to_supplier` | pedido enviado ao fornecedor |
| 7 | In Production | `in_production` | o fornecedor está fazendo |
| 8 | In Transit | `in_transit` | o fornecedor despachou (com rastreio) |
| 9 | Delivered | `delivered` | entregue: o pedido fecha e vai para o Histórico |
| 10 | Canceled | `canceled` | cancelado: fecha e vai para o Histórico |

Cada troca de etapa fica na **linha do tempo** do pedido, com quem trocou e quando.

---

## 4. As 29 medidas

Vão no campo `medidas.valores`, com a unidade em `medidas.unidade` (`cm` ou `in`) e o peso em
`medidas.unidade_peso` (`kg` ou `lb`). **Grave o número exatamente como o cliente mandou**, na
unidade dele. O painel mostra as duas unidades no e-mail do fornecedor. O tamanho do pé é texto
(`"42 EUR"`, `"9 US"`): não existe conversão exata, então nunca converta.

| # | Chave | Medida |
|---|---|---|
| 1 | `head` | Head circumference |
| 2 | `forehead_neck` | Distance from forehead to neck |
| 3 | `neck` | Neck circumference |
| 4 | `chin_neck` | Distance from chin to neck |
| 5 | `shoulder` | Shoulder width |
| 6 | `chest` | Chest circumference |
| 6bis | `bust` | Bust circumference (só para mulheres) |
| 7 | `waist` | Waist circumference |
| 8 | `hip` | Hip circumference |
| 9 | `neck_back` | Distance from neck to back |
| 10 | `neck_tailbone` | Distance from neck to tail bone |
| 11 | `arm` | Arm length |
| 12 | `elbow_wrist` | Distance from elbow to wrist |
| 13 | `biceps` | Biceps circumference |
| 14 | `elbow` | Elbow circumference |
| 15 | `forearm` | Forearm circumference |
| 16 | `wrist` | Wrist circumference |
| 17 | `thigh` | Thigh circumference |
| 18 | `knee` | Knee circumference |
| 19 | `calf` | Calf circumference |
| 20 | `ankle` | Ankle circumference |
| 21 | `waist_ankle` | Distance from waist to ankle |
| 22 | `groin_ankle` | Distance from groin to ankle |
| 23 | `knee_ankle` | Distance from knee to ankle |
| 24 | `trapezius_ankle` | Distance from trapezius to ankle |
| 25 | `trapezius_floor` | Distance from trapezius to floor |
| 26 | `nipple_ankle` | Distance from nipple to ankle |
| 27 | `height` | Height |
| 28 | `weight` | Weight |
| 29 | `foot` | Foot size (texto) |

Ao abrir um pedido, o painel devolve `faltam_medidas`: a lista do que ainda não chegou. Para
apagar uma medida gravada errada, mande a chave com valor vazio.

**Design** (campo `design`): `ideia`, `cores`, `logos`, `posicao_logos`, `nome` (o nome que vai
no macacão), `bandeira`, `observacoes`.

---

## 5. De onde vem um pedido

1. **Venda no site.** Chega o e-mail "[Urace]: You've got a new order" com um macacão. A ponte
   abre o pedido sozinha (origem `site`, com o número do pedido do site) e a IA manda as
   boas-vindas.
2. **E-mail de cliente.** Um e-mail com o marcador **Suits** do Gmail **só vira candidato** quando
   o assunto ou o texto **falam de macacão** (suit, race suit, macacão, mono de karting,
   combinaison…) e o remetente **não é robô** (noreply, cobrança, recibo, newsletter, aviso).
   Mesmo assim, o pedido só é criado quando a IA lê a conversa e vê que é **alguém querendo
   comprar um macacão**: orçamento, medidas ou design para encomendar, confirmação ou pagamento.
3. **À mão**, pelo botão **Registrar novo pedido** ou pela API, sempre com **"Vincular ao
   cliente"** quando a pessoa já tem card no painel.
4. **Lead que virou pedido** (aba Leads › Virar pedido).

### O que NÃO é pedido de macacão

Nunca abra pedido, e descarte se aparecer um:
- fatura, recibo ou cobrança (Stripe, OpenAI, Anthropic, QuickBooks…);
- newsletter, propaganda, ofertas de milhas, agência de vídeo;
- homologação/FIA, frete, nota fiscal, conversa com fornecedor sem pedido de cliente;
- e-mail da própria equipe (`@urace.us`);
- conversa sobre outro serviço (aula, aluguel, horário de treino);
- dúvida geral sem intenção de comprar. **Na dúvida, não crie.**

Exemplo real de 13/10: os pedidos #153 a #163 (Stripe, OpenAI, Anthropic, Points Insider,
ConnectMiles, RaceSelect, Max from 3 Second Media, Alexa Llanteret, Daneyza Cabrestra, Eduardo
Resende) foram abertos por engano pela versão antiga da ponte, só por causa do marcador. Foram
**descartados**.

---

## 6. A ponte de e-mail (a IA trabalhando sozinha)

A cada 15 minutos a ponte lê o Gmail `urace@urace.us` e, para cada novidade, chama a IA do
painel com o pedido e o e-mail (anexos baixados para a pasta do pedido):

| Chegou | A IA faz |
|---|---|
| venda de macacão no site | preenche o pedido, manda as boas-vindas com o manual de medidas (PDF), move para `awaiting_measurements` |
| resposta do cliente | grava medidas e design que vieram, pede **só o que falta**; com design suficiente, manda o briefing ao designer e move para `design_pending`; aprovou a arte, move para `approved` |
| resposta do designer | pergunta: leva ao cliente com as palavras da URACE; arte entregue: manda ao cliente pedindo aprovação e move para `design_review` |
| e-mail do fornecedor | anota; se avisou produção ou envio, move para `in_production` / `in_transit` com o rastreio |
| reclamação, reembolso, troca, cancelamento, preço, algo estranho | **não responde**: chama a equipe com a nota "Precisa de alguém da equipe: …" na linha do tempo do pedido |

**A chave "IA neste pedido".** Todo pedido tem, no topo, uma chave que liga e desliga a IA só
naquele pedido (ligada por padrão). Desligada, a IA não responde, não manda e-mail, não altera e
não anota nada ali, e não dá para simular nem "Pedir à IA" pela nota. O e-mail que chegar fica
guardado (com os anexos), aparece na linha do tempo como "Precisa de alguém da equipe" e quem
responde é a equipe. Use quando o cliente pede atendimento humano, quando a negociação está
delicada, ou quando o pedido é tratado por fora. Ligou de novo, a ponte volta a tratar os e-mails
novos. Na lista, o pedido aparece com a etiqueta **IA desligada**.

**Simulação ou envio de verdade.** Com o **envio automático desligado** (o padrão), nada sai: o
e-mail que a IA mandaria aparece na linha do tempo do pedido para a equipe conferir. Só um
gerente liga o envio automático, em Suits › Ponte de e-mail.

**Quem recebe é o painel que decide**, nunca o modelo: o e-mail só vai para o cliente, o designer
ou o fornecedor **daquele** pedido.

### A política dos macacões (vai nas boas-vindas)

- três rodadas de revisão do design antes da produção, sem custo;
- macacão personalizado não tem devolução voluntária nem reembolso;
- erro da URACE: corrigido sem custo;
- erro de medida do cliente que inutilize o macacão: 50% de desconto na troca;
- erro do design fornecido pelo cliente que exija macacão novo: 33% de desconto na troca.

Tudo sujeito aos termos da compra e aos direitos do cliente. Conflito com isso sobe para a equipe.
**Nunca prometa preço, prazo ou desconto que não esteja no pedido ou nesta política.**

---

## 7. As operações (o que o Claude chama com `urace_api`)

Todos os caminhos começam com `/ops/api/suits`. "Op." é OPERATOR, "Ger." é MANAGER.

### Ler

| Para | Método e caminho | Papel |
|---|---|---|
| quantos por etapa | `GET /ops/api/suits/resumo` | Op. |
| a lista | `GET /ops/api/suits` com consulta `estado` = `abertos`, `fechados` ou `descartados`; `status` = código da etapa; `q` = nome, piloto ou e-mail; `limit`, `offset` | Op. |
| um pedido inteiro (cliente, medidas, `faltam_medidas`, design, notas, o que a IA respondeu) | `GET /ops/api/suits/{id}` | Op. |
| os arquivos que chegaram por e-mail | `GET /ops/api/suits/{id}/anexos` | Op. |
| o e-mail ao fornecedor já montado (e o que falta para montar) | `GET /ops/api/suits/{id}/email-fornecedor` | Op. |
| o que o cadastro do cliente já tem (para puxar ao pedido) | `GET /ops/api/suits/cliente/{client_id}` | Op. |
| as etapas, as medidas e os campos de design | `GET /ops/api/suits/etapas` | Op. |
| leads de macacão | `GET /ops/api/suits/leads` (consulta `estado` = `aberto`, `convertido`, `perdido`) | Op. |
| fornecedores | `GET /ops/api/suits/fornecedores` | Op. |
| a configuração da ponte | `GET /ops/api/suits/ponte` | Op. |

Para achar o card do cliente: `GET /ops/api/clients` com consulta `q` = nome.

### Fazer

| Para | Método e caminho | Corpo (exemplo) | Papel |
|---|---|---|---|
| registrar pedido | `POST /ops/api/suits` | `{"customer_name": "Ryan Capner", "customer_email": "ryan@exemplo.com", "client_id": 584, "driver_name": "Ryan Jr.", "nota": "pediu orçamento pelo WhatsApp"}` | Op. |
| atualizar dados | `PATCH /ops/api/suits/{id}` | `{"customer_phone": "+1 916 555 0148", "ship_address": "..."}` | Op. |
| gravar medidas | `PATCH /ops/api/suits/{id}` | `{"medidas": {"valores": {"head": 59, "chest": 92, "weight": 54, "foot": "42 EUR"}, "unidade": "cm", "unidade_peso": "kg"}}` | Op. |
| gravar design | `PATCH /ops/api/suits/{id}` | `{"design": {"cores": "preto e vermelho", "logos": "URACE no peito", "nome": "RYAN"}}` | Op. |
| mudar a etapa (com o motivo) | `PATCH /ops/api/suits/{id}` | `{"status": "design_pending", "nota": "cliente mandou medidas e logos"}` | Op. |
| anotar na linha do tempo | `PATCH /ops/api/suits/{id}` | `{"nota": "cliente pediu para trocar o azul por verde"}` | Op. |
| ligar a conversa do Gmail ao pedido | `PATCH /ops/api/suits/{id}` | `{"gmail_thread_cliente": "<link da conversa no Gmail>"}` (também `gmail_thread_designer`, `gmail_thread_fornecedor`) | Op. |
| rastreio | `PATCH /ops/api/suits/{id}` | `{"status": "in_transit", "tracking": "1Z999..."}` | Op. |
| **descartar** (não é pedido de macacão) | `POST /ops/api/suits/{id}/descartar` | `{"motivo": "fatura da OpenAI"}` | Op. |
| restaurar um descartado | `POST /ops/api/suits/{id}/restaurar` | — | Op. |
| ligar ou desligar a IA neste pedido | `POST /ops/api/suits/{id}/ia` | `{"ligada": false}` | Op. |
| simular o próximo passo da IA (nada sai) | `POST /ops/api/suits/{id}/ponte/simular` | — | Op. |
| rascunho do pedido ao fornecedor no Gmail | `POST /ops/api/suits/{id}/email-fornecedor/rascunho` | — (pede confirmação) | Op. |
| guardar um lead | `POST /ops/api/suits/leads` | `{"name": "...", "email": "...", "notes": "..."}` | Op. |
| lead vira pedido | `POST /ops/api/suits/leads/{id}/pedido` | — | Op. |
| rodar a ponte agora | `POST /ops/api/suits/ponte/rodar` | — | Ger. |
| ligar/desligar a ponte e o envio automático, designer, assinatura, política | `PUT /ops/api/suits/ponte` | `{"envio_automatico": false}` | Ger. |
| fornecedores e o modelo do e-mail ao fornecedor | `POST`/`PATCH /ops/api/suits/fornecedores…`, `PUT /ops/api/suits/modelo` | — | Ger. |

**Nota com print:** a nota com imagem (screenshot para a IA entender) só pelo painel, no campo
"Nova nota" do pedido. Pelo Claude, a nota é só texto.

---

## 8. Rotinas prontas

### Toda manhã (5 minutos)
1. `GET /ops/api/suits/resumo`: quantos pedidos em cada etapa.
2. Nos pedidos abertos, procure as notas que começam com "Precisa de alguém da equipe": é a ponte
   pedindo gente (reclamação, dúvida, algo estranho). Também vale olhar `urace_atencao`.
3. `GET /ops/api/suits` com `estado=abertos`: para cada pedido parado há mais de 3 dias na mesma
   etapa, diga qual é o próximo passo e quem deve dar.
4. Algum pedido que **não é de macacão** na lista? Mostre ao Lucas e, com o OK dele, descarte.

### Cliente mandou medidas por WhatsApp ou foto
1. Abra o pedido (`GET /ops/api/suits/{id}`).
2. Grave as medidas **como vieram**, na unidade que o cliente usou.
3. Anote de onde vieram (`"nota": "medidas recebidas pelo WhatsApp em 13/10"`).
4. Conte o que ainda falta pelo `faltam_medidas` e diga ao Lucas.

### Design aprovado, mandar para produção
1. `GET /ops/api/suits/{id}/email-fornecedor`: se a resposta tiver `faltam`, pare e diga o que
   falta (medida, fornecedor, e-mail).
2. Mova para `approved` com a nota de quem aprovou e quando.
3. `POST /ops/api/suits/{id}/email-fornecedor/rascunho` (o painel pede confirmação: mostre ao
   Lucas antes). O rascunho fica no Gmail do `urace@`.
4. **Humano**: anexar o mockup final no rascunho e enviar. Depois, mover para `sent_to_supplier`.

### Fornecedor avisou que despachou
`PATCH` com `{"status": "in_transit", "tracking": "<código>", "nota": "Usman avisou pelo WhatsApp em 13/10"}`.

### Entregue
`PATCH` com `{"status": "delivered"}`. O pedido vai para o Histórico.

### Cliente pediu para falar com uma pessoa
1. Desligue a IA no pedido: `POST /ops/api/suits/{id}/ia` com `{"ligada": false}`.
2. Anote o motivo (`PATCH` com `{"nota": "cliente pediu atendimento humano"}`).
3. Daí em diante, a equipe responde. Para devolver à IA, ligue a chave de novo.

**Para o Claude:** se um pedido estiver com `ia_ligada = 0`, não proponha e-mail nem mudança de
etapa por conta própria. Mostre ao Lucas o que chegou e pergunte o que fazer.

### Achou um pedido que não é de macacão
1. Confirme lendo o pedido: remetente, assunto, notas.
2. Mostre ao Lucas o que achou.
3. Com o OK: `POST /ops/api/suits/{id}/descartar` com o motivo. Nada é apagado: o pedido some
   das listas, a ponte para de ler aquela conversa, e dá para restaurar.

### Frases que o Lucas pode usar com o Claude
- "Como estão os Suits hoje?"
- "O que falta no pedido do Ryan Capner?"
- "O cliente do pedido 171 mandou estas medidas em polegadas: …. Grave."
- "Move o 171 para Design Pending com a nota: cliente mandou logos."
- "Tem algum pedido em Suits que não é de macacão?"
- "Monta o rascunho do pedido do 171 para o fornecedor."

---

## 9. Regras que nunca mudam

1. **NO FAKE DATA.** Nunca invente medida, e-mail, telefone, endereço, data ou valor. Faltou, pergunte.
2. **O designer nunca recebe dado do cliente** (nome completo, e-mail, telefone, endereço,
   pagamento). **O cliente nunca recebe o nome ou o contato do designer.** O Mateus é designer,
   não fabricante: nunca diga ao cliente quem desenha nem quem fabrica.
3. **Nunca ponha informação de um cliente no pedido ou no card de outro.**
4. **Na dúvida, não crie pedido e não responda o cliente**: chame a equipe.
5. **Não prometa** preço, prazo ou desconto fora do pedido ou da política.
6. **Nada se apaga.** O que não serve é **descartado** (reversível), nunca excluído.
7. **E-mail que sai** (rascunho ao fornecedor, envio ao cliente) só depois do "pode mandar" do Lucas.
8. **Senha, token ou chave nunca no chat.** O login é pelo navegador.
9. **Horário da Flórida** (America/New_York) em tudo.
10. Não usar Turo nem Hostaway para nada.

---

## 10. Quando algo dá errado

| Sintoma | O que fazer |
|---|---|
| "este acesso é só de leitura" | conecte de novo e marque "Também operar o painel como você" |
| "isto é do papel MANAGER" | peça a um gerente ou ao dono |
| "precisa_confirmar" | mostre ao Lucas o que vai acontecer e repita com `confirmar: true` só depois do OK |
| pedido aparece com nome de empresa, banco ou newsletter | não é pedido de macacão: descarte (seção 8) |
| a IA não respondeu um cliente | abra o pedido: a nota da IA mostra o que ela fez ou o erro. Se a ponte estiver em simulação, o e-mail ficou na linha do tempo e não saiu |
| a ponte não roda | em Suits › Ponte de e-mail: a ponte precisa estar ligada e a IA no motor novo |
| "Falta … para montar o pedido ao fornecedor" | complete o que a mensagem diz (medida, fornecedor atual, e-mail do fornecedor) |

---

*Processo completo, com o histórico das decisões: `brain/10_PROCESSOS/Pedido de macacão.md`.*
