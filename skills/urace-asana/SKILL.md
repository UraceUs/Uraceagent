---
name: urace-asana
description: Operação da URACE no Asana — projetos U-RACE (corridas e serviços), SUITS (macacões), Shipping Orders (compras e envios) e ADM URACE (somente leitura). Use para ler, classificar, atualizar e manter esses quadros, aplicar o modelo de tarefa de serviço, respeitar prazos de corrida e sincronizar status com quadro. Contém IDs reais, regras de negócio e o que nunca fazer.
---

# Asana da URACE

Workspace ` COMMAND CENTER` `1205450084498489`. Tudo abaixo foi lido da
fonte, não presumido. Antes de agir em estrutura nova, **re-sondar**.

## Projetos e permissão

| Projeto | GID | Acesso |
|---|---|---|
| U-RACE | `1205450093098920` | ler e escrever |
| SUITS | `1205661933760052` | ler e escrever |
| Shipping Orders | `1215968721507536` | ler e escrever |
| ADM URACE | `1205530439507169` | **SOMENTE LEITURA — não criar, não alterar** |

## U-RACE — colunas

`RACES` `1205450093098932` · `Finished Services` `1208640396741022` ·
`TUESDAY` `1209248561126025` · `WEDNESDAY` `1205141832260875` ·
`THURSDAY` `1205141832260876` · `FRIDAY` `1205141832260877` ·
`SATURDAY` `1205141832260878` · `SUNDAY` `1205141832260879` ·
`🗓️ Pending Reschedule` `1210426520994573` ·
`Luis tasks` `1205141832260887` · `Matt tasks` `1207668579521894`.

- **`Matt tasks`: nenhuma automação. Nunca tocar.**
- `Luis tasks`: deixar como está por ora.
- **Serviço concluído sai da coluna do dia** → `Finished Services`, mesmo
  com subtarefas pendentes. Na coluna do dia fica só o agendado e o do dia.

## Campo `Race` (`1213088541600529`) — obrigatório

`Practice OKC` `1215501111942172` (Orlando, o padrão) · `Practice Bushnell`
`1216267652449325` · `KART` `1213088541600530` · `F4` `1213088541600531` ·
`TRACK CLOSED` `1216760479094481`. É por ele que se separa prática de corrida e kart
de F4. **Sempre preencher.**

## RACES — corridas

- **Nada avança sem o Italo confirmar.** Confirmação é pré-requisito.
- Acompanhar o site de cada corrida (link na descrição).
- Cronograma padrão ao lançar corrida NOVA: `start_on` = **2 dias antes
  do primeiro dia do evento** (chegada da equipe), depois treino URACE,
  treino oficial, classificação, corrida.
- **As corridas já lançadas estão com as datas corretas — não mexer.**
- Template: 25 subtarefas (as antigas têm 19 — aceitar as duas gerações).
- **Corrida nova é `asana_criar_corrida`** (liberado em 17/09): nasce do modelo "New Race"
  na coluna RACES, com as subtarefas; `vence_em` = dia da corrida; cidade/pista viram
  `[cidade / pista]` no nome. Nunca `asana_criar_tarefa` para corrida.
- Regra escrita no projeto: confirmar ≥15 dias antes; organizado 1 mês antes.

## Serviços — o modelo é obrigatório

**Modelo de tarefa do Asana:** `Session Setup | Customer Name_Product
[Category_ Engine and Days]`, gid `1208702559561159`. Instanciar por
`create_task_from_template` (é assíncrono — conferir por leitura direta que
nasceram **12 subtarefas** antes de seguir), depois renomear, preencher a
descrição, `due_on`, `Race`, responsável, e mover para a coluna do dia.

Nome: `{Piloto}_{Serviço}_{Categoria} [n/total]`. Descrição:

```
Service Dates for this Month:
Driver's name / Date of Birth / Age / Height / Weight / Waist
Karting Experience
----------------------------------------
Responsible Name / Email / Phone
----------------------------------------
Invoice link:        Price:
Security deposit:    Price:
```

