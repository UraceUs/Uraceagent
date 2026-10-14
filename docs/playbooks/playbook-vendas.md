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
> Atualizado em 14/10/2026. Painel: https://ops.urace.us/ops/

---

## Sumário

1. Para quem é e como usar
2. O funil da URACE no Command Center
3. Achar ou criar o cliente certo
4. Oportunidade e venda: abrir, ligar, fechar, reenviar, o seu Google Calendar
5. Agendamentos do site
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
- **Cuidado:** o painel reconhece "pessoa que já existe" por e-mail ou telefone. Ao criar o card
  de um irmão com o mesmo e-mail, ele pode devolver o card do outro irmão. **Sempre confira o
  piloto do card que voltou.** Se for de outro piloto, pare e chame a gerência: não ponha o serviço
  ali. Se a família tem conta no site, o card do irmão nasce em **Agendamentos do site › Contas de
  clientes**, pelo driver (seção 5): ali o e-mail repetido dos irmãos não bloqueia.
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

### 4.4 Preço: de onde vem

Preço nunca é de memória. A ordem (`brain/00_SYSTEM/PARAMETROS.md`):

1. o valor que o dono passar (vence tudo);
2. a **Rate Card** (planilha no Drive; serviço: aba Academy; corrida: aba Racing team);
3. invoice anterior do mesmo serviço e cliente (dizendo que reaproveitou);
4. catálogo do QuickBooks (defasado, só referência).

Para sessão do site, o preço está em **Agendamentos do site › Serviços e preços** (`GET /ops/api/site/servicos`).
Mudar preço é da gerência.

### 4.5 Fechar a venda

Botão **Fechar venda** (`POST /sales/{id}/close`). Uma tela: à esquerda o que foi vendido, à direita
a lista do que acontece, cada linha com uma chave para desligar.

**Obrigatório para fechar:** serviço e valor. Sem isso o painel responde "Para fechar, diga o serviço
e o valor."

| Passo | O que faz (código) | Quando falha |
|---|---|---|
| **Card do cliente** (`cliente`) | usa o card vinculado; se não houver, procura pelo mesmo e-mail ou telefone; se não achar, cria. Nunca duplica | raro |
| **QuickBooks** (`qbo`) | acha o cliente no QuickBooks (pelo e-mail, ou pelo nome se não houver e-mail), cria se faltar, e **cria e envia** a invoice do valor fechado. A invoice vence na data do serviço | QuickBooks fora do ar |
| **Waiver** (`waiver`) | DocuSign: parental se a idade é menor que 18, adulto se não (ou se a idade está vazia), para o nome e e-mail da ficha | sem e-mail; e-mail da URACE; já tem válida ou envelope aberto |
| **Asana** (`asana`) | tarefa no quadro U-RACE com o nome `Piloto_Serviço - data hora` e a data do serviço | Asana fora do ar |
| **Kommo** (`kommo`) | se a oportunidade veio do chat, move o lead para a etapa "Closed won" do funil dele | sem lead: só anota que não havia nada a mover |
| **Tarefa personalizada** | lembrete no painel ou tarefa no Asana, com o texto que você escrever | — |

Regras do fechamento:

- **Valor fora da tabela:** a venda fecha, os outros passos saem, e a **invoice fica esperando a
  aprovação do dono**. Gerente e administrador passam direto.
- O campo **Preço da tabela** vem preenchido com o próprio valor. **Troque pelo preço da tabela de
  verdade.** Sem preço de tabela, a invoice sai como "sem referência" e você responde pelo valor.
- Falha de um passo não derruba os outros. A tela vira **acompanhamento**: cada linha diz feito,
  aguardando ou falhou, com **tentar de novo** ao lado do que falhou.
- **Ganho** só quando há card de cliente. Se o passo Card do cliente estiver desligado e não houver
  card vinculado, a oportunidade fica em Fechamento.
- O fechamento **não cobra depósito**. Depósito de venda feita à mão segue
  `brain/10_PROCESSOS/Pagamento e security deposit.md` (conferir no QuickBooks antes de cobrar) e é
  com a gerência.
- Se você já criou a tarefa de serviço pelo modelo oficial (`POST /tasks`, com subtarefas),
  **desligue o passo Asana** no fechamento. Os dois juntos fazem duas tarefas.

