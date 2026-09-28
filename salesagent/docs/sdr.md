# SDR — o Chase reorganizado pelas diretivas de 25/09/2026

O Chase volta como **SDR** do Kommo: separa o que é lead do que não é, organiza
o card nos funis da equipe (**Urace → Comercial**) e, só quando o dono ligar,
responde e chama a pessoa certa. O desenho dos funis é o do time de vendas
(relatório *URACE — Meta e Kommo*, 25/09/2026). A decisão está em
[`brain/08_DECISOES/D-2026-09-25 - Chase reorganizado como SDR.md`](../../brain/08_DECISOES/D-2026-09-25%20-%20Chase%20reorganizado%20como%20SDR.md).

O princípio do Chase continua o mesmo: **as garantias vivem abaixo do modelo.**
O que decide se é lead, para onde vai o card e quando chamar uma pessoa é
código determinístico (`salesagent/sdr/`), testado offline, antes de qualquer
chamada ao modelo.

---

## 1. Três níveis, um interruptor

`SDR_MODO` em `~/.urace/bridge.env`. O instalador grava `observar` se não houver
nada.

| Nível | Lê as mensagens | Escreve no Kommo (etapa, tag, nota, tarefa) | Responde ao lead | Quem liga |
|---|---|---|---|---|
| `observar` (padrão) | sim, pelo webhook de conta | **não**: só registra no log o que faria | **não** | já vem ligado |
| `organizar` | sim, pelo webhook de conta | sim, em Urace/Comercial (§2) | **não**: gente responde | **dono** |
| `atender` | sim, pelo Salesbot | sim, em Urace/Comercial (§2) | sim (o Chase completo) | **dono** |

O **agendador** da ponte (follow-up, resgate da resposta devida, re-alerta
no WhatsApp interno) só liga em `atender`. Em `observar` e `organizar` ele
fica parado: é ele quem falaria sozinho com o lead, inclusive com as
conversas antigas que ficaram no banco de antes da D-2026-08-27.

Por que o dono: escrever etapa, tag e resposta no Kommo é ato dele
(D-2026-09-17), e desde D-2026-08-27 os leads são 100% humanos. `observar` não
fere nenhuma das duas: não escreve, não fala. É o nível para conferir as
decisões com leads reais antes de subir.

Conferir o que o SDR decidiu:

```bash
python3 salesagent/tools/show_recent_audit.py --kind sdr -n 30
```

---

## 2. Urace → Comercial: os funis da equipe

O SDR **não cria funil nem etapa**. Trabalha nas duas páginas que a equipe já
usa, com as regras que ela já pôs no ar:

```
PÁGINA 1 = funil Urace (recebe tudo)
  First Contact  ◄─ todo card novo
    REGRA 1 (equipe): sem Meta_Ads/Website/Ads Forms/nao_e_lead, +5 min → tag DM
    REGRA 2 (equipe): com DM/Meta_Ads/Ads Forms/Website, +10 min → Comercial › ENTRADA
  Cold Leads / Follow Up 1  ◄─ conversa antiga enterrada
PÁGINA 2 = funil Comercial (só lead)
  ENTRADA → QUALIFICADO → ATENDIMENTO → STAND BY → PROPOSTA → FECHAMENTO
  PERDIDO / NÃO QUALIFICADO
```

**Quem move o quê:**

| Onde está o card | O que o SDR faz | O que o SDR não faz |
|---|---|---|
| Urace › First Contact, card criado há menos de 15 min | tags: `opt_out` (fecha como perdido), `Quer atendimento`; escalação vira tarefa | não sobe o card: quem sobe é a REGRA 2 (subir antes pularia a tag DM) |
| Urace › First Contact, card mais antigo (movido para lá, ou que já estava) | com sinal comercial sobe para Comercial › ENTRADA, com a tag DM se não houver tag de origem; o log marca `sem_regra_2` | sem sinal, não mexe |
| Lead criado em First Contact com nome de lixo (webhook `add_lead`) | `nao_e_lead` na hora | nada com lead de nome de gente |
| Urace › Cold Leads, Follow Up 1, ou fechado | mensagem com sinal comercial sobe para Comercial › ENTRADA, com a tag DM se não houver tag de origem | sem sinal, não mexe |
| Urace › Hot Leads, Closing the sale e as demais | nada | é trabalho da equipe |
| Comercial | escalação → ATENDIMENTO + tarefa; opt-out → PERDIDO / NÃO QUALIFICADO; perdido há até 30 dias que volta com sinal reabre em ENTRADA | **nunca** devolve card para etapa anterior: depois de ENTRADA quem move é o vendedor |
| Outro funil (Contact list, Pós Venda…) | contato antigo com sinal comercial: **tarefa + nota** para o responsável, uma vez por dia | não move |
| *Incoming leads* | nada | o Kommo não deixa mover por PATCH |

