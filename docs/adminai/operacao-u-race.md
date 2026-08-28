# Como o U-RACE opera — regras ditadas pelo dono (28/08/2026)

Projeto **U-RACE** (`1205450093098920`), visão de quadro. Este documento
é a fonte de verdade da operação; valores numéricos ficam em
`parametros-operacionais.md`.

## As colunas e quem manda em cada uma

| Coluna | O que é | Papel da IA |
|---|---|---|
| **RACES** | calendário das corridas que vamos (ou pretendemos) disputar | agir **só depois de confirmação do Italo** |
| **TUESDAY … SUNDAY** | serviços do dia — a tarefa fica na coluna do dia em que o serviço acontece | operação principal |
| **Finished Services** | serviços cuja data já passou e que ainda têm subtarefas pendentes | acompanhar pendências |
| **Matt tasks** | — | **nenhuma automação.** Monitorado por humano, a IA não age |
| **Luis tasks** | — | deixar como está por ora; mexer no futuro |

## RACES — o calendário

- Sempre alimentada com as corridas que vamos ou pretendemos disputar.
- **Nada avança sem o Italo confirmar.** Confirmação é pré-requisito de
  qualquer ação em qualquer corrida da coluna.
- É preciso **acompanhar o site de cada corrida** (o link fica na
  descrição da tarefa) — datas e regulamentos mudam.
- O campo `Race` diz se é **KART** ou **F4**. Sempre conferir.
- Semanas de prática também vivem aqui (ex.: *Practice at Jacksonville
  for FLKC Jacksonville*).

### Como marcar as datas de uma corrida

O cronograma é o mesmo para toda corrida nossa, qualquer que seja o dia
da semana:

```
dia 1   equipe chega (à noite)
dia 2   treino URACE com os pilotos
dia 3   treino oficial
dia 4   classificação
dia 5   corrida
```

Exemplo do dono: evento sexta/sábado/domingo → a equipe chega na quarta,
treino nosso na quinta. Ou seja, a tarefa **começa 2 dias antes do
primeiro dia do evento** — nunca no dia da corrida.

Exceção: evento nosso, em que levamos os pilotos para treinar (a semana
de 25–27/09 em Jacksonville). Aí as datas são as do próprio serviço.

## Serviços (colunas dos dias da semana)

**A tarefa vai para a coluna do dia em que o serviço acontece.** É isso
que dá a visão de quadro da semana.

### O modelo é obrigatório

Toda tarefa de serviço **tem que ser criada pelo modelo**. Não é
preferência estética: o modelo é o que alimenta as automações. Tarefa
fora do modelo é tarefa que a IA não consegue ler direito.

Boa referência: *Jayden Lago_Professional Coaching_4T [1/1]*.

Campos da descrição (preenchidos à mão hoje):

```
Service Dates for this Month:      (os dias daquele cliente naquele mês)
Driver's name / Date of Birth / Age
Height / Weight / Waist
Karting Experience
----------------------------------------
Responsible Name / Email / Phone   (responsável — normalmente o pai)
----------------------------------------
Invoice link:            Price:
Security deposit:        Price:    (ver parametros-operacionais.md)
```

Nome da tarefa: `{Piloto}_{Serviço}_{Categoria} [n/total]` — o `[1/3]`
indica qual dia de um pacote de 3 dias.

### As 12 subtarefas, uma a uma

Prioridade do dono: **fazer as 5 primeiras funcionarem redondas antes de
qualquer outra coisa.**

| # | Subtarefa | O que é, na prática |
|---|---|---|
| 1 | **Price + Payment Links** | preencher preço e links e **deixá-los na descrição** da tarefa |
| 2 | **Security Deposit sent?** | **primeiro conferir no QuickBooks** se já foi enviado para aquele cliente/serviço. Se não foi, enviar para os dados do responsável. Valor fixo (ver parâmetros). Enviou → marca |
| 3 | **Signed waiver** | menor de idade → waiver para o **responsável**; maior → waiver *adult*. Enviado por **DocuSign**. Voltou assinado no e-mail → marcar como assinado **e anexar o PDF na tarefa** |
| 4 | **Payment completed (invoice)** | quando o que foi enviado pelo QuickBooks for pago, marcar aqui |
| 5 | **Send driver pass / registration** | hoje é manual. **Não priorizar agora** — comunicação com cliente vem depois |
| 6 | **Service Order** | vem do mecânico: peças usadas pelo cliente. Se quebrou/usou peça → invoice para o cliente, **abatida do depósito** |
| 7 | **Return Security Deposit** | 5 dias depois da sessão: devolver o depósito **menos** as peças, pelo *merchant view* do QuickBooks |
| 8–12 | feedback do coach, checklists, formulários, convite para a próxima | trabalho posterior |

### Regra de decisão do waiver

Idade é o que decide: com responsável (criança/menor) → waiver do
responsável; maior de idade → waiver *adult*. São dois modelos
diferentes.

## Conectores que ainda faltam

