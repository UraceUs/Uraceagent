# Modelos de mensagem do WhatsApp (templates) — URace × Kommo

Guia operacional para criar, submeter à Meta e usar os modelos que permitem
falar com um lead **depois** que a janela de 24 horas fechou.

---

## 1. Por que isto existe

O WhatsApp Business API tem uma regra que não depende de plano, de selo nem de
verificação: **a janela de 24 horas.**

| Situação | O que você pode enviar |
|---|---|
| O lead te mandou mensagem há menos de 24h | Qualquer texto livre |
| Passaram-se mais de 24h desde a **última mensagem do lead** | Somente modelo aprovado pela Meta |
| O lead responde ao modelo | A janela reabre por mais 24h — volta o texto livre |

Os erros que aparecem no Kommo quando se tenta texto livre fora da janela são
tipicamente `131047` (reengajamento fora da janela) e `131026` (mensagem não
entregável). Não são erro de configuração da conta.

**Meta Verified não muda nada disso.** É uma assinatura de selo, suporte e
proteção de marca. O que afeta volume é a *Business Verification* (verificação
da empresa no Gerenciador de Negócios, gratuita), que eleva o limite de
conversas iniciadas pela empresa a partir do teto inicial de 250/dia. A janela
de 24h continua valendo nos dois casos.

Isto é a mesma regra que o agente já respeita em `prompts/modes/followup.md`
("Hard stops — the channel's messaging window rules don't allow it"). Este
documento é o que destrava esse caso: com modelos aprovados, o follow-up fora
da janela deixa de ser proibido e passa a ser "enviar o modelo certo".

---

## 2. As três categorias da Meta

| Categoria | Para que serve | Aprova fácil? | Custo |
|---|---|---|---|
| `UTILITY` | Acompanhar algo que o lead pediu ou combinou: confirmação, lembrete, retorno de ligação, orçamento solicitado | Sim, quando o texto é claramente transacional | Mais barato; grátis se enviado dentro de janela aberta |
| `MARKETING` | Reengajar, retomar conversa parada, oferta, convite | Sim, mas exige opt-in e conta no limite de marketing por usuário | Mais caro |
| `AUTHENTICATION` | Código de verificação | Não usamos | — |

**Regra prática:** se a mensagem só faz sentido porque existe um compromisso
concreto (uma visita marcada, um orçamento pedido, um retorno combinado), é
`UTILITY`. Se ela serve para acordar alguém que sumiu, é `MARKETING`. Classificar
um reengajamento como `UTILITY` para pagar menos é o caminho mais rápido para
reprovação — e a Meta reclassifica sozinha quando discorda.

---

## 3. Regras que reprovam um modelo

Antes de submeter, confira cada item:

1. **Nome** só com letras minúsculas, números e underline: `reengage_inquiry_v1`.
2. **Variável nunca no começo nem no fim do corpo.** `{{1}}, tudo bem?` reprova.
   `Oi {{1}}, tudo bem?` passa.
3. **Nunca duas variáveis coladas** (`{{1}} {{2}}`). Sempre com texto entre elas.
4. **Numeração sequencial** a partir de `{{1}}`, sem pular número.
5. **Exemplo de preenchimento obrigatório** para cada variável, no momento da
   submissão. Sem exemplo, reprova por incompletude.
6. **Limites:** cabeçalho 60 caracteres, corpo 1024, rodapé 60.
7. **Sem promessa de resultado, sem urgência falsa, sem preço enganoso.** Preço
   em modelo é permitido, mas tem que ser verdadeiro e não pode ser a isca
   principal de um `UTILITY`.
8. **Um idioma por modelo.** O mesmo nome pode ter versões `en_US`, `pt_BR` e
   `es_ES` — são submissões separadas sob o mesmo nome.
9. **Sem link encurtado** de domínio genérico (bit.ly e similares) — use o
   domínio da URace.

Aprovação costuma sair em minutos; o prazo formal da Meta é de até 24 horas.

---

## 4. Os modelos

Todos escritos primeiro em `en_US` (público principal, Orlando) com as versões
`pt_BR` e `es_ES` logo abaixo. Copie o texto exatamente como está.

### 4.1 `reengage_inquiry_v1` — reabertura geral