Referência boa: *Jayden Lago_Professional Coaching_4T [1/1]*.
Tarefa fora do modelo é tarefa que a automação não lê.

**Piloto ≠ serviço (dono, 16/09, reforçado em 22/09).** No título, o que vem antes do
primeiro separador é a **pessoa**; o resto é serviço. Nunca use o título inteiro como
nome de gente: "Elliott Hubbard_Summer Camp 2026 1/4" é o piloto **Elliott Hubbard** no
serviço **Summer Camp 2026**, sessão 1 de 4.

O quadro escreve o cliente de seis formas. Reconheça as seis:

| No título | Cliente | O que separa |
|---|---|---|
| `Aaron Benoit_Trackside Support` | Aaron Benoit | `_` |
| `Harley Keeble - Rotax [3/3]` | Harley Keeble | hífen **com espaço** |
| `Alexander Jacoby \| KA100` | Alexander Jacoby | `\|` |
| `David Pera Using his own Kart` | David Pera | **só o espaço** — corta na palavra de serviço |
| `Jude cook/Harley client - Kart proprio` | Jude cook | `/` entre pessoas (nunca entre números: `3/6`) |
| `Alex Xikis KA100_Professional Coaching` | Alex Xikis | categoria colada no nome, sai fora |

E o nome nem sempre vem completo: `Branson_Practice KA100` é **Branson**,
`Charlie M_Racing Program 3/6` é **Charlie M** (= Charlie Marron), `G.J_Orlando Cup` é
**G.J**. Primeiro nome sozinho e inicial abreviada VALEM — foi o que faltava até 22/09,
quando o dono achou 112 serviços de outras pessoas dentro do card do David Pera.

O hífen colado (`Elliott Hubbard-Summer Camp 2026`) só separa quando o que vem depois é
serviço ou tem número — `Jean-Luc Picard` é um nome só. E `Sr`/`Jr` no fim do nome são
do nome (`Thiago Belluci Sr`), não categoria de kart.

**Nome de serviço nunca é cliente.** "Lead and Follow", "Urace Daily", "Trackside
Support", "Professional Coaching", "Orlando Cup", "Date of Birth" — nada disso é gente.
Na dúvida entre duas pessoas (`Alexander` com um Savage e um Jacoby no quadro),
**pergunte**: não escolha no escuro.

**Instrução dentro da tarefa (16/09).** Quando o comando vier como `INSTRUÇÃO DO DONO
dentro da tarefa do Asana "…" (gid N)`, você age **nessa tarefa e só nela**: comentário,
subtarefa, anexo, data, coluna — sempre com o gid dado. Não crie outra tarefa por esse
caminho; se a instrução pedir algo fora da tarefa, proponha e diga que está fora dela.

### As 12 subtarefas (prioridade do dono: 1–4 e 7 primeiro)

1. **Price + Payment Links** — preencher e deixar na descrição.
2. **Security Deposit sent?** — **a IA envia esta invoice** (exceção
   autorizada; valor fixo). Gatilho: invoice do serviço paga. Limite:
   **4 dias antes do serviço, paga ou não** — e **no mesmo dia** se o
   serviço foi agendado com menos de 4 dias. **Conferir no QuickBooks
   antes** (pode já ter sido cobrado e não anotado na tarefa).
   Processo: `brain/10_PROCESSOS/servico-pagamento-e-deposito.md`.
3. **Signed waiver** — menor → waiver do responsável; maior → *adult*.
   Via DocuSign. **Decidir pela idade** — sem idade na descrição, não
   decidir: escalar.
   **A assinada sempre chega em `support@urace.us`.** Voltou → baixar,
   **anexar o PDF na tarefa** e marcar.
   **Vale por temporada:** antes de pedir, procurar nos anexos de tarefas
   anteriores do piloto E na caixa `support@`.
4. **Payment completed** — pago no QuickBooks → marcar. **A 2 dias do
   serviço tem que estar tudo pronto: invoice do serviço paga, depósito
   pago e waiver assinada.** Faltando qualquer um → **alertar o humano**.
