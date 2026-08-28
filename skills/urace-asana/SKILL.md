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

`Practice OKC` (Orlando, o padrão) · `Practice Bushnell` · `KART` ·
`F4` · `TRACK CLOSED`. É por ele que se separa prática de corrida e kart
de F4. **Sempre preencher.**

## RACES — corridas

- **Nada avança sem o Italo confirmar.** Confirmação é pré-requisito.
- Acompanhar o site de cada corrida (link na descrição).
- Cronograma padrão ao lançar corrida NOVA: `start_on` = **2 dias antes
  do primeiro dia do evento** (chegada da equipe), depois treino URACE,
  treino oficial, classificação, corrida.
- **As corridas já lançadas estão com as datas corretas — não mexer.**
- Template: 25 subtarefas (as antigas têm 19 — aceitar as duas gerações).
- Regra escrita no projeto: confirmar ≥15 dias antes; organizado 1 mês antes.

## Serviços — o modelo é obrigatório

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

### As 12 subtarefas (prioridade do dono: 1–4 e 7 primeiro)

1. **Price + Payment Links** — preencher e deixar na descrição.
2. **Security Deposit sent?** — **conferir no QuickBooks antes**; se não
   foi enviado, enviar para os dados do responsável. Valor em
   `brain/00_SYSTEM/PARAMETROS.md` (US$ 400).
3. **Signed waiver** — menor → waiver do responsável; maior → *adult*.
   Via DocuSign. Voltou assinado → marcar **e anexar o PDF**.
   **Decidir pela idade** — sem idade na descrição, não decidir: escalar.
4. **Payment completed** — pago no QuickBooks → marcar.
5. **Driver pass / registration** — manual, **não priorizar agora**.
6. **Service Order** — peças usadas pelo cliente (vem do mecânico) →
   invoice ao cliente, abatida do depósito.
7. **Return Security Deposit** — 5 dias após a sessão, depósito menos as
   peças, pelo *merchant view* do QuickBooks.
8–12. Feedback do coach, checklists, formulários — depois.

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
(formato exato no processo). **1 dia depois** → `In Production`.

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
