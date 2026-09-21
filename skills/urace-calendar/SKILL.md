---
name: urace-calendar
description: Espelha as corridas do Asana no Google Calendar da URACE. Use quando uma corrida for lançada, confirmada ou tiver data alterada na coluna RACES do U-RACE, para criar ou atualizar o evento correspondente no Urace Race Calendar.
---

# Corridas do Asana → Urace Race Calendar

Calendário alvo: **Urace Race Calendar**
`c_739bbc...eafe4@group.calendar.google.com` (confirmar o id completo com
`list_calendars` antes de escrever).

## O que espelhar

Tarefa da coluna `RACES` do U-RACE (`1205450093098932`) → evento com:

| Campo do evento | Origem |
|---|---|
| título | nome da corrida (como está no Asana) |
| início / fim | `start_on` / `due_on` da tarefa |
| local | pista/cidade do nome ou da descrição |
| descrição | link da tarefa no Asana + `asana_gid` |

## Dedupe

O `asana_gid` vai na descrição do evento e é a chave. Corrida já
espelhada → **atualizar** o evento, nunca criar outro. Antes de criar,
procurar por `asana_gid` no calendário.

## Regras

- **Só espelha corrida confirmada pelo Italo.** Corrida "com pretensão de
  participar" não vira compromisso no calendário da equipe.
- Data mudou no Asana → atualizar o evento. O Asana é a fonte.
- **Nunca apagar evento** que a IA não criou.
- Corrida marcada como concluída significando "não vamos" (padrão
  observado): não espelhar; se já houver evento, escalar antes de mexer.
