# Estado das corridas — 28/08/2026 (Parte A, 1ª rodada do espelho)

Fonte: projeto U-RACE, seção RACES, lido ao vivo (read-only). Espelhos
em `brain/20_ENTIDADES/corridas/`. Prazos pela regra escrita no próprio
projeto: confirmado ≥15 dias antes; organizado 1 mês antes.

## 🔴 AÇÃO HUMANA — prazo estourando

| Corrida | Datas | D-30 (organizado) | D-15 (confirmação) | Críticas abertas |
|---|---|---|---|---|
| AMR 2026 Round 8 (Homestead) | 17–20/09 | **estourado há 11 dias** | **02/09 — em 5 dias** | 6/6 (só Confirm Drivers tem dono: Eduardo) |
| FLKC Practice Jacksonville | 25–27/09 | **estourado há 3 dias** | 10/09 — em 13 dias | 6/6 (idem; responsável geral: Luis Barros) |

Nas duas corridas: Pre race invoice, Pit spot, Hotel, Track hours e
Event schedule estão abertas e SEM RESPONSÁVEL. Os itens "1 month
earlier" já passaram do próprio prazo que carregam no nome.

## 🟡 Horizonte (incompletas, fora da janela)

- Florida Karting Championship R9&R10 [Jacksonville NFKC] — 01–04/10 (D-30 em 01/09!)
- SKAPA Winter Series Rd4&5 — 18/10
- AMR 2026 R9 (22–25/10) · R10 (19–22/11) · R11 (17–20/12)
- Florida Karting Championship R11&R12 [AMR] — 03–06/12
- FLKC 2027 (0 Plate, R1–R8) e Star Champions 2027 — longe, com template ok

## 🧾 Inconsistências documentadas (não corrigidas — regra da missão)

1. Tarefas com data FUTURA já marcadas completed: F4 (06/09, 20/09,
   18/10), Lucas Oil (29/09, 03/11), Star Night Fight ("NOT GOING" no
   nome). Padrão provável: "completed" = "não vamos" / planejamento
   encerrado — o espelho não pode tratar completed como "corrida feita".
   Perguntar ao dono qual é a semântica oficial.
2. Duas tasks "Jude Cook" (22 e 23/08, 0 subtarefas, assignee Luis
   Barros) na seção RACES — nome de driver como task de corrida; fora
   do padrão do template.
3. Templates variam: corridas antigas com 19 subtarefas, novas com 25;
   FLKC 2027 já veio com 25. O checker precisa aceitar as duas gerações.

## Como isto foi gerado (observabilidade)

Sondas MCP read-only: get_tasks na seção RACES (paginado) + get_task nas
2 corridas em janela + get_task nas 12 subtarefas críticas. Nenhuma
escrita no Asana. Próxima rodada: re-sondar e fazer diff contra os
espelhos (o que mudou = o que a equipe fez).
