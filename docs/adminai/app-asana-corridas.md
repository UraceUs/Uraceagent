# Aplicação 1 — Asana (Corridas)

Primeira aplicação do Administrative AI, por decisão do dono (28/08):
construção **por partes e por aplicação**. Esta é a parte Asana, restrita
ao domínio de corridas. O quadro "ADM URace Workflow" foi descartado como
base; a fonte de verdade operacional é o **projeto U-RACE**.

## Fonte de verdade (descoberto na FASE 2, tudo confirmado por sonda)

- Workspace: ` COMMAND CENTER` (`1205450084498489`)
- Projeto: **U-RACE** (`1205450093098920`), seção **RACES**
  (`1205450093098932`)
- Séries ativas: AMR 2026 (R6–R11) e FLKC 2027
- Custom field: `Race` = KART (`1213088541600529`)
- **Template real de corrida = 25 subtarefas padrão** (exemplo: Round 8,
  gid `1216270696569279`): Confirm Drivers · Pre race invoice · Pit spot
  · Flights · Hotel · Track hours for practice · Event schedule · Buy
  Tires · Specify Mechanic/Engine/Fuel Rule/Chassis · Assign coaches
  (1:4) · Head staff · Send race info to WhatsApp group · Review parts
  lists per driver · After race invoice · Pay race staff · Collect
  post-race feedback · 4 checklists FORMS · Post LineUp Instagram ·
  Create race financial sheet.
- Regra de negócio escrita no projeto: *"Confirmation needed at least 15
  days before the event, preferably fully organized 1 month prior."*
- Pessoas: Eduardo (logística: flights, hotel, mecânicos), Lara
  (planejamento e faturamento: schedule, pneus, pit-spot, invoices
  pré/pós). Divisão documentada pela própria equipe.

## Desenho (arquitetura híbrida da missão)

**Determinístico** (código, sem modelo):
- Poll do projeto U-RACE; dedupe por `gid` do Asana (chave externa — a
  mesma corrida nunca vira duas entidades).
- Espelho da corrida como entidade no Obsidian (ver schema abaixo).
- Cálculo de prazos: D-30 ("preferencialmente organizado") e D-15
  (confirmação obrigatória) a partir do `due_on`.
- Checklist de completude: quais das 25 subtarefas existem/estão feitas.

**Claude** (interpretação):
- Resolver entidades: driver citado numa subtarefa → qual CLIENTE
  (cruzando com QuickBooks/CRM quando essas aplicações entrarem).
- Ler comentários/descrições e extrair fatos (datas, pistas, mudanças).
- Exceções: subtarefa fora do padrão, corrida sem template, conflito
  entre fontes.

**Humano** (escalação, formato PROBLEMA/CONTEXTO/INFORMAÇÕES/O QUE FOI
TENTADO/RECOMENDAÇÃO): conflito de dados, cliente não identificado,
valores anormais, qualquer ação irreversível.

## Entidade CORRIDA (Obsidian — segundo cérebro)

```yaml
# brain/20_ENTIDADES/corridas/<serie>-<round>.md (frontmatter)
tipo: corrida
asana_gid: "1216270696569279"     # chave externa; dedupe
serie: AMR 2026
round: 8
data: 2026-XX-XX                  # due_on da task
pista: ...
status_asana: aberta|concluida
prazo_d30: ok|estourado
prazo_d15: ok|estourado
subtarefas_chave:
  pre_race_invoice: pendente|feita
  after_race_invoice: pendente|feita
  flights: ...
  hotel: ...
drivers: []                       # nomes; vínculo a CLIENTE vem depois
atualizado_em: ...
fonte: asana                      # nunca editar à mão o que é espelho
```

Ligações futuras (outras aplicações, uma por vez): CORRIDA → INVOICE
(QuickBooks), CORRIDA → evento (Urace Race Calendar), CORRIDA → CLIENTE.

## Partes (nesta ordem, cada uma validada antes da próxima)

- **Parte A — Leitor/espelho (SÓ LEITURA no Asana).** Lê o U-RACE, gera/
  atualiza as notas de corrida no Obsidian e um relatório de estado
  (corridas próximas, subtarefas pendentes, prazos D-30/D-15). Nenhuma
  escrita no Asana. É o alicerce da observabilidade ("por que a IA fez
  isso?" = a nota espelha a fonte, com timestamps).
- **Parte B — Alertas de prazo.** Sobre o espelho da Parte A: corrida a
  ≤30/≤15 dias com subtarefa-chave pendente → alerta ao humano (canal a
  definir com o dono; WhatsApp NÃO — regra da missão: não transformar o
  WhatsApp administrativo em canal de bot de vendas nem vice-versa).
- **Parte C — Escrita assistida.** Criar corrida nova já com as 25
  subtarefas do template, sob comando humano explícito. Primeira escrita
  no Asana só aqui, e só depois de A e B validadas pelo dono.

## Invariantes desta aplicação

- A IA NÃO ENVIA A INVOICE (prepara/preenche/revisa; envio é humano) —
  vale desde já, mesmo antes da aplicação QuickBooks.
- Nada de deletar/renomear tarefas do Asana; Parte A e B são read-only.
- IDs externos (gid) são a chave de dedupe; nunca casar por nome.
- Nunca presumir schema: toda estrutura acima veio de sonda real e será
  re-sondada antes de cada parte entrar em produção.

---

## AMPLIAÇÃO DE ESCOPO (28/08) — a Aplicação 1 é o Asana inteiro

O dono definiu os 4 projetos que compõem a aplicação Asana: **U-RACE,
SUITS, Shipping Orders e ADM URACE** (este último SOMENTE LEITURA). O
mapa completo, com seções, campos personalizados, modelos de tarefa e
inconsistências, está em `mapa-asana-4-projetos.md`.

Corridas (este documento) são UMA das entidades do U-RACE. A outra é
SERVIÇO — tarefa com 12 subtarefas que anda pelos quadros dos dias da
semana (TUESDAY…SUNDAY). Pedidos por e-mail entram por último, por
decisão do dono.