**Categoria:** MARKETING · **Idiomas:** en_US, pt_BR, es_ES

- Corpo (en_US):
  ```
  Hi {{1}}, it's the URace Karting team in Orlando. You reached out about getting on track with us and we never got to finish the conversation. Still thinking about it? Reply here and I'll pick it up from where we stopped.
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, aqui é a equipe da URace Karting, em Orlando. Você entrou em contato com a gente sobre andar de kart e a conversa acabou ficando pela metade. Ainda tem interesse? É só responder aqui que eu retomo de onde a gente parou.
  ```
- Corpo (es_ES):
  ```
  Hola {{1}}, somos el equipo de URace Karting en Orlando. Nos escribiste sobre entrar a la pista y la conversación quedó a medias. ¿Sigues interesado? Responde aquí y la retomamos donde la dejamos.
  ```
- Variáveis: `{{1}}` = primeiro nome do lead. Exemplo: `Marcos`
- Rodapé: `Reply STOP to opt out.`
- Botões: resposta rápida `Yes, let's talk` · resposta rápida `Not right now`

> Os botões de resposta rápida são o ponto mais importante deste modelo: um
> toque do lead reabre a janela de 24h e devolve o texto livre ao agente.

### 4.2 `reengage_missing_info_v1` — falta um dado da qualificação

**Categoria:** MARKETING · **Idiomas:** en_US, pt_BR

- Corpo (en_US):
  ```
  Hi {{1}}, quick one from URace Karting so I can point you the right way: {{2}} Just reply here whenever you have a second.
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, uma pergunta rápida da URace Karting pra eu te indicar o caminho certo: {{2}} É só responder aqui quando puder.
  ```
- Variáveis:
  - `{{1}}` = primeiro nome. Exemplo: `Ana`
  - `{{2}}` = a pergunta que falta, já com ponto final. Exemplo: `are you around Orlando, or visiting?`
- Rodapé: `Reply STOP to opt out.`

> `{{2}}` é preenchido pelo agente com o campo faltante do segmento
> (`segments.required_fields`). Isso mantém um único modelo aprovado servindo
> todos os casos de qualificação incompleta, em vez de um modelo por pergunta.

### 4.3 `reengage_date_pending_v1` — parou na data

**Categoria:** MARKETING · **Idiomas:** en_US, pt_BR

- Corpo (en_US):
  ```
  Hi {{1}}, no pressure at all — whenever you land on a date for {{2}}, just give me a rough idea and I'll hold a spot for you.
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, sem pressa nenhuma — quando você fechar uma data para {{2}}, me dá uma ideia aproximada que eu seguro um horário pra você.
  ```
- Variáveis:
  - `{{1}}` = primeiro nome. Exemplo: `Beatriz`
  - `{{2}}` = o que foi conversado. Exemplo: `the Academy day`
- Rodapé: `Reply STOP to opt out.`

### 4.4 `appointment_confirmation_v1` — confirmação de agendamento

**Categoria:** UTILITY · **Idiomas:** en_US, pt_BR, es_ES

- Corpo (en_US):
  ```
  Hi {{1}}, your visit to URace Karting is confirmed for {{2}} at {{3}}. If anything changes, reply here and we'll move it.
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, sua visita à URace Karting está confirmada para {{2}}, às {{3}}. Se mudar alguma coisa, é só responder aqui que a gente remarca.
  ```
- Variáveis:
  - `{{1}}` = primeiro nome. Exemplo: `Rafael`
  - `{{2}}` = data. Exemplo: `Tuesday, March 4`
  - `{{3}}` = horário com fuso. Exemplo: `10:00 AM ET`

Este é o modelo disparado logo depois de `create_calendar_event` /
`create_kommo_task`. Como é `UTILITY` e a janela geralmente está aberta nesse
momento, o envio costuma ser gratuito.

### 4.5 `appointment_reminder_v1` — lembrete véspera

**Categoria:** UTILITY · **Idiomas:** en_US, pt_BR, es_ES

- Corpo (en_US):
  ```
  Hi {{1}}, just a reminder about your session at URace Karting tomorrow, {{2}} at {{3}}. Come in closed shoes and comfortable clothes. See you there.
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, lembrete da sua sessão na URace Karting amanhã, {{2}}, às {{3}}. Venha de sapato fechado e roupa confortável. Até lá.
  ```
