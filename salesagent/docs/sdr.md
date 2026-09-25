# SDR — o Chase reorganizado pelas diretivas de 25/09/2026

O Chase volta como **SDR** do Kommo: separa o que é lead do que não é, organiza
o card no **Novo funil** e, só quando o dono ligar, responde e chama a pessoa
certa. A decisão está em
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
| `organizar` | sim, pelo webhook de conta | sim, no Novo funil | **não**: gente responde | **dono** |
| `atender` | sim, pelo Salesbot | sim, no Novo funil | sim (o Chase completo) | **dono** |

Por que o dono: escrever etapa, tag e resposta no Kommo é ato dele
(D-2026-09-17), e desde D-2026-08-27 os leads são 100% humanos. `observar` não
fere nenhuma das duas: não escreve, não fala. É o nível para conferir as
decisões com leads reais antes de subir.

Conferir o que o SDR decidiu:

```bash
python3 salesagent/tools/show_recent_audit.py --kind sdr -n 30
```

---

## 2. O Novo funil

Um funil próprio. **Os funis da equipe não são tocados**: Urace, Comercial,
Contact list, Emails, Pós Venda, Operacional Vendas e o antigo "Chase — AI Sales
Funnel". Card fora do Novo funil é ignorado pela ponte.

Dentro do Novo funil há duas zonas. As etapas de **triagem** recebem tudo e não
são trabalho de quem vende. As etapas de **venda** só recebem o que é lead, por
regra. "Descer para o comercial" é passar de uma zona para a outra.

| Ordem | Etapa (nome exato no Kommo) | Zona | O que cai |
|---|---|---|---|
| 1 | Triagem | triagem | conversa nova (primeira etapa, **sem Incoming leads**) |
| 2 | Aguardando contexto | triagem | "oi", áudio ou foto sem texto |
| 3 | Lead novo | venda | formulário do site, chamada perdida |
| 4 | Em qualificação (robô) | venda | preço, agenda, contratação, score ≥ 40 |
| 5 | Atendimento humano | venda | toda escalação (ver §4) |
| 6 | Reserva Etapa 1 (Pit ID) | venda | reserva iniciada no site, Pit ID informado |
| 7 | Briefing Etapa 2 | venda | acompanhamento do briefing |
| 8 | Sem sinal comercial | triagem | "obrigado", pergunta solta ("onde fica?") |
| 9 | Automáticos (e-mails e códigos) | triagem | código de login, e-mail de sistema, newsletter, com a tag `nao_e_lead` |
| 10 | Ruído (spam e fornecedores) | triagem | spam, fornecedor, currículo, interno ou grupo, com a tag `nao_e_lead` |
| — | Ganho (142, nativo) | venda | Driver Briefing concluído |
| — | Perdido (143, nativo) | ambas | opt-out (com a tag `opt_out`) ou trilha de follow-up esgotada |

A ponte acha o funil e cada etapa **pelo nome**. Nenhum id fica no repositório.
Quem cria o funil pode ser a extensão, pela tela
([`docs/extensao/PROMPT-SDR-KOMMO.md`](../../docs/extensao/PROMPT-SDR-KOMMO.md)),
ou `tools/sdr_funil.py --aplicar`, pela API. `tools/sdr_funil.py` sem
`--aplicar` confere e não escreve nada. Ele nunca cria etapa em funil que já
existe; o que faltar aparece como pendência.

**Regras de movimento:**
1. Card de triagem com sinal comercial **desce** para venda (`promover_card`):
   é o mesmo card, não nasce outro.
2. Card já em venda e aberto só recebe registro (`anexar_card`) e **nunca volta**
   para a triagem.
3. Card fechado há até 30 dias que volta com sinal é reaberto em "Em
   qualificação (robô)".
4. Escalação leva para "Atendimento humano". A exceção é quem já está em
   Reserva Etapa 1 ou 2, que não volta de etapa.
5. Etapa criada à mão no Novo funil é da equipe: a ponte não mexe.
6. Nota no card **só** quando ele entra em venda ou vai para uma pessoa. O que
   fica na triagem não polui o histórico.
7. Tags **só somam** (`tags_to_add`), nunca apagam as da equipe.

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
teste: código de login do Kommo, DocuSign, RD Station, Zoho e Alibaba.

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
Perdido com a tag `opt_out`.

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
| Novo funil (plano, criação, ids por nome) | `sdr/funil.py` |
| Aplicar no Kommo, com os níveis | `sdr/executor.py` |
| Ligação com a ponte (Kommo real, log, threads) | `bridge/sdr_ponte.py` |
| Webhook de conta (observar/organizar) | `POST /kommo/eventos?key=` em `bridge/app.py` |
| Teste de balcão via HTTP (localhost) | `POST /tools/sdr` com `{"texto": "..."}` |
| Teste de balcão via terminal | `python3 salesagent/tools/sdr_avaliar.py --tabela` |
| Conferir ou criar o Novo funil | `python3 salesagent/tools/sdr_funil.py [--aplicar]` |
| Testes | `python3 salesagent/tests/test_sdr.py` (e `tools/chase_validate.py` roda todos) |

---

## 8. Ainda depende da palavra do dono

- **Subir de nível** (`organizar`, `atender`) e religar o serviço
  `sales-bridge`, desligado desde D-2026-08-27.
- **Horário de atendimento humano.** O valor atual veio do arquivo do Chase
  (quarta a domingo, 9h–18h) e não vale como regra (D-2026-08-31). A pista
  opera de quarta a domingo, 8h–13h.
- **Portfólio que o robô oferece.** O material de venda do Chase está em
  `90_ARQUIVO`. Enquanto não for reescrito com fonte confirmada, o robô não
  afirma preço, idade mínima nem política: manda o link (G1) ou escala.
- **Qual robô responde no Novo funil.** O Salesbot da ponte (162247, "Salesbot #9") e o chat do
  Command Center (`/ops/api/crm/hook`) usam o mesmo circuito, e o Kommo não
  roda dois bots no mesmo lead ao mesmo tempo.