### 4.6 Reenviar a invoice ou a waiver de uma venda

`POST /sales/{id}/step/{passo}`, com `passo` = `cliente`, `qbo`, `waiver`, `asana` ou `kommo`.
É o botão **tentar de novo**.

- **Não cobre duas vezes.** `step/qbo` **cria e envia outra invoice**. Só use quando a linha do
  QuickBooks estiver como **falhou**. Se estiver "feito", a invoice já saiu.
- **Invoice esperando aprovação do dono** não se libera com `step/qbo`. Avise a gerência.
- `step/waiver` reenvia pelo DocuSign; as travas de waiver válida e envelope aberto continuam.
- Para corrigir o e-mail de uma waiver que já saiu, use o reenvio da waiver
  (`POST /waivers/{id}/resend` com o e-mail novo), não um envio novo.

### 4.7 A IA dentro da oportunidade

Na ficha há a caixa **Falar com a IA** ("ela age nesta oportunidade: registrar, agendar, waiver,
invoice, fechar"). Ditar funciona. O que ela pode fazer e quem aprova:

| Ação | Política (padrão do código, revisada pelo dono em 21/09) |
|---|---|
| registrar ligação, marcar retorno, anotar, criar tarefa | executa sozinha |
| enviar waiver | executa sozinha (as travas do DocuSign continuam) |
| mover etapa, fechar a venda | espera alguém confirmar (o Operador pode) |
| enviar invoice | espera confirmação, e **só gerente ou administrador** decide |

A política em vigor de cada ação está em **O que a IA pode fazer** (`/ops/ai/capabilities`); o
administrador muda em Políticas da IA.

Atenção: o **fechar pela IA da ficha** liga todos os passos e não confere o preço da tabela.
Confira serviço, valor, idade e e-mail na ficha antes de aprovar.

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

**O que o cliente faz** (site novo, em inglês):

1. Na página do Arrive and Drive escolhe o kart, o dia e o turno e toca em **Add to cart** (o preço
   mostrado é o do serviço do painel com o nome do kart). Na reserva da área do cliente
   (`/ops/portal/reserve`) também há **Add to cart**. Na loja, **Add to cart** ao lado do **Buy now**.
2. O ícone do carrinho no topo mostra quantos itens há. Em **`/cart/`** ele vê as linhas, o depósito e
   o total. **Sessão pede a conta do site** (Sign in / Create account, e volta para o carrinho) e o
   **piloto** de cada sessão (um piloto só já vem escolhido). Produto sozinho não pede conta.
3. **Checkout** abre o Stripe com **todas** as linhas e, para cada sessão com depósito, a linha
   "Refundable security deposit". Paga, volta para `/cart/thanks/` com o pedido confirmado.

**Regras que o sistema garante** (código: `providers/carrinho.py`):

| Regra | Como |
|---|---|
| preço é do sistema | o servidor recalcula preço (Serviços e preços / catálogo da loja), depósito e vaga; o navegador só manda as escolhas |
| preço do dia | o pedido guarda o preço e o depósito do dia da compra; mudar o preço depois não muda o pedido |
| vaga | confere ao montar o carrinho, no checkout (o Checkout do Stripe expira em 31 min) e **de novo no pagamento** |
| conta e piloto | só pilotos da própria conta, com o cadastro em dia (medidas e dados do responsável) |
| uma vez só | o webhook do Stripe e a página de obrigado não marcam nem vendem duas vezes |
| cancelado / expirado | nada é marcado nem vendido |

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
- **E-mail:** o cliente recebe a confirmação (com o link para assinar a waiver de cada sessão) e
  `support@` recebe o aviso com as linhas e os links de Vendas.

**Vaga que sumiu entre o checkout e o pagamento** (alguém pegou a última vaga enquanto a pessoa
pagava): o pagamento **não se perde**. A sessão **não** entra na agenda (não lota por cima), a linha
fica **"sem vaga"**, o pedido mostra **Resolver:** no detalhe da venda, o aviso para `support@` chega
com "SEM VAGA", e o cliente lê que a equipe vai ligar para remarcar ou devolver. **Quem vende:** ligue,
remarque a sessão pela agenda (ou combine o reembolso no Stripe com o gerente) e anote na venda.

**Depósito de segurança:** cobrado no carrinho (Stripe) e na invoice do Aceitar e da venda automática
(QuickBooks), sempre que o serviço tem depósito em Serviços e preços. É devolvido em até 5 dias úteis
depois da sessão se não houver incidente: a devolução continua sendo feita pela equipe.

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

**Regra para o Claude:** o painel não pede `confirmar` nas rotas `/crm/…`. Mesmo assim, o Claude
**só responde ao lead com o texto que a pessoa aprovou, palavra por palavra**, e só move etapa ou
marca tag depois de a pessoa dizer qual.

### Atendimento humano (`/ops/atendimento`) — quando a IA pede uma pessoa (14/10)

Quando a IA (o robô da ponte ou qualquer agente com a chave do painel) precisa de gente — o
cliente pediu uma pessoa, reclamou, falou de pagamento, reembolso, desconto, segurança, ou a IA
não tem dado para responder —, ela abre um **caso**. Na hora:

1. **A IA para de responder naquela conversa.** Quem trava é o sistema (o mesmo arquivo da
   pausa por conversa), não o texto da persona. Nem follow-up, nem resgate, nem "ainda estamos
   vendo": a conversa é da pessoa até ela devolver.
2. **A equipe é avisada:** push no celular (Operador, Gerente e Administrador que ativaram o
   aviso), mensagem no canal **Atendimento humano** do chat da equipe e, quando o WhatsApp
   oficial da equipe estiver configurado, WhatsApp para quem está marcado para receber.
3. **O caso aparece na fila** com prioridade, cliente, motivo, resumo e a ação que a IA pede.

| Para | Botão | Rota | Quem |
|---|---|---|---|
| ver a fila (pendentes, em atendimento, atrasados, sem responsável, resolvidos) | — | `GET /atendimento/casos?filtro=` | todos |
| ver o caso, a linha do tempo e os avisos | abrir o caso | `GET /atendimento/casos/{id}` | todos |
| pegar o caso para você | **Assumir atendimento** | `POST /atendimento/casos/{id}/assumir` | Operador (pessoa) |
| responder ao cliente no canal dele | **Responder ao cliente** | `POST /atendimento/casos/{id}/responder` | quem atende ou Gerente |
| passar para outra pessoa | **Transferir** | `POST /atendimento/casos/{id}/transferir` | quem atende ou Gerente |
| fechar com o resultado | **Encerrar** | `POST /atendimento/casos/{id}/encerrar` | quem atende ou Gerente |
| deixar a IA continuar, com o contexto | **Devolver à IA** | `POST /atendimento/casos/{id}/devolver` | quem atende ou Gerente |
| abrir um caso à mão (e já assumir) | — | `POST /atendimento/casos` com `assume: true` | Operador |

- **Responder:** o texto sai pelo mesmo circuito do Chat do Kommo (canal em que o cliente falou,
  como mensagem do bot, com fila e recibo). Também dá para responder direto no Kommo — o botão
  **Abrir no Kommo** leva à conversa. Mensagem de pessoa nunca volta para a IA como se fosse do
  cliente.
- **Devolver à IA** pede o que a IA precisa saber ("remarcada para sábado 10h"): isso vira memória
  daquela conversa. Sem a devolução a IA não volta, nem que o caso fique dias aberto.
- **Encerrar** pede o resultado. Se o cliente escrever de novo depois, começa um ciclo novo com a IA.
- **Cliente escreveu de novo** num caso que você está atendendo: você recebe um push (um a cada 10 min).
- **Atrasado:** caso pendente sem ninguém depois do prazo (urgente 5 min, alta 15, normal 60, baixa
  4 h) — a equipe é avisada de novo a cada 15 min, até 4 vezes. Normal e baixa só no horário humano.
- **"A ponte ainda não confirmou"** ao encerrar ou devolver: a conversa continua com você e a IA
  travada; o sistema tenta de novo a cada meio minuto. Nada a fazer.
- A pausa manual da página do Robô SDR **não** solta uma conversa com caso aberto (o painel recusa):
  quem devolve é o botão do caso.

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
| **fechar a venda** | `POST /ops/api/sales/{id}/close` | `{"service": "Test Drive", "service_date": "2026-10-24", "service_time": "09:00", "amount": 0, "preco_tabela": 0, "pilot_name": "Piloto Exemplo", "pilot_age": 12, "email": "cliente@exemplo.com", "passos": {"cliente": true, "qbo": true, "waiver": true, "asana": true, "kommo": false}, "extras": [{"titulo": "avisar o instrutor", "onde": "painel", "quando": "2026-10-23"}]}` (valores `0` = troque pelo valor real da tabela) | Operador | **sim** |
| refazer um passo | `POST /ops/api/sales/{id}/step/{passo}` | — (`passo`: cliente, qbo, waiver, asana, kommo) | Operador | **sim** |
| tarefa de serviço no Asana (modelo oficial) | `POST /ops/api/tasks` | `{"client_id": 123, "pilot_name": "Piloto Exemplo", "responsible": "Responsável Exemplo", "email": "cliente@exemplo.com", "phone": "+1 407 555 0100", "dob": "2014-05-10", "product": "Test Drive", "category": "4 stroke", "due_on": "2026-10-24"}` | Operador | **sim** |
| enviar waiver avulsa | `POST /ops/api/waivers/send` | `{"template": "parental", "signer_name": "Responsável Exemplo", "signer_email": "cliente@exemplo.com", "service": "Test Drive", "client_id": 123}` | Operador | **sim** |
| reenviar waiver (corrigir e-mail) | `POST /ops/api/waivers/{id}/resend` | `{"email": "novo@exemplo.com"}` | Operador | **sim** |
| aceitar pedido do site | `POST /ops/api/site/agendamentos/{id}/aceitar` | `{}` | Operador | **sim** |
| recusar pedido do site | `POST /ops/api/site/agendamentos/{id}/recusar` | `{"nota": "texto que o cliente vai ler"}` | Operador | **sim** |
| cancelar sessão | `POST /ops/api/site/agendamentos/{id}/cancelar` | `{"nota": "…"}` | Operador | **sim** |
| confirmar sem pagamento e waiver | `POST /ops/api/site/agendamentos/{id}/confirmar` | `{}` | **Gerente** | **sim** |
| responder lead no Kommo | `POST /ops/api/crm/leads/{id}/reply` | `{"text": "texto aprovado pela pessoa"}` | Operador | não (o playbook pede o "pode mandar") |
| anotar no lead | `POST /ops/api/crm/leads/{id}/note` | `{"text": "…"}` | Operador | não |
| ligar lead ao card | `POST /ops/api/crm/leads/{id}/link` | `{"client_id": 123}` | Operador | não |
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
| aprovar invoice proposta pela IA ou fora da tabela | Gerente / dono |
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
7. **Fechar venda**, com `preco_tabela` e o passo Kommo ligado. Confirme com a pessoa.
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
4. Feche com o preço da tabela.

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
3. Passo com `ok: null` e "invoice esperando aprovação do dono": não refaça. Avise a gerência.
4. Nunca chame `close` de novo numa venda que já tem `closing`.

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
4. Precisa de atenção: ligação perdida, waiver parada, pedido do site.

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
| **Não cobrar duas vezes** | antes de fechar, olhe `closing`; `step/qbo` só para passo que falhou; agendamento com invoice não gera outra; depósito à mão só depois de conferir no QuickBooks |
| **Nunca serviço de um cliente no card de outro** | confira o piloto do card antes de vincular; irmão tem card próprio; mover serviço é da gerência |
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
| "QuickBooks: registrar a venda à mão" numa venda do site | o serviço não tem item do QuickBooks ou o item "Security deposit" não está sincronizado: acerte em Serviços e preços / sincronize; a rodada de 15 min tenta de novo |
| "Ganho é o resultado do Fechar venda…" | use Fechar venda, não o botão de etapa |
| "Perdido exige motivo." | mande `motivo` |
| "Cliente não existe." | o `client_id` está errado: busque de novo |
| Waiver: "sem e-mail do responsável" | complete o e-mail na ficha e use **tentar de novo** |
| Waiver: "e-mail do domínio da URACE não é de cliente" | troque pelo e-mail do cliente |
| Waiver: "RECUSADO (trava 1)… waiver válida" | o signatário já tem waiver de menos de 1 ano: não precisa outra |
| Waiver: "RECUSADO (trava 2)… envelope em aberto" | já existe uma enviada e não assinada: use o reenvio (`/waivers/{id}/resend`) |
| Passo "não conectado: …" (QuickBooks, DocuSign, Asana, Kommo) | integração fora do ar: veja Integrações; quando voltar, **tentar de novo** só nesse passo |
| "invoice esperando aprovação do dono" | valor fora da tabela: avise a gerência; não refaça o passo |
| Passo Kommo "feito", mas com a nota "não achei a etapa 'Closed won' neste funil do Kommo" | o lead não se mexeu: mova a etapa à mão no chat ou avise a gerência |
| Site: "a conta do site ainda não está ligada a um card (Client ID)" | Agendamentos do site › Contas de clientes: ligue o driver ao card certo; o painel tenta a invoice de novo |
| Site: "o serviço não tem item do QuickBooks…" | é da gerência: escolher o item em Serviços e preços |
| Site: "o cliente não está no QuickBooks…" | avise a gerência |
| Site: "não achei o item "Security deposit" no QuickBooks…" | avise a gerência (sincronizar o QuickBooks) |
| Site: "o piloto não tem data de nascimento" | o cliente completa o driver na área do cliente, ou peça ao cliente |
| Site: "piloto adulto sem e-mail: ele assina a própria waiver…" | peça o e-mail do piloto e cadastre no driver |
| Site: "Confirmar sem esperar pagamento e waiver é do gerente. Use Aceitar." | use **Aceitar** |
| Chat: "Na fila: o painel insiste…" | espere; em 15 min, se não sair, vira nota no lead e acende o aviso. Use **Enviar de novo** |
| Chat: "Kommo não conectado." | avise a gerência (Integrações) |
| Atendimento: "O caso mudou enquanto você olhava" | outra pessoa assumiu ou fechou antes: recarregue a fila |
| Atendimento: "Só uma pessoa logada assume…" | a chave de API (a IA) abre caso, mas quem assume é gente: entre no painel |
| Atendimento: "Este lead ainda não está no espelho do painel" | responda pelo Kommo (botão **Abrir no Kommo**) |
| Atendimento: aviso "simulado (não saiu)" no WhatsApp | o WhatsApp oficial da equipe ainda não está configurado: o aviso saiu por push e no chat da equipe |
| Atendimento: "Esta conversa está com um atendimento humano aberto" ao reativar a IA no Robô SDR | use **Devolver à IA** no caso |
| Novo cliente: "Esse cliente já existia: abrindo o card dele." | confira se o card é **do mesmo piloto**. Se for irmão, pare e chame a gerência |
| Unir: "Esses dois cards não se unem: …" | são drivers ou contas diferentes do site: não una |
| Nova tarefa: "A data cai numa segunda-feira…" | escolha outra data |
| Nova tarefa: "Piloto menor de idade: o responsável é obrigatório…" | preencha o responsável |
| Google: botão cinza, "O gerente ainda não configurou o acesso ao Google…" | é da gerência: seção 4.8, "Para a gerência" |
| Google: "O arquivo na VPS é de um cliente OAuth do tipo Desktop…" | a gerência cria um cliente do tipo **Aplicativo da Web** e troca o arquivo |
| Google: "A volta do Google não foi aceita…" | o link venceu (10 min), já foi usado ou abriu em outro navegador: toque em Conectar de novo, no mesmo navegador |
| Google: "O Google não deu a permissão de agenda…" | conecte de novo e deixe marcado o acesso ao Google Calendar |
| Google: "O Google recusou a renovação: conecte de novo." | o acesso expirou (no modo Testing, a cada 7 dias) ou foi revogado: **Conectar de novo** |
| Google: "Esta conta não está na lista de testadores" (tela do Google) | o app está em Testing: a gerência põe o seu e-mail em Usuários de teste, ou publica o app |
| Google: "Error 400: redirect_uri_mismatch" (tela do Google) | o redirecionamento do cliente OAuth não está igual a `https://ops.urace.us/ops/api/google/callback`: é da gerência |