- Variáveis: `{{1}}` nome (`Rafael`) · `{{2}}` data (`Tuesday, March 4`) ·
  `{{3}}` horário (`10:00 AM ET`)
- Botões: resposta rápida `I'll be there` · resposta rápida `Need to reschedule`

### 4.6 `owner_callback_v1` — retorno do dono (handoff)

**Categoria:** UTILITY · **Idiomas:** en_US, pt_BR

- Corpo (en_US):
  ```
  Hi {{1}}, Italo from URace is going to call you about your racing program. Does {{2}} still work on this number?
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, o Italo, da URace, vai te ligar sobre o seu programa de corrida. O horário de {{2}} ainda funciona nesse número?
  ```
- Variáveis: `{{1}}` nome (`Lucas`) · `{{2}}` janela combinada (`this afternoon`)

Use somente quando o retorno foi realmente combinado com o lead — é o que
sustenta a categoria `UTILITY`. Este é o modelo do caminho
`agent_action = handoff_to_owner`.

### 4.7 `corporate_quote_followup_v1` — orçamento corporativo

**Categoria:** UTILITY · **Idiomas:** en_US, pt_BR

- Corpo (en_US):
  ```
  Hi {{1}}, following up on the URace quote for your {{2}} event. Any questions on it, or would you like us to adjust the number of participants?
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, retomando o orçamento da URace para o evento de {{2}}. Ficou alguma dúvida, ou quer que a gente ajuste o número de participantes?
  ```
- Variáveis: `{{1}}` nome (`Patricia`) · `{{2}}` empresa ou tipo (`team building`)

Se a Meta reclassificar para `MARKETING`, o modelo continua funcionando — muda
apenas o custo e a contagem no limite de marketing.

### 4.8 `last_touch_close_v1` — encerramento com dignidade

**Categoria:** MARKETING · **Idiomas:** en_US, pt_BR

- Corpo (en_US):
  ```
  Hi {{1}}, I won't keep messaging you. If you ever want to do anything karting in Orlando, or just have a question, reach out any time — we'll be here.
  ```
- Corpo (pt_BR):
  ```
  Oi {{1}}, não vou mais te mandar mensagem. Se um dia quiser fazer qualquer coisa de kart em Orlando, ou só tirar uma dúvida, é só chamar — a gente vai estar por aqui.
  ```
- Variáveis: `{{1}}` nome. Exemplo: `Camila`
- Rodapé: `Reply STOP to opt out.`

É a última tentativa descrita em `prompts/modes/followup.md`. Depois dele o lead
é fechado com `close_lead(reason='no_response')` e nada mais é enviado.

---

## 5. Como submeter pelo Kommo

1. Entre no Kommo com um usuário administrador.
2. Menu lateral → **Configurações** → **Ferramentas de comunicação** →
   aba **Templates**.
3. **Criar template** e escolha o canal **WhatsApp Business** (o número oficial;
   se a conta for WhatsApp Lite via QR code, templates não existem — veja §8).
4. Preencha, nesta ordem: **nome** do modelo, **categoria**, **idioma**.
5. Cole o corpo. Onde este documento indica `{{1}}`, use o seletor de campo do
   Kommo para inserir o dado (nome do contato, por exemplo) — o Kommo converte
   para a numeração que a Meta exige. Se digitar `{{1}}` à mão, confira depois
   que o campo ficou mapeado.
6. Preencha o **exemplo** de cada variável. Este passo é obrigatório e é a causa
   mais comum de reprovação silenciosa.
7. Adicione rodapé e botões quando o modelo pedir.
8. **Salvar / Enviar para aprovação.** O status vai para `Pending`.
9. Acompanhe o status na mesma tela: `Approved` libera o uso imediato,
   `Rejected` traz o motivo.

Se for reprovado: ajuste o texto conforme o motivo e submeta de novo. Reprovação
não penaliza a conta. O que penaliza é usuário marcando as mensagens como spam —
isso derruba a nota de qualidade do número e, no limite, pausa os modelos.

---