5. **Driver pass / registration** — manual, **não priorizar agora**.
6. **Service Order** — peças usadas pelo cliente (vem do mecânico) →
   invoice ao cliente, abatida do depósito.
7. **Return Security Deposit** — 5 dias após a sessão, depósito menos as
   peças, pelo *merchant view* do QuickBooks.
8–12. Feedback do coach, checklists, formulários — depois.

### Regras de pacote, criação e waiver (28/08)

- **Uma invoice e uma waiver por pacote.** `[1/3] [2/3] [3/3]` = 1
  invoice, 1 waiver. A numeração `[n/total]` é **por invoice / por mês**.
- **Depósito: um por CLIENTE, enquanto estiver retido.** Antes de cobrar,
  verificar no QuickBooks se foi **devolvido**: devolvido ou inexistente →
  cobra; ainda retido → **não cobra**; indeterminado → **escala**.
- **A IA cria a tarefa quando vê o pagamento da invoice do serviço no
  QuickBooks** — o mesmo evento cria a(s) tarefa(s) e dispara o depósito.
  O que faltar de informação, **perguntar**, não deduzir.
- **Waiver vale por temporada.** Conferir se o piloto já tem uma válida
  antes de pedir outra.
- **Remarcação ou cancelamento: sempre escalar.** A IA move a tarefa e
  avisa; devolução e crédito são decisão humana. Não mexer em dinheiro.

### Marcadores que não são serviço

`TRACK CLOSED` / `OKC CLOSED` e qualquer **folga** = **dia sem treino**;
nenhum serviço pode ser agendado nesse dia. `OKC Morning Practice` está
em desuso. `Kart Pick Up` = cliente buscando kart no galpão.

## SUITS — pedido de macacão

Processo completo: `brain/10_PROCESSOS/suits-pedido-de-macacao.md`.
Modelo de tarefa: gid `1217959088745716` (nome `New Order: {cliente}`).
Campo de número do pedido = **`Pedido`** (texto, `1206689200495431`) —
o enum `Order number` é legado quebrado, não usar.

O macacão é **100% personalizado**; sem as 29 medidas e o design
definido, o pedido não segue.

| Status | Quem move |
|---|---|
| `Standby` · `Awaiting Measurements` · `Design Pending` | IA |
| `Design Under Client Review` | **humano** |
| `Order sent to Usman` · `In Production` · `In Transit` · `Delivered` | IA |
| `Canceled` | humano |

**Gatilho central:** anexo do design final **+** status `Order sent to
Usman` — as duas condições juntas — disparam o e-mail ao fornecedor
(formato exato no processo). O e-mail leva **o próprio anexo da tarefa**,
não outro arquivo. **1 dia depois** → `In Production`.

O vai-e-vem com o designer segue humano por decisão do dono.

## Shipping Orders — status × quadro

Sincronia nos dois sentidos; empate resolvido pela **última alteração**
(ler o histórico da tarefa). Mapa e IDs em
`docs/adminai/automacao-status-secao.md`. **Sempre link** em `Order
Number` e `Tracking Number` — link que abre, não código solto.

## Nunca

- Deletar tarefa, renomear em massa, mexer em `Matt tasks`.
- Confiar em `search_tasks` para provar mudança (**índice atrasa**) —
  conferir lendo a tarefa/seção direto.
- Confiar em "Updated N of N" como prova.
- Corrigir dado de cliente sem fonte externa. Com fonte: trocar só o
  campo, conferir por leitura direta, comentar na tarefa com a fonte.
- Criar campo personalizado ou tag pela API — **não existe** essa
  ferramenta; é ação do dono na tela.

## Sempre

- Comentário na tarefa com prefixo **`[IA ADM]`** (o conector autentica
  como Italo Silveira — sem o prefixo parece que foi ele quem escreveu).
- Espelhar no Obsidian conforme `urace-obsidian`.
