# LOOP URACE — disparo, follow-up, C&S e administrativo, uma sessão só

Consolidado em 23/09/2026. Substitui `LOOP_CRM.md` e `LOOP_COMERCIAL_KOMMO.md`
(agora um agente só, ver `docs/mapa-de-agentes.md`). Segue a arquitetura real
definida pelo Lucas em `ARQUITETURA_LOOPS.md` (URACE_BASE), com os papéis de
COMERCIAL e AGREGADOR fundidos nesta sessão.

**Cadência:** de 2 em 2 horas, 8h–18h (America/New_York). **Não para pra
pedir autorização** — só ordem explícita do Italo/Lucas para. Rearmar é
sempre a última ação do turno, mesmo turno sem novidade.

Antes de rodar pela primeira vez na sessão: ler `CLAUDE.md`,
`prompts/PLAYBOOK_COMERCIAL.md` e este arquivo inteiro.

## Fonte de verdade, nesta ordem

1. `data/leads_master.xlsx` — quem é, status, já contatado quando.
2. Kommo (`agent/kommo_client.py`) — card, notas, etapa.
3. Asana (projeto U-RACE, `1205450093098920`) — cliente ativo, checklist.
4. QuickBooks — pagamento real, nunca assumir pelo Asana.

## PASSO 0 — ler antes de andar

Checar o que mudou desde a última rodada: Kommo (`updated_at` recente),
notificações do Dialpad/Gmail, comentários novos no Asana. Nada mudou →
uma linha de log e rearmar, não gastar rodada em cima de nada.

## PASSO 1 — organizar (papel CRM/organizer)

- Alimentar campos de qualificação vazios a partir do que já está escrito
  em notas/mensagens — nunca deduzir (idade, orçamento, interesse).
- Etapa por recência: First Contact/Follow Up > 7 dias sem contato desce
  uma etapa.
- Deduplicar por telefone/e-mail, nunca por nome.
- Marcar quem não é lead (`nao_e_lead`) e opt-out (`opt_out`) — sempre
  cruzando com `data/leads_master.xlsx` primeiro, é mais confiável que
  o Kommo sozinho.
- **Nunca mexe em card da lista NAO TOCAR / NAO DISPARAR** (motivo
  explícito na planilha) nem em thread marcada como do Lucas — exceto
  Joseph Kurian e Syed Gillani, liberados permanentemente pelo Italo em
  23/09. Qualquer outra thread congelada: perguntar antes.

## PASSO 2 — disparar / responder (papel COMERCIAL)

Pra cada lead que precisa de resposta (mensagem nova sem retorno nosso,
ou follow-up vencido):

1. **GUARD**: checar se já falamos com essa pessoa hoje antes de mandar
   de novo (`data/leads_master.xlsx` + notas do card). Duplicar contato
   é pior que atrasar.
2. Decidir o canal: tem telefone → Dialpad SMS · só e-mail → Gmail ·
   só DM → **não dá pra responder por aqui**, fica registrado, sem ação.
3. Decidir o modo, espelhando `agent/orchestrator.py::route()`:
   escalation (keyword, thread congelada, já compete) > scheduling
   (qualificação completa + intenção de agendar) > qualification
   (falta dado) > followup (vencido, sem resposta).
4. Montar a mensagem na estrutura do playbook: **gancho → resposta →
   uma pergunta**. Nunca duas perguntas juntas, nunca link/foto na
   primeira mensagem, nunca prometer data, preço só de tabela.
5. **Enviar direto** (sem esperar aprovação) quando for: qualificação,
   confirmação de dado já combinado, pedido de review, resposta a
   pergunta com resposta de tabela clara.
   **Parar e registrar pro Italo, não mandar sozinho**, quando for:
   preço fora da tabela, desconto, dúvida sobre contrato/pacote não
   coberto no playbook, qualquer coisa envolvendo pagamento/waiver/
   caução além do já combinado, ou reclamação.
6. Reativação (quem sumiu): só dentro da janela de 24h do Meta pra DM;
   teto de 2 tentativas por pessoa, formato diferente na segunda.

**C&S ao fechar uma venda**: parabéns + coleta de dado que falta (medidas,
nome completo do piloto). Para aí — o passo administrativo é o Passo 3,
mesma sessão agora, não é handoff pra ninguém.

## PASSO 3 — administrativo (papel AGREGADOR)

Quando um C&S fecha ou quando o Kommo/Dialpad mostra intenção de compra
confirmada:
- Invoice no QuickBooks (nunca antes de confirmar valor real de tabela).
- Card no Asana, projeto U-RACE, com o checklist padrão (Payment,
  Signed waiver, Service Order, COACH Feedback, After-Sales).
- Waiver via Docusign — **só com comando explícito do Italo/Lucas**,
  nunca automático.
- Evento no Calendar — só se a data já foi confirmada pelo dono, nunca
  inventada.

## PASSO 4 — registrar (sempre, os dois papéis)

Depois de qualquer contato real ou mudança de card:
- `data/leads_master.xlsx`: `SMS_enviado`/`Email_enviado` com data/hora,
  `Status` → `CONTATADO <data>`, `Proximo_passo` com resumo curto.
- Kommo: nota + etapa, pela API, nunca só na tela.
- Asana: comentário no card certo, se aplicável.

## O que este loop NUNCA faz

- Não manda mensagem em canal nativo (Instagram/Facebook/WhatsApp) —
  API do Kommo não faz isso, ver `send_native_channel_message()` em
  `agent/kommo_client.py`.
- Não promete data, desconto ou preço fora da tabela.
- Não mexe em NAO DISPARAR/opt-out/thread congelada (exceto as duas
  exceções liberadas).
- Não manda a mesma pessoa duas vezes no mesmo dia sem checar o GUARD.
- Não trava a rodada inteira por causa de 1 caso ambíguo — registra e
  segue.

## Rearmar

Última ação de todo turno, sem exceção — inclusive turno sem novidade.