| Conector | Para quê | Status |
|---|---|---|
| **DocuSign** | enviar e receber os waivers automaticamente | **precisa ser conectado** — sem ele a subtarefa 3 continua manual |
| **QuickBooks** | conferir depósito enviado/pago, emitir invoice de peças, devolver depósito | já conectado nesta sessão; falta token próprio para rodar sozinho |

## Ordem de prioridade (dono)

1. Subtarefas 1–4 e 7 (dinheiro: preço, depósito, waiver, pagamento, devolução)
2. Depois: comunicação com o cliente (subtarefa 5)
3. Depois: feedback, checklists e formulários (8–12)
4. `Luis tasks` fica para o futuro; `Matt tasks` nunca entra

---

# Complemento (28/08) — marcadores, sensibilidade e autonomia

## Corridas: as datas do Asana estão certas

Fechado pelo dono: as datas das corridas já lançadas estão corretas como
estão. **Não mexer.** O cronograma padrão documentado acima continua
valendo para lançar corrida NOVA.

## Os marcadores que ocupam as colunas dos dias

Não são serviços. Existem para **indicar** alguma coisa, e viraram
tarefa "porque foi feito nas coxas" (palavras do dono).

| Marcador | O que significa | Efeito prático |
|---|---|---|
| `TRACK CLOSED` / `OKC CLOSED` | a pista está fechada | **não pode haver treino nesse dia** |
| `Folga Track team` / `Folga Anderson` / qualquer *folga* | equipe de folga | **não pode haver treino nesse dia** |
| `OKC Morning Practice` | jeito antigo de dizer "Practice OKC" | **em desuso** — não usar mais |
| `Kart Pick Up` | cliente vem buscar o kart guardado no galpão | evento pontual |
| `Montar o kart do Martin`, `Photos_Baby Kart`, `No practice - Orlando` | marcadores pontuais, provavelmente colocados por engano | não são rotina |

**A regra que a automação precisa extrair disso:** dia com *TRACK CLOSED*
ou com *folga* é **dia sem treino** — nenhum serviço pode ser agendado
ali. Pista fechada e equipe de folga têm o mesmo efeito.

O campo `Race`, por sua vez, é indicação de **onde/o quê**: `Practice
OKC` = treino em Orlando · `Practice Bushnell` = treino no autódromo de
Bushnell · `KART` = corrida de kart · `F4` = corrida de Fórmula 4.

O dono está aberto a transformar esses marcadores em algo **visual**,
desde que **nada do conteúdo das tarefas seja alterado**.

## ⚠️ Dados sensíveis — regra permanente

**As tarefas de serviço contêm dados de clientes** (nome e idade de
criança, telefone, e-mail do responsável, links de pagamento). São dados
sensíveis. Toda operação sobre elas exige cuidado: alterar só o campo em
questão, nunca reescrever a descrição inteira, e sempre registrar no
comentário o que mudou e por quê.

## Autonomia concedida (28/08): corrigir erro rastreado

O dono autorizou: **quando a IA identificar um erro e souber de onde veio
o dado errado, pode corrigir.** Foi o caso do e-mail do Mathias Brouta,
que estava com o e-mail do Shaun Lareau (responsável de outro cliente).

Condições que a IA se impõe para usar essa autonomia:
1. **Ter fonte.** Corrigir só com evidência externa — não com dedução.
2. **Trocar só o campo errado**, byte por byte no resto.
3. **Conferir por leitura direta** depois (a busca do Asana atrasa).
4. **Comentar na tarefa** dizendo o que mudou, para quê e com que fonte.
5. Sem fonte, **não corrigir**: comentar pedindo o dado.

### Caso executado — Tyron Brouta (28/08)

O e-mail correto (`mbrouta@hotmail.fr`) veio de três notificações de
pagamento do QuickBooks, uma delas a invoice `4YZRN1QWN528NQM` de
**$2.369,93** — exatamente o valor da tarefa, paga em 02/06/2026.
Corrigidas as 3 tarefas do pacote, conferidas por leitura direta.

### Achado colateral que muda uma conclusão anterior

O diagnóstico de hoje dizia que 30 dos 31 serviços não tinham registro de
security deposit. O QuickBooks mostra que, para o Tyron, **o depósito de
US$ 400 foi cobrado e pago** (invoice `4YZRN1QWN529NQM`, 03/06/2026) —
só não foi anotado na tarefa.

Ou seja: o problema não é depósito não cobrado, é **depósito não
registrado no Asana**. A verdade está no QuickBooks, e é ele que a
subtarefa "Security Deposit sent?" precisa consultar — exatamente como o
dono já tinha descrito.

## Próximo passo dos conectores

O dono confirmou o rumo: mais à frente a IA terá acesso às **duas caixas
de e-mail** e ao sistema de onde saem os links. **Por ora, o foco é só o
Asana.** O Gmail foi usado hoje apenas como fonte de verificação pontual
para não gravar um dado inventado.