**Por que a janela de 15 min.** As REGRAS 1 e 2 da equipe só rodam para o
card que **nasce** em First Contact. No teste ponta a ponta de 28/09, um card
antigo movido para First Contact ficou 32 minutos parado, sem tag DM e sem
subir. Por isso o SDR só segura para a REGRA 2 o card criado há menos de
`JANELA_REGRA_2_MINUTOS` (15, a REGRA 2 age em +10). Se a equipe também
agir, dá no mesmo: mesma etapa, mesma tag.

**`nao_e_lead` nunca vem de conversa de chat.** A tag tira o card da REGRA 1
para sempre. O SDR só a põe pelo nome do lead criado (assunto de e-mail de
sistema) ou por mensagem de e-mail (`CANAIS_QUE_MARCAM_NAO_LEAD`). No mesmo
teste, uma DM com cara de código de login teria marcado `nao_e_lead` num card
que um minuto antes perguntou preço. Em Instagram, WhatsApp, Messenger e
site, o log registra `nao_marcou: nao_e_lead` e fica só `sdr:automatico`.

**Mapa das etapas** (`sdr/regras.py`): triagem → First Contact; opt-out →
perdido (143); novo lead e em qualificação → ENTRADA; atendimento humano →
ATENDIMENTO; reserva Etapa 1/2 → QUALIFICADO; reserva confirmada → ganho (142);
perdido → PERDIDO / NÃO QUALIFICADO.

A ponte acha os funis e cada etapa **pelo nome**. Nenhum id fica no
repositório. `tools/sdr_funil.py` confere se tudo que as regras usam existe e
nunca escreve; etapa renomeada no Kommo aparece como pendência.

**Tags:** só somam (`tags_to_add`), nunca apagam as da equipe. As da equipe que
o SDR usa: `DM`, `Meta_Ads`, `Website`, `Ads Forms` (origem), `nao_e_lead`,
`opt_out`, `Quer atendimento`. As `sdr:*` são só do SDR e não entram em nenhuma
condição das regras da equipe.

**Nota** no card só quando ele entra no Comercial, vai para uma pessoa ou é
contato antigo de outro funil.

---

## 3. O que é lead e o que não é (triagem)

**Não é lead, fica na triagem e o robô não responde:**
- código, e-mail de sistema e newsletter: pelo texto ou pelo remetente
  (`no-reply@`, `mfa@`, `@notice.`, `@account.`, `-security.`…). "Unsubscribe"
  no rodapé de newsletter não é opt-out;
- spam, fornecedor e currículo;
- grupo e contato interno.

**É lead, desce para venda:** preço, agenda, contratação, sinal de conversão,
piloto que compete, pedido de pessoa, corporativo ou grupo acima de 4 pilotos,
tema sensível, Pit ID, eventos do site, qualificação completa, ou soma de
sinais fracos ≥ 40.

**Fica na triagem, mas o robô responde (no nível atender):** saudação, mídia
sem texto, agradecimento, pergunta operacional solta.

Os termos, os pesos e os limiares estão em `sdr/regras.py`, que é o único lugar
onde se muda essa política. A regra casa **palavra inteira**: "hi" não casa com
"this", "ok" não casa com "book".

Os casos reais que a equipe tinha marcado à mão como `nao_e_lead` viraram
teste: código de login do Kommo, DocuSign, RD Station, Zoho e Alibaba. Os 7
assuntos do Inbox de e-mail listados no relatório de 25/09 (código de login,
Dialpad, alerta de segurança, token do GitHub, Bank of America,
"new notifications", Alibaba) também.

---

## 4. Quando chamar uma pessoa (roteador, nível atender)

Antes do modelo, nesta ordem:

| Sinal | Motivo | Prioridade |
|---|---|---|
| tema sensível (jurídico, lesão, reembolso, imprensa) | `TEMA_SENSIVEL` | alta |
| pediu uma pessoa | `PEDIDO_HUMANO` | alta |
| irritado, cobrando retorno | `LEAD_INSATISFEITO` | alta |
| "let's do it", "quero fechar", "como pago" | `SINAL_CONVERSAO` | alta |
| compete hoje (SKUSA, Rotax, "currently racing") | `PILOTO_COMPETIDOR` | alta |
| desconto ou condição especial | `NEGOCIACAO` | média |
| empresa, evento, grupo acima de 4 | `CORPORATIVO` | média |

**Uma pessoa no comercial.** Prioridade **alta** chama agora, pelo WhatsApp
interno, como sempre foi. Prioridade **média** vira **tarefa** no Kommo para o
responsável único (`KOMMO_RESPONSAVEL_ID`), com prazo de 15 minutos, sem
interromper. No nível `organizar` toda escalação vira tarefa: 5 minutos para
alta, 15 para média.

O B4 de `gates.py` continua valendo para o que ele já cobria.

**Não é lead, então não responde:** automático, spam, interno e grupo. "Toda
mensagem de lead recebe resposta" continua de pé. A ponte marca a mensagem
como atendida para o resgate do agendador não responder no lugar dela.

**Opt-out:** uma confirmação no idioma do lead, conversa fechada, card em
perdido com a tag `opt_out`.