## 6. Como usar no dia a dia

- Na conversa dentro do Kommo, quando a janela estiver fechada, o campo de
  mensagem oferece os modelos aprovados em vez do texto livre.
- Escolha o modelo, confira o preenchimento das variáveis e envie.
- **Assim que o lead responder, a janela reabre** e você (ou o agente) volta a
  escrever normalmente por mais 24 horas. É por isso que quase todo modelo de
  reengajamento aqui termina com um convite explícito à resposta ou com botões.
- Modelo de `MARKETING` só para quem deu opt-in. Todo lead que iniciou a
  conversa por WhatsApp já deu; lista importada de outra origem, não.

---

## 7. O que isto muda no agente

Com os modelos aprovados, a regra em `prompts/modes/followup.md` deixa de ser um
bloqueio absoluto e vira uma bifurcação:

| Janela | O que o agente faz |
|---|---|
| Aberta (< 24h) | Escreve o follow-up livre, como hoje |
| Fechada (> 24h) | Escolhe o modelo aprovado que corresponde à situação e envia com as variáveis preenchidas |

O mapeamento situação → modelo é o mesmo do "Shape by situation" daquele arquivo:

| Situação no follow-up | Modelo |
|---|---|
| Qualificação incompleta | `reengage_missing_info_v1` |
| Parou numa data, interesse claro | `reengage_date_pending_v1` |
| Frio / reabertura genérica | `reengage_inquiry_v1` |
| Já corre → dono | `owner_callback_v1` |
| Evento corporativo com orçamento enviado | `corporate_quote_followup_v1` |
| Última tentativa | `last_touch_close_v1` |

Os nomes dos modelos são dados de configuração, não texto de prompt: vivem em
`configurations`, categoria `message_templates` (seção 19 da arquitetura), junto
das versões por idioma. Trocar um texto aprovado não deve exigir mudança de
código.

---

## 8. Caminho de WhatsApp da conta — verificado

O Kommo oferece dois caminhos de WhatsApp, e só um deles tem modelos.

**A conta da URace está no caminho certo.** Uma auditoria das configurações do
Kommo confirmou que o número está no **WhatsApp Business oficial (WABA / Cloud
API)** provido pela própria Kommo, com status `Connected` e nota de qualidade
`High`. Nada deste documento depende de migração: os modelos podem ser
submetidos hoje.

Para referência futura, o outro caminho é o **WhatsApp Lite**, que pareia um
celular por QR code. Ele não passa pela API oficial, não tem modelos, não tem
aprovação da Meta e não tem garantia de entrega. Se um dia os modelos sumirem
das configurações, é sinal de que o número voltou para esse caminho.

### 8.1 Isto não vale para Instagram e Messenger

Modelos são um mecanismo **exclusivo do WhatsApp**. O Instagram tem a sua
própria janela de 24 horas e **não tem equivalente a modelo aprovado**: passado
esse prazo, uma DM só pode ser respondida se o lead escrever de novo. O
Messenger tem a mesma restrição.

Isso importa porque a auditoria encontrou os canais de Instagram (DM e
comentários) e Facebook Messenger com **erro de conexão** no Kommo desde o fim de
agosto — mensagens desses canais deixaram de chegar ao CRM. Esse é um problema
separado, de reautorização de token da Meta, e nenhum modelo de WhatsApp o
resolve. Os leads perdidos nesses canais só voltam a ser alcançáveis se
escreverem de novo, ou por outro canal em que você já tenha o contato — e aí,
sim, o WhatsApp com os modelos abaixo é a via.

---

## 9. Checklist de implantação

- [x] Confirmar que o número está no WhatsApp Business API oficial (não Lite) — confirmado: WABA/Cloud API via Kommo, `Connected`, qualidade `High`
- [ ] Concluir a *Business Verification* no Gerenciador de Negócios da Meta
- [ ] Submeter os 8 modelos em `en_US`
- [ ] Submeter `pt_BR` para os modelos que atendem público brasileiro
- [ ] Registrar os nomes aprovados em `configurations` / `message_templates`
- [ ] Testar cada modelo com um número interno, fora da janela de 24h
- [ ] Ligar a bifurcação de janela no modo de follow-up do agente
