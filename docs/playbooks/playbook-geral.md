# Playbook geral do Command Center — URACE

> **Para quem é:** para todo mundo da URACE que usa o Command Center, e para o Claude de cada
> pessoa.
> **Como usar:**
> - **Pessoa:** leia uma vez de ponta a ponta. Depois, volte à seção de que precisar.
> - **IA (Claude):** cole este arquivo inteiro nas instruções de um Projeto do Claude
>   (claude.ai › Projetos › Instruções do projeto) ou salve como `CLAUDE.md` na pasta em que você
>   abre o Claude Code. A partir daí, o Claude sabe como o painel funciona, o que pode fazer
>   sozinho e o que tem de perguntar antes.
>
> Pedido do dono, 13/10/2026: *"um playbook de como operar dentro do Command Center, que seja
> entendido tanto por IA quanto por um humano, para eu poder estar passando isso para o time"*.
>
> Este é o playbook **geral**. Os detalhes de cada área estão nos outros:
>
> | Área | Playbook |
> |---|---|
> | Vendas (oportunidades, agenda, Kommo, fechamento) | [playbook-vendas.md](playbook-vendas.md) |
> | Box (mecânicos e coaches: Meu dia, checklists, balcão, estoque) | [playbook-mecanicos-e-coaches.md](playbook-mecanicos-e-coaches.md) |
> | Suits · Alpha Line (macacões) | [../suits-guia-do-lucas.md](../suits-guia-do-lucas.md) |
> | Conectar o Claude ao painel (MCP) | [../command-center-mcp-operar.md](../command-center-mcp-operar.md) |
>
> Todos os guias também estão no painel, em **Administrativo › Como usar**, para ler ou baixar; lá fica
> também o **MD para a sua IA**, que junta tudo num arquivo só.
>
> Atualizado em 14/10/2026. Tudo aqui foi conferido no código do painel. Se a tela mudar e este
> texto não, vale a tela; avise quem cuida do painel para corrigir aqui.

---

## Sumário