**Canais com bot da equipe** (`CANAIS_COM_BOT_DA_EQUIPE`): quem responde ao
lead em Urace é o agente de IA do Kommo (*Agente qualificador de leads*),
**sempre ligado** por decisão do dono em 28/09, ao lado dos bots da equipe
(*URACE - Atendimento inicial DM*, *Website bot*). Nesses canais o roteador não deixa a ponte falar
(`BOT_DA_EQUIPE_NO_CANAL`); as escalações da tabela acima continuam, marcadas
`sem_resposta`, e viram tarefa. Tirar um canal da lista é decisão do dono,
junto com desligar o bot da equipe naquele canal.

**Janela de 24 h da Meta:** no WhatsApp, Instagram e Messenger não existe
mensagem livre 24 h depois da última mensagem do lead. Toque de follow-up do
agendador que cairia fora da janela (23 h, com margem) **não sai**: vira tarefa
para uma pessoa (modelo aprovado ou ligação) e a trilha para. A cadência C11
continua a mesma; na prática, o toque de +1 dia em diante vira tarefa.

---

## 5. O que sai para o lead (guarda de estilo, nível atender)

Aplicada à resposta do modelo, depois dele:
- sem emoji;
- sem travessão (vira vírgula);
- frase com termo de `NUNCA_DIZER` é **cortada inteira**: "come by", "all
  inclusive", "reserva confirmada", "garanto sua vaga"… Cada termo custou um
  incidente no Chase.

Se nada sobrar, sai a mensagem de espera (`holding.py`).

---

## 6. Travas corrigidas junto

- **G9 pelo id.** Antes comparava a chave literal `closed_won`, e no funil do
  Chase a chave é `closed___won`: o fechamento passava. Agora recusa tudo que
  resolve para 142 ou 143. Com o SDR em `organizar` ou `atender`, o modelo não
  muda etapa nenhuma: a etapa é da ponte.
- **Tags não apagam mais.** O PATCH em `_embedded.tags` substituía a lista
  inteira do card.
- **Kommo fora do ar não deixa o lead mudo.** Nota e tag da escalação não
  derrubam mais o turno.

---

## 7. Onde está cada coisa

| Peça | Arquivo |
|---|---|
| Parâmetros (termos, pesos, etapas, prioridades, estilo) | `sdr/regras.py` |
| Classificador, triagem, roteador, estilo | `sdr/classificador.py` · `triagem.py` · `roteador.py` · `estilo.py` |
| Urace e Comercial (conferência, ids por nome, ordem das etapas) | `sdr/funil.py` |
| Aplicar no Kommo, com os níveis | `sdr/executor.py` |
| Ligação com a ponte (Kommo real, log, threads) | `bridge/sdr_ponte.py` |
| Webhook de conta (mensagem recebida e lead criado; observar/organizar) | `POST /kommo/eventos?key=` em `bridge/app.py` |
| Teste de balcão via HTTP (localhost) | `POST /tools/sdr` com `{"texto": "..."}` |
| Teste de balcão via terminal | `python3 salesagent/tools/sdr_avaliar.py --tabela` |
| Conferir Urace e Comercial (só leitura) | `python3 salesagent/tools/sdr_funil.py` |
| Testes | `python3 salesagent/tests/test_sdr.py` (e `tools/chase_validate.py` roda todos) |

---

## 8. Ainda depende da palavra do dono

- **Subir de nível** (`organizar`, `atender`) e religar o serviço
  `sales-bridge`, desligado desde D-2026-08-27.
- **Horário de atendimento humano.** O valor atual veio do arquivo do Chase
  (quarta a domingo, 9h–18h) e não vale como regra (D-2026-08-31). A pista
  opera de quarta a domingo, 8h–13h. O relatório de 25/09 achou três arquivos
  com QUI–DOM 8h–15h e uma mensagem a cliente dizendo 5pm.
- ~~Responsável único~~: decidido em 28/09, URace Support
  (`KOMMO_RESPONSAVEL_ID=12209643`). O Lucas não é usuário do Kommo.
- **Portfólio que o robô oferece.** O material de venda do Chase está em
  `90_ARQUIVO`. Enquanto não for reescrito com fonte confirmada, o robô não
  afirma preço, idade mínima nem política: manda o link (G1) ou escala.
- **Qual robô responde.** Hoje respondem os bots da equipe (Instagram,
  Messenger, WhatsApp, chat do site). O Salesbot da ponte (162247, "Salesbot
  #9") e o chat do Command Center (`/ops/api/crm/hook`) usam o mesmo circuito,
  e o Kommo não roda dois bots no mesmo lead ao mesmo tempo. Ligar o Chase para
  responder num canal é tirar aquele canal de `CANAIS_COM_BOT_DA_EQUIPE` e
  desligar o bot da equipe ali.
- **Pendências do relatório fora do SDR:** agente de IA do Kommo (ligado
  sempre, decisão do dono em 28/09; falta decidir se revela que é IA), o que `NAO_TOCAR` significa, seis bots dividindo o gatilho de
  conversa, gatilhos em "Integração deletada", formulário de anúncio sem
  contato, 33 conversas sem resposta.