1. [Para que serve o Command Center](#1-para-que-serve-o-command-center)
2. [Entrar e quem vê o quê](#2-entrar-e-quem-vê-o-quê)
3. [Mapa das telas](#3-mapa-das-telas)
4. [Rotinas do dia](#4-rotinas-do-dia)
5. [Clientes e pilotos](#5-clientes-e-pilotos)
6. [Cada área, em poucas linhas](#6-cada-área-em-poucas-linhas)
7. [A IA no painel](#7-a-ia-no-painel)
8. [Operar pelo Claude (MCP)](#8-operar-pelo-claude-mcp)
9. [Regras que nunca mudam](#9-regras-que-nunca-mudam)
10. [Quando algo dá errado](#10-quando-algo-dá-errado)
11. [Glossário](#11-glossário)
12. [Bloco para a IA](#12-bloco-para-a-ia)

---

## 1. Para que serve o Command Center

O Command Center é a **mesa de operação** da URACE. Ele junta num lugar só o que está espalhado
em Asana, DocuSign, Gmail, QuickBooks e Kommo, e mostra o que precisa de gente.

Três ideias explicam o painel inteiro:

1. **Nada é inventado.** A tela mostra o que foi lido das fontes. Se uma fonte não respondeu, a
   tela diz isso. Não preenche com palpite.
2. **A IA faz o trabalho interno e a pessoa decide o que sai da empresa.** Enviar invoice,
   e-mail, apagar ou anular espera um clique de alguém. Exceções que o dono abriu: a waiver e o
   **lembrete de invoice em aberto** saem sozinhos.
3. **Tudo fica registrado.** Login, comando, aprovação e mudança ficam na **Auditoria**, com o
   nome de quem fez. Esse registro não se apaga.

---

## 2. Entrar e quem vê o quê

### Entrar

1. Abra **https://ops.urace.us/ops/**
2. Entre com o **seu** e-mail e a **sua** senha. Quem cria o usuário é um administrador, na tela
   **Usuários**.
3. "Manter conectado por 30 dias" é opcional. Sem isso, a sessão dura 12 horas.

| Situação | O que acontece |
|---|---|
| Errou a senha 5 vezes em 15 minutos | o acesso trava por alguns minutos ("Too many attempts") |
| Esqueceu a senha | não há autoatendimento: um administrador redefine em **Usuários** |
| Quer trocar a senha | menu do seu nome (canto de cima) › **Minha conta e senha**. Trocar a senha encerra todas as suas sessões |
| Celular | o mesmo endereço. Embaixo aparece a barra de abas |

**Nunca mande senha pelo chat**, nem para colega, nem para a IA.

### Papéis

Todo usuário tem um **papel**. O papel diz o que a pessoa alcança. O servidor confere o papel em
cada ação; o menu só esconde o que não é seu.

| Papel (na tela) | Alcança | Não alcança |
|---|---|---|
| **Acesso livre** | tudo, sem cargo. É a conta do dono | — |
| **Administrador** (`ADMIN`) | tudo: usuários, políticas da IA, integrações, atualizar o sistema | — |
| **Gerente** (`MANAGER`) | tudo do operador + financeiro (QuickBooks, invoices), auditoria e biblioteca | usuários e políticas da IA |
| **Operador** (`OPERATOR`) | o dia a dia **e as vendas**: clientes, serviços, waivers, e-mails, chat, corridas, oportunidades, Suits, balcão e a IA. Aprova o que a IA propõe nesses módulos | financeiro (invoice e QuickBooks), auditoria, usuários, políticas |
| **Leitura** (`VIEWER`) | vê o que a tela mostra | não muda nada |

**Quem vende é operador.** Não existe papel "vendas" (dono, 17/09).

### Cargos do box

Mecânico e coach têm papel de operador, mas com um **cargo** que corta o resto (#92). O cargo
mostra só o que é do box.

| Cargo | Telas |
|---|---|
| **Mecânico** (`MECANICO`) | Meu dia, Balcão, Checklists, Estoque, Pedidos, Compras, Clientes (o card sai sem valores), Equipe, Minha conta |
| **Coach** (`COACH`) | as mesmas do mecânico, por enquanto |

Fora dessas telas, o painel mostra "Esta área não é do seu acesso". Rota nova do sistema nasce
**fechada** para o box: só abre se alguém incluir na lista.

A trava do cargo vale nas três portas: navegador, Claude conectado e chave de API (#201). Por
enquanto, o conector do Claude fica **fechado** para mecânico e coach, porque as ferramentas de
leitura dele alcançam partes do painel que não são do box.

O detalhe do dia do box está no [playbook de mecânicos e coaches](playbook-mecanicos-e-coaches.md).

### Outros endereços

| Endereço | Para quê |
|---|---|
| `ops.urace.us/ops/` | o painel da equipe |
| `parts.urace.us` | **só** o balcão do celular (leitor de peças). Qualquer outra tela responde "Este endereço é só do balcão." |
| `/ops/portal` | a **área do cliente** (outra porta, outro login). Não é o painel da equipe |

---

## 3. Mapa das telas

O menu tem grupos. Um número ao lado do item é um contador (coisas esperando). Fechado, o menu
vira um trilho de ícones; **⌘K** (ou Ctrl+K) abre a busca, que também pergunta à IA.

"Quem usa" é quem vê o item no menu. Uma pessoa de **Leitura** vê alguns itens que, ao abrir,
pedem acesso de operador.

### Menu da equipe (todos menos o box)

| Grupo | Tela | Endereço | Para que serve | Quem usa |
|---|---|---|---|---|
| Hoje | **Hoje** | `/ops/` | a abertura do dia: pista de hoje, o que precisa de gente, o que espera aprovação, waivers abertas, próximos 7 dias, sistemas | todos |
| Hoje | **Precisa de atenção** | `/ops/attention` | a fila do que a IA não resolveu sozinha, do mais grave para o menos | todos |
| Hoje | **Calendário** | `/ops/meu-dia` | o dia, a semana e o mês do box: serviços do Asana, corridas, sessões do site e checklists. Mostra **só o ativo**: serviço cancelado ("CANCELLED - …") ou excluído não aparece. Tudo em **cards**: o treino é o card do cliente; a corrida é um card geral com um card por cliente inscrito | todos |
| Comercial | **Oportunidades** | `/ops/sales` | o quadro de vendas por etapa | operador+ |
| Comercial | **Agenda de vendas** | `/ops/sales/agenda` | os retornos marcados em cada ligação; o cartão **Google Calendar** liga o calendário Google de cada pessoa (os retornos vão para lá e os compromissos dela aparecem aqui). Passo a passo no [playbook de vendas](playbook-vendas.md), 4.8 | operador+ |
| Comercial | **Chat do Kommo** | `/ops/crm/chat` | a conversa do lead dentro do painel | todos |
| Comercial | **Funil do Kommo** | `/ops/crm/funil` | as etapas do funil do Kommo, espelhadas | todos |
| Comercial | **Robô SDR** | `/ops/sdr` | o robô de vendas no Kommo: ligar, instruir, relatar erro | todos |
| Comercial | **Clientes** | `/ops/clients` | um card por pessoa; o card abre em `/ops/clients/<n>` | todos |
| Logística | **Agendamentos do site** | `/ops/site` | os pedidos de sessão da área do cliente, a agenda que abre e fecha, serviços e preços, contas | operador+ |
| Logística | **Corridas** | `/ops/races` | as corridas (coluna RACES do Asana) e o convite aos ★ Pro | todos (criar: operador+) |
| Logística | **Balcão** | `/ops/balcao` | ler a peça e o piloto do dia: cobrar ou guardar | operador+ |
| Logística | **Estoque** | `/ops/estoque` | uma fileira por prateleira; contar, assinalar peça para cliente | todos |
| Logística | **Checklists** | `/ops/checklists` | os checklists do dia, do kart e os trimestrais | operador+ |
| Pedidos e compras | **Pedidos** | `/ops/pedidos` | a lista do que a equipe **precisa** que se compre | todos |
| Pedidos e compras | **Suits · Alpha Line** | `/ops/suits` | os pedidos de macacão sob medida, em dez etapas | operador+ |
| Pedidos e compras | **Compras** | `/ops/compras` | o que a URACE comprou: pedido, envio, chegada. Os e-mails de compra entram sozinhos | todos |
| Pedidos e compras | **Planejamento** | `/ops/planejamento` | peças e corridas: o que vai faltar, e quando | todos |
| IA e inserções manuais | **AI Command** | `/ops/ai` | a conversa com a IA, e o quadro "Falta completar" | todos (mandar comando: operador+) |
| IA e inserções manuais | **Aprovações** | `/ops/approvals` | o que a IA propôs e espera uma pessoa decidir | todos (decidir: operador+) |
| IA e inserções manuais | **Automação e memória** | `/ops/automation` | as rotinas automáticas e o que a IA aprendeu | todos |
| IA e inserções manuais | **Manual dos marcadores** | `/ops/gmail/manual` | como marcar e-mail à mão para a triagem da IA aprender | todos |
| IA e inserções manuais | **O que a IA pode fazer** | `/ops/ai/capabilities` | cada ferramenta da IA e a política dela, lido do código | todos |
| IA e inserções manuais | **Atividade da IA** | `/ops/activity` | tudo o que a IA fez, em ordem | todos |
| Equipe | **Equipe** | `/ops/equipe` | o chat interno (direto ou em grupo), "Conectar o Claude" e o aviso no celular | todos |
| Equipe | **Biblioteca** | `/ops/biblioteca` | os documentos de cada cliente, com o PDF; cópia no Drive | gerente+ |
| Administrativo | **Como usar** | `/ops/como-usar` | os guias do painel para ler ou baixar (.md e PDF) e o **MD para a sua IA**, que junta tudo para o Claude operar o painel com o seu usuário | todos |
| Administrativo | **QuickBooks** | `/ops/quickbooks` | invoices e pagamentos. A IA prepara; enviar pede aprovação | todos veem a tela; financeiro é gerente+ |
| Administrativo | **DocuSign** | `/ops/docusign` | as waivers. Entregue não é assinada; devolvida é e-mail errado | todos |
| Administrativo | **Gmail** | `/ops/gmail` | o que a triagem da IA não decidiu | todos |
| Administrativo | **Asana** | `/ops/asana` | o **espelho** do quadro U-RACE: agenda (TUESDAY a SUNDAY), RACES e Finished Services. Tarefa excluída no Asana sai daqui na sincronia seguinte (até 15 min) e fica no card do cliente como "excluída no Asana" | todos |
| Administrativo | **Integrações** | `/ops/integrations` | o estado de cada sistema; "Verificar agora"; atualizar o sistema | todos (atualizar: administrador) |
| Administrativo | **Auditoria** | `/ops/audit` | o registro imutável de tudo | gerente+ |
| Administrativo | **Políticas da IA** | `/ops/policies` | o que a IA faz sozinha, o que pede confirmação, aprovação ou está bloqueado | administrador |
| Administrativo | **Usuários** | `/ops/users` | criar, desativar, mudar papel e cargo; chaves de API | administrador |
| Administrativo | **Cofre** | `/ops/cofre` | logins e senhas da URACE, cifrados. A IA não tem acesso | só acesso livre |
| (menu do nome) | **Minha conta** | `/ops/account` | trocar a própria senha; quem vende também conecta o próprio Google Calendar aqui | todos |

### Menu do box (mecânico e coach)

Meu dia (é a tela inicial) · Balcão · Checklists · Estoque · Pedidos · Clientes · Equipe.
Detalhe no [playbook de mecânicos e coaches](playbook-mecanicos-e-coaches.md).

### A barra de cima (em toda tela)

Quatro cápsulas mostram o estado da operação. Cada uma leva para onde se resolve:

| Cápsula | Diz | Leva para |
|---|---|---|
| **Espelho** | há quanto tempo os dados foram lidos das fontes | Hoje |
| **Sistemas** | quantos sistemas estão respondendo | Integrações |
| **Atenção** | quantos itens precisam de gente, e quantos críticos | Precisa de atenção |
| **IA** | quantas ações esperam você | Aprovações |

Se aparecer **Offline**, o aparelho está sem internet. **Servidor fora**: o painel não respondeu.

### Endereços antigos

`/ops/vendas` vai para `/ops/sales`; `/ops/crm` e `/ops/kommo` vão para o Chat do Kommo;
`/ops/tasks` para Asana; `/ops/waivers` para DocuSign; `/ops/emails` para Gmail.

---

## 4. Rotinas do dia

### O que o sistema faz sozinho

Estes são os horários **padrão**, no fuso da Flórida. Um administrador pode ligar e desligar
cada rotina em **Automação e memória**.

| Quando | Rotina |
|---|---|
| a cada 15 minutos | o espelho lê de novo as fontes (Asana, DocuSign, Gmail, QuickBooks) |
| a cada 15 minutos | a ponte de e-mail dos Suits lê o Gmail `urace@` (ver o [guia de Suits](../suits-guia-do-lucas.md)) |
| 06:00 | varre Gmail e DocuSign de cada cliente ativo e liga o que achar ao card |
| 07:00, 13:00, 21:00 | triagem do Gmail pela IA: marca e move para o marcador principal |
| 07:00, 22:00 | testa cada integração com uma chamada real |
| 07:30 | lê a Rate Card no Drive e aplica os preços no QuickBooks |
| 08:10 | confere a conversa de cada lead no Kommo contra a do painel |
| 09:00 | lembrete das invoices em aberto que têm lembrete ligado e dia chegado |
| 09:00, 16:00 | aviso no celular de cada pessoa com o que ela ainda precisa completar ("Falta completar") |

### Abertura (equipe)

1. **Hoje** (`/ops/`): pista de hoje, "Precisa de gente", "Esperando você", waivers abertas.
   Se o aviso "Espelho antigo" aparecer, clique em **↻ Sincronizar** (operador+).
2. **Precisa de atenção**: comece pelo crítico. Cada item tem um botão para abrir a origem
   (cliente, inbox, estoque, compras, agenda, aprovações...) e **✦ Instruir a IA**.
3. **Aprovações**: decida o que a IA propôs. Cada proposta mostra a prévia do que vai acontecer.
4. **AI Command › Falta completar**: registros que a IA criou com informação faltando e que você
   pediu. Complete e toque em **Completei**.
5. **Equipe**: mensagens não lidas (o número no menu).
6. Vendas: **Agenda de vendas** do dia. Detalhe no [playbook de vendas](playbook-vendas.md).

### Abertura (box)

**Meu dia** é a tela inicial do mecânico e do coach: os serviços, as corridas e as sessões
marcadas pelo site no dia, com o checklist de cada um. Detalhe no
[playbook de mecânicos e coaches](playbook-mecanicos-e-coaches.md).

### Durante o dia

| Aconteceu | Onde |
|---|---|
| cliente novo, ou cliente que já existe | **Clientes** (ver seção 5) |
| peça usada ou entregue | **Balcão** |
| falta peça | **Pedidos** (o pedido); quem compra junta em **Compras** |
| lead conversando | **Chat do Kommo** |
| pedido de macacão | **Suits · Alpha Line** |
| pedido de sessão pelo site | **Agendamentos do site** |
| preciso que a IA faça algo | **AI Command**, ou **✦ Instruir a IA** no item de atenção |
| conversa com colega | **Equipe** (o que é de cliente fica no Chat do Kommo) |

### Fechamento (sugestão de conferência)

O painel não tem um botão de "fechar o dia". Antes de sair, vale conferir:

1. **Precisa de atenção** sem crítico esquecido.
2. **Aprovações** sem proposta sua parada.
3. **Falta completar** com o que você já conseguiu completar marcado como **Completei**.
4. Box: os checklists do dia preenchidos em **Meu dia**.
5. Vendas: os retornos de amanhã na **Agenda de vendas**.

---

## 5. Clientes e pilotos

### O card do cliente

Clientes (`/ops/clients`) tem **um card por pessoa**, do serviço mais recente para o mais
antigo. **Ativo** é quem teve serviço nos últimos 6 meses. O **piloto** aparece em destaque; o
**responsável** (quem paga e assina) fica ao lado.

Dentro do card (`/ops/clients/<n>`), as abas:

| Aba | O que tem |
|---|---|
| Linha do tempo | serviço, waiver enviada/assinada, ação da IA, invoice |
| Mensalidade e contrato | plano mensal e contrato da Academy (valor: gerente+) |
| ★ Equipamento e ★ Corridas | só para Pro Racing Driver |
| Peças | o QR que o mecânico lê no balcão e as peças do cliente |
| Conta no site | a conta da área do cliente ligada ao card |
| Serviços | as tarefas do Asana do cliente: **Renomear** (operador+), **Mover** (gerente+) |
| Waivers | os envelopes do DocuSign e as assinadas no sistema, com o PDF assinado; no topo, o **Convite da waiver por e-mail** (abaixo) |
| E-mails | os e-mails ligados ao card |
| Invoices | só gerente e administrador (para os outros, aparece 🔒) |
| IA | o que a IA propôs para este cliente |

O box vê o card **sem valores**: não aparecem mensalidade, corridas, conta no site, e-mails,
invoices nem IA.

#### Convite da waiver por e-mail (#135)

Dono, 14/10: *"vai ser por e-mail para o adulto ou para o responsável assinar aquela waiver. Tanto
para adulto quanto para responsável, o e-mail que tiver no card vai receber isso."*

1. No card, aba **Waivers** (ou o botão **✉ Convite por e-mail** no quadro Waiver do topo).
2. O quadro diz **para quem vai**: piloto com **18 anos ou mais** (pela data de nascimento do
   piloto no card) assina a **própria** waiver (adult); **menor**, o **responsável** (o nome do
   card) assina por ele (parental, pai ou mãe). O e-mail é sempre o **e-mail do card**.
3. **Enviar convite da waiver por e-mail** → a janela mostra nome e e-mail → **Enviar**.
4. A pessoa recebe um link **pessoal**, que vale **uma vez** e vence em **72 horas**. Ele abre a
   assinatura do próprio sistema **sem conta e sem login**, já presa àquele card e piloto. Na hora
   de assinar chega um **código de 6 dígitos** no mesmo e-mail.
5. Assinou: a waiver aparece na aba Waivers como as outras ("área do cliente"), com o PDF e o
   certificado, e o convite fica **assinado**.

Situação de cada convite: **enviado** · **aberto** (a pessoa abriu o link) · **assinado** ·
**expirado** (passou das 72 h) · **substituído** (você reenviou; o link velho não vale mais) ·
**não saiu** (o Gmail não mandou: tente de novo). **Reenviar** manda um link novo. Tudo fica na
Auditoria (`waiver.invite.*`).

O botão fica **desligado, com o motivo escrito**, quando: o card não tem e-mail; o card não tem a
data de nascimento do piloto; o piloto é menor e o card não tem o responsável; o e-mail é da URACE;
ou a assinatura no próprio sistema está desligada (Agendamentos do site › Waiver). Se o card mudar
de e-mail ou de data de nascimento depois do envio, o link para de valer: reenvie.

### Um card por piloto

Dono, 01/10 (#65): **cada driver tem o seu card.** Irmãos costumam ter o mesmo responsável,
e-mail e telefone; mesmo assim, cada um tem o próprio card. O painel recusa unir cards ligados a
drivers diferentes do site ("Esses dois cards não se unem: são de drivers diferentes no site").

### Nunca pôr serviço de um cliente no card de outro

Dono, 22/09: *"Nunca colocar serviço de outro cliente em card de outro cliente."* Na dúvida, card
próprio. Para confirmar que é a mesma pessoa, use **e-mail, telefone ou responsável iguais**.
Primeiro nome parecido é só suspeita.

| Caso | O que fazer |
|---|---|
| serviço caiu no card errado | no card, aba Serviços › **Mover** (gerente+) e escolha o cliente certo |
| serviço que não devia estar no calendário | Calendário › no serviço, **Excluir** (gerente+ e acesso livre), com o motivo. Some do calendário, do balcão, dos contadores e dos avisos, e a IA não age mais nele. No card, aba Serviços, continua como **excluído** (quem, quando, por quê), com **Restaurar**. No Asana nada muda; a auditoria guarda `task.deleted` e `task.restored` (#219) |
| dois cards da mesma pessoa | Clientes › **⧉ Unir dois clientes**. O registro unido fica guardado e auditado |
| pares com nome quase igual | Clientes › **Possíveis duplicados**; dá para pedir o parecer da IA. A decisão é humana |

### "Vincular ao cliente" em toda inserção manual

Dono, 08/10 (#158): todo formulário que cria registro à mão tem o seletor de cliente. Ele grava o
vínculo e **puxa do cadastro** o que já existe (nome, e-mail, telefone, piloto, endereço,
medidas). Hoje o seletor aparece, por exemplo, em:

- **Suits** › Registrar novo pedido: "Vincular ao cliente (puxa os dados do cadastro)";
- **Oportunidades** › nova oportunidade: "Já é cliente? Vincular ao cliente";
- **Balcão**, **Estoque** e **Pedidos**: o cliente dono da peça, ou "para o kart de".

Regra prática: **antes de digitar dados de alguém, procure o card.** Se existir, vincule. Se não
existir, crie o cliente em Clientes › **+ Novo cliente** (o painel avisa quando ele já existe e
abre o card dele).

---

## 6. Cada área, em poucas linhas

| Área | Em uma frase | Onde ir |
|---|---|---|
| **Vendas** | oportunidade por etapa, ligação registrada, retorno na agenda, fechamento numa tela só (cliente, invoice, waiver, Asana, Kommo) | [playbook-vendas.md](playbook-vendas.md) |
| **Box** | Meu dia, checklists com foto, balcão (cobrar ou guardar peça), estoque, pedidos e compras | [playbook-mecanicos-e-coaches.md](playbook-mecanicos-e-coaches.md) |
| **Suits · Alpha Line** | pedido de macacão sob medida, das 29 medidas e do design até a entrega, com a ponte de e-mail | [../suits-guia-do-lucas.md](../suits-guia-do-lucas.md) |
| **Corridas** | a coluna RACES do Asana; convidar os ★ Pro, que ficam na corrida até confirmar | tela Corridas |
| **Agendamentos do site** | os pedidos de sessão que chegam pela área do cliente, e a agenda que abre e fecha | tela Agendamentos do site |
| **Waivers** | DocuSign: baixar PDF assinado, reenviar corrigindo e-mail, lixeira. Entregue não é assinada. **Convite por e-mail** para assinar no próprio sistema, do card do cliente | tela DocuSign · card › Waivers |
| **Gmail** | a IA marca e move 3 vezes ao dia; o que ela não decidiu fica aqui. Ela só usa marcador do manual confirmado | tela Gmail |
| **Financeiro** | invoices, lembretes e catálogo no QuickBooks. A conta é do **responsável**, nunca do piloto | tela QuickBooks (gerente+) |

### Suits: duas novidades

- **"Não é pedido de suit"**: botão no pedido para **descartar** o que não é pedido de macacão
  (fatura, newsletter, conversa com fornecedor...). Nada é apagado: o pedido sai das listas, a
  ponte para de ler aquela conversa, e dá para **restaurar**.
- **Chave "IA neste pedido"** (#198, 13/10): liga e desliga a IA só
  naquele pedido. Desligada, a IA não responde, não manda e-mail e não mexe no pedido; o e-mail
  que chegar aparece como "Precisa de alguém da equipe" e quem responde é a equipe. Use quando o
  cliente pede atendimento humano ou a negociação está delicada.

Detalhe e rotinas no [guia de Suits](../suits-guia-do-lucas.md).

---

## 7. A IA no painel

### Onde falar com a IA

| Lugar | Como |
|---|---|
| **AI Command** (`/ops/ai`) | uma conversa contínua, por pessoa. Enter envia; Shift+Enter quebra a linha; microfone dita; **Ouvir** lê a resposta |
| **✦ Instruir a IA** | em cada item de **Precisa de atenção**. Dá para marcar "guardar na memória da IA" |
| **⌘K** | a busca de cima também pergunta à IA |
| dentro de uma oportunidade, de uma tarefa do Asana ou de um pedido de Suits | a caixa da IA age só naquele registro |

Mandar comando à IA exige papel de operador ou acima.

### O que a IA faz sozinha e o que espera você

| Tipo | Exemplos | O que acontece |
|---|---|---|
| **Ler** | QuickBooks, Asana, Gmail, DocuSign, Kommo, o painel, a web, o cérebro da empresa | faz direto |
| **Trabalho interno** | tarefa, comentário e seção no Asana; cliente, item, invoice e estimate no QuickBooks **sem enviar**; rascunho de e-mail; marcador no Gmail | faz direto e registra como ação feita |
| **Sai da empresa ou não volta atrás** | enviar invoice, lembrete de invoice já paga ou e-mail; apagar; anular; unir cards; mudar preço do catálogo; pagamento; recorrência | **não executa**: vira um "aprovar" de um clique em **Aprovações** |
| **Bloqueado pela política** | o que estiver como `BLOCKED` em Políticas da IA | não roda, nem com aprovação |

A **waiver** é a exceção que o dono abriu: enquanto a política dela estiver em "sozinha" (SAFE),
ela sai na hora. O **convite da waiver por e-mail** (`painel_waiver_convite`, #135) **não** é
exceção: pela IA ele espera o aprovar; pelo painel, é o clique de quem manda (com a confirmação). A política de cada ação está em **Políticas da IA** (administrador muda) e em
**O que a IA pode fazer** (todos veem). **Não decore**: a política pode mudar; confira lá.

O **lembrete de invoice** também sai sozinho (dono, 14/10, #230): quando a IA manda o lembrete e o
QuickBooks, lido na hora, mostra a invoice **em aberto** (com saldo), o lembrete vai sem clique, e o
painel marca o próximo dia. Se a invoice já está paga, se não há como conferir ou se a política do
lembrete foi apertada em Políticas da IA, volta o clique.

Ação que não tem política própria pede confirmação. Qualquer ação com "apagar", "excluir",
"remover" no nome tem, no mínimo, a política de "apagar qualquer coisa": o sistema erra para o
lado de perguntar.

### Quem aprova

| Papel | Decide |
|---|---|
| Acesso livre, administrador, gerente | tudo |
| Operador | o que é dos módulos dele (inclui vendas). **Invoice e QuickBooks, não** |
| Leitura | nada |

Aprovar executa na hora e fica na auditoria. Recusar registra o motivo.

### "Falta completar" (pedido incompleto)

Dono, 12/10 (#185): a IA **não trava** por falta de informação.

1. Procura antes: painel, QuickBooks, Kommo, Gmail e o cérebro.
2. **Cria com o que tem** e deixa a lacuna visível no próprio registro ("horário: a confirmar").
   Nunca inventa o que falta.
3. Registra uma **pendência**: o que criou, onde está, o que falta e o contato que achou.
4. Avisa você: "Criei X. Falta: A, B. Contato para pedir: …".
5. A pendência aparece no topo do **AI Command** ("Falta completar") e em **Precisa de atenção**,
   e você recebe aviso no celular às 09:00 e 16:00 até completar.
6. Mande o dado na conversa ou complete no registro e toque em **Completei**. E-mail, telefone,
   nome ou nascimento do piloto **fecham sozinhos** quando alguém preenche o card.

A IA só para sem criar quando criar causaria dano: cobrar ou enviar sem o valor ou o
destinatário certo, ou quando não dá para saber de quem é o pedido.

### Para ligar o aviso no celular

**Equipe** › **Ligar notificação neste aparelho**. No iPhone, antes, instale o painel na tela
inicial (Compartilhar › Adicionar à Tela de Início) e abra por esse ícone.

---

## 8. Operar pelo Claude (MCP)

Cada pessoa pode ligar o **próprio** Claude ao painel. O Claude passa a agir **como você**, com o
**seu** papel, e tudo fica na auditoria com o seu nome. O passo a passo também está no painel, em
**Equipe › Conectar o Claude**. Detalhe em [command-center-mcp-operar.md](../command-center-mcp-operar.md).

### Conectar (uma vez)

**No app do Claude (claude.ai, celular ou computador):**

1. Configurações › **Conectores** › **Adicionar conector personalizado**.
2. Nome: `URACE Command Center`. URL: `https://ops.urace.us/ops/mcp`
3. **Conectar**, entre com o **seu** usuário do painel, deixe marcado
   **"Também operar o painel como você"** e clique em **Autorizar**.

**No terminal (Claude Code):**

```
claude mcp add --transport http urace https://ops.urace.us/ops/mcp
```

Depois, no Claude Code, digite `/mcp`, escolha **urace** e **Authenticate**. Entre e marque
**"Também operar o painel como você"**.

Sem a caixa marcada, o Claude **só lê**. Ninguém copia senha, token ou chave para o chat: o login
é pelo navegador.

### As ferramentas

| Ferramenta | Para quê |
|---|---|
| `urace_resumo` | o panorama |
| `urace_atencao` | o que precisa de gente hoje |
| `urace_clientes`, `urace_cliente`, `urace_corridas`, `urace_estoque`, `urace_invoices`, `urace_precos_cobrados`, `urace_auditoria`, `urace_kommo_*` | leituras prontas |
| `urace_operacoes` | lista **as operações que o seu papel alcança**. Filtre com uma palavra: `venda`, `waiver`, `invoice`, `suits`... |
| `urace_api` | executa uma operação (método, caminho, corpo). É a **mesma rota** do botão do painel |

### Confirmação antes de mandar para fora

O que vai para o cliente ou cobra (invoice, waiver, e-mail, QuickBooks, DocuSign, Asana, Kommo,
agendamento do site) **não acontece na primeira chamada**. O painel devolve `precisa_confirmar`
com o que vai fazer. O Claude mostra para você e só repete com `confirmar: true` depois do seu
"pode mandar".

Ficam fora do MCP: login, senha e chaves (`/ops/api/auth/*`) e a área do cliente
(`/ops/api/portal/*`).

---

## 9. Regras que nunca mudam

Regras do dono. Valem para pessoa e para IA, em toda tela e em todo canal.

1. **Não destruir dados.** Não apagar banco, cliente ou registro. O que não serve é **ocultado**,
   **descartado** ou vai para a **lixeira**, sempre reversível. Risco real de perda ou de sistema
   fora do ar: pedir autorização antes.
2. **Nunca pedir nem mandar senha, token, PIN ou chave pelo chat.** O login é pelo navegador.
3. **Segredo nunca no código nem no repositório.**
4. **Nunca pôr serviço de um cliente no card de outro.** Na dúvida, card próprio.
5. **NO FAKE DATA.** Nunca inventar nome, e-mail, telefone, valor, data, id ou link. Faltou:
   procure; não achou, diga que não achou e pergunte.
6. **Não usar Turo nem Hostaway** para nada.
7. **Tudo no fuso da Flórida** (America/New_York).
8. **Na dúvida, perguntar.** A pergunta não trava o resto: o item fica em espera e o trabalho
   segue. Item em espera com prazo chegando volta a ser alertado.
9. **Inserção manual sempre com "Vincular ao cliente".**
10. **O que sai da empresa passa por uma pessoa**, conforme a política da ação.

---

## 10. Quando algo dá errado

| Sintoma (o que aparece) | O que quer dizer | O que fazer |
|---|---|---|
| "Esta área não é do seu acesso" / "Ela exige acesso de … ou acima" | a tela pede um papel acima do seu | peça a quem tem o papel, ou fale com o administrador |
| "Ela não faz parte do acesso do box" | mecânico/coach fora das telas do box | use as telas do box; se precisa de outra, fale com o administrador |
| "You don't have permission to do this." | a ação pede um papel acima do seu | peça a um gerente ou administrador |
| "Your session has expired." | a sessão acabou (12 h, ou 30 dias com "manter conectado") ou a senha foi trocada | entre de novo |
| "Invalid email or password." | e-mail ou senha errados | confira; esqueceu, peça ao administrador para redefinir |
| "Too many attempts. Try again in a few minutes." | 5 erros em 15 minutos | espere alguns minutos |
| "Invoice e QuickBooks são decisão do gerente ou do administrador." | operador tentando aprovar proposta financeira | peça a um gerente |
| "This action is blocked by policy and cannot be approved." | a política da ação é BLOCKED | não há como aprovar; fale com o dono se for o caso de mudar a política |
| "Esses dois cards não se unem: …" | cards de drivers ou contas diferentes do site | não una; cada driver tem o seu card |
| "Essa recorrência já está vinculada ao card de outro cliente." | tentativa de ligar a mensalidade de um cliente ao card de outro | confira o cliente certo |
| "Este endereço é só do balcão." | você está em `parts.urace.us` | para o resto do painel, use `ops.urace.us/ops/` |
| Cápsula **Espelho** em amarelo/vermelho ou "Espelho antigo" | dados não lidos há tempo | Hoje › **↻ Sincronizar** |
| Cápsula **Sistemas** com problema | uma integração não respondeu | Integrações › **Verificar agora**; se persistir, avise o administrador |
| **Offline** / **Servidor fora** | sem internet / painel não respondeu | confira a internet; se for o servidor, avise o administrador |
| Notificação não chega no celular | permissão negada ou iPhone sem o painel na tela inicial | Equipe › ligar notificação; siga o aviso da tela |
| **Pelo Claude:** "este acesso é só de leitura" | conectou sem marcar a caixa | conecte de novo e marque "Também operar o painel como você" |
| **Pelo Claude:** "isto é do papel MANAGER ou acima; você é OPERATOR" | a rota pede papel acima do seu | peça a um gerente |
| **Pelo Claude:** `precisa_confirmar` | vai sair da empresa ou cobrar | mostre à pessoa e repita com `confirmar: true` só depois do "pode mandar" |
| **Pelo Claude:** "… não existe no painel (veja urace_operacoes)" | caminho errado | procure a operação certa com `urace_operacoes` |
| **Pelo Claude:** "login, chaves e área do cliente não são operados pelo MCP" | rota fora do MCP | faça pelo painel |
| Chave de API: "Esta chave é só de leitura" | a chave está como só leitura | o administrador, em Usuários › Chaves de API, toca em **Liberar para operar** (a chave continua a mesma; #209) |

---

## 11. Glossário

| Termo | O que é |
|---|---|
| **Card** | a ficha de um cliente no painel (`/ops/clients/<n>`) |
| **Piloto / driver** | quem pilota. Cada driver tem o seu card |
| **Responsável** | quem paga e assina (às vezes o pai ou a mãe do piloto). A conta do QuickBooks é dele |
| **Pro Racing Driver (★ Pro)** | piloto pronto para competir; libera equipamento e corridas no card |
| **Serviço** | uma tarefa do quadro U-RACE no Asana (coaching, academy, trackside...) |
| **Waiver** | o termo de responsabilidade do DocuSign. Parental se o piloto é menor; adulto se não. Sem ela assinada, o piloto não entra na pista |
| **Invoice** | a cobrança no QuickBooks |
| **Estimate** | o orçamento no QuickBooks (ex.: preparação de corrida) |
| **Security deposit** | o depósito do serviço, cobrado depois que a invoice do serviço é paga |
| **Rate Card** | a tabela de preços oficial; manda acima do catálogo |
| **Oportunidade** | uma venda em andamento. Não é cliente até fechar |
| **Lead** | contato que chegou pelo Kommo |
| **Closer** | quem fecha a venda. Não é um papel do sistema: é operador |
| **Balcão** | a tela de ler QR do cliente e das peças: cobrar (vai para a invoice de peças do dia, não é enviada sozinha) ou guardar (estoque do cliente) |
| **Ponte (de e-mail)** | a rotina que lê o Gmail a cada 15 minutos e leva cada novidade de Suits para a IA |
| **Espelho** | a cópia, no painel, do que está nas fontes (Asana, DocuSign, Gmail, QuickBooks, Kommo) |
| **Precisa de atenção** | a fila do que a IA não resolveu sozinha |
| **Aprovação** | proposta da IA que espera uma pessoa decidir |
| **Pendência / Falta completar** | registro criado com informação faltando, até alguém completar |
| **Política** | a regra de cada ação da IA: sozinha (SAFE), confirmação, aprovação ou bloqueada |
| **Box** | mecânicos e coaches |
| **Meu dia** | a tela inicial do box: serviços, corridas e sessões do dia, com checklist |
| **Área do cliente / portal** | o site do cliente (`/ops/portal`), separado do painel da equipe |
| **Cérebro** | a memória da empresa (`brain/` no repositório): processos, clientes, regras |
| **MCP** | o jeito de ligar o Claude de cada pessoa ao painel |
| **Auditoria** | o registro imutável de tudo o que foi feito, e por quem |

---

## 12. Bloco para a IA

> Esta seção é para o Claude. Uma pessoa pode pular.

### Quem você é aqui

Você trabalha com uma pessoa da URACE (kart racing em Orlando) e opera o Command Center **como
ela**, com o papel dela, pelo MCP `https://ops.urace.us/ops/mcp`. Tudo o que você faz fica na
auditoria com o nome dela.

### Como trabalhar

1. **Comece pelo panorama:** `urace_resumo` e `urace_atencao`.
2. **Descubra antes de agir:** `urace_operacoes` com uma palavra (`clients`, `sales`, `suits`,
   `waiver`, `invoice`...). Ela só lista o que o papel da pessoa alcança. Não chute rota.
3. **Leia antes de perguntar:** procure o cliente (`GET /ops/api/clients?q=…`), o pedido, a
   oportunidade. Muitas vezes só o nome basta para achar e-mail e telefone.
4. **Antes de criar, procure o card.** Achou, use o `client_id`. Nunca grave dado de uma pessoa
   no registro de outra.
5. **O que sai da empresa ou cobra:** a primeira chamada devolve `precisa_confirmar`. Mostre à
   pessoa o que vai acontecer e só repita com `confirmar: true` depois do "pode mandar" dela.
   Não procure outro caminho para pular a confirmação.
6. **Erro de papel:** diga qual papel precisa e pare. Não tente outra rota para contornar.
7. **Faltou dado:** não invente. Diga o que falta, de forma curta, e o que você já fez.
8. **Responda em português do Brasil, direto, frases curtas.** No fim: o que você fez (uma linha
   por coisa, com link quando houver) e o que ficou esperando a pessoa.

### Rotas que você vai usar com frequência

Todas com prefixo `/ops/api`. Papel mínimo entre parênteses ("logado" = qualquer papel).

| Para | Método e caminho |
|---|---|
| panorama do dia | `GET /dashboard` (logado) |
| fila de atenção | `GET /needs-attention` (logado) |
| instruir a IA do painel sobre um item | `POST /needs-attention/instruct` (operador) |
| ocultar / restaurar um aviso (não apaga a origem) | `POST /needs-attention/dismiss` · `POST /needs-attention/restore` (operador) |
| buscar | `GET /search?q=…` (logado) |
| listar / abrir cliente | `GET /clients?q=…` · `GET /clients/{id}` (logado) |
| criar cliente (se já existir, devolve o existente) | `POST /clients` (operador) |
| editar cliente | `PATCH /clients/{id}` (operador) |
| unir dois cards | `POST /client-merge` (operador; recusa drivers diferentes do site) |
| mover serviço para o card certo | `POST /tasks/{id}/cliente` (gerente, pelo botão "Mover" do card) |
| criar serviço (tarefa do Asana pelo modelo oficial) | `POST /tasks` (operador) |
| enviar waiver avulsa | `POST /waivers/send` (operador) |
| convite da waiver por e-mail: para quem vai e os já mandados | `GET /clients/{id}/waiver-invite` (operador) |
| mandar / reenviar o convite | `POST /clients/{id}/waiver-invite` com `{"email": "<o e-mail do card>"}` (operador; o e-mail confere com o card) |
| dia do box | `GET /meu-dia` (operador; é a tela inicial do mecânico e do coach) |
| mandar comando à IA do painel | `POST /ai/commands` (operador) |
| propostas esperando decisão | `GET /ai/actions?status=PROPOSED` (logado) |
| aprovar / recusar proposta | `POST /ai/actions/{id}/approve` · `POST /ai/actions/{id}/reject` (operador; financeiro só gerente+) |
| pendências "Falta completar" | `GET /ai/pendencias` (logado; `todas=true` para gerente) |
| marcar pendência como completa | `POST /ai/pendencias/{id}/resolver` (operador; quem pediu ou gerente) |
| o que a IA pode fazer e a política | `GET /ai/capabilities` (logado) |
| Suits: descartar / restaurar | `POST /suits/{id}/descartar` com `{"motivo": "…"}` · `POST /suits/{id}/restaurar` (operador) |
| Suits: ligar/desligar a IA no pedido (#198) | `POST /suits/{id}/ia` com `{"ligada": false}` (operador) |

As rotas de vendas, do box e de Suits estão nos playbooks de cada área (links no topo).

### Limites que você respeita sempre

- Você **não** tem acesso ao Cofre, a login, senha e chaves, nem à área do cliente.
- Você **nunca** pede senha, token, PIN ou chave. Se a pessoa colar um, diga para não fazer isso
  e não repita o valor.
- Você **nunca** apaga. Para tirar algo do caminho: ocultar, descartar ou lixeira, e só com o OK
  da pessoa.
- Pedido de Suits com a IA desligada (`ia_ligada = 0`): não proponha e-mail nem mudança de etapa
  por conta própria; mostre o que chegou e pergunte.
- Datas e horas em America/New_York.
- Nada de Turo nem Hostaway.
- Resposta 200 de uma API externa não é prova de que algo aconteceu: confira no registro.

### Onde ler mais

- Processos da empresa: `brain/10_PROCESSOS/` (índice em `Processos.md`).
- Decisões do dono e o porquê: `brain/08_DECISOES/`.
- Manual técnico: `docs/manual-do-command-center.md`.
