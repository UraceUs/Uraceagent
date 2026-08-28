# Sincronia automática: campo "Status da ordem" × quadro (seção)

Projeto: **Shipping Orders** (`1215968721507536`). Decisão do dono:
sincronia **nos dois sentidos** — status mudou, a tarefa anda para o
quadro; tarefa arrastada de quadro, o status acompanha.

> **Prioridade:** o dono avisou em 28/08 que Shipping Orders **não é a
> prioridade agora**. O que está aqui fica pronto e parqueado; a regra e o
> mapa valem para quando voltarmos, e o mesmo desenho serve ao SUITS.

## O que "concluída" significa (definido pelo dono)

Concluída = **encerrada**, e é independente do status. Um pedido pode ser
concluído em mais de um caminho:
- `Cancelled` + concluída → foi cancelado e o assunto acabou (ex.: *Starter Solenoid*).
- `Arrived` + concluída → chegou, acabou o ciclo.

Ou seja: **não existe "concluída errada"**; o que existe é status
desatualizado. Se algo está concluído com status de meio de caminho
(`In Production`, `Order Created`), é erro humano de não ter trocado o
campo — e é exatamente isso que a sincronia resolve.

## O mapa (lido da fonte, não presumido)

| Status da ordem | Quadro (seção) |
|---|---|
| Order Created | Order Created |
| Shipped | Shipped |
| Arrived | Arrived |
| Pending/Review | Pending/Needs review *(nomes diferentes, mesmo estado)* |
| Payment pending | **Payment pending** *(criada em 28/08)* |
| Refunded | **Refunded** *(criada em 28/08)* |
| Cancelled | Cancelled |

`Payment pending` e `Refunded` existiam como status e **não existiam como
quadro** — por isso 3 pedidos pareciam "divergentes" sem culpa de
ninguém. Criadas a pedido do dono.

**Quadros que NÃO são status** e que a automação nunca toca, porque ali a
seção quer dizer categoria: `Locations` (cartões de endereço, nem são
pedidos), `Alphaline Suits`, `Cannotops`, `Seção sem título`.

## Como o empate é resolvido: a última alteração vence

Não é escolha de gosto — foi validada em caso real. Na tarefa *"4 Pieces
Hour Meters"*, o histórico mostra:

```
19:32:29  Eduardo marcou esta tarefa como concluída
19:32:53  Eduardo moveu de "Order Created" para "Cancelled"
```

O campo nunca foi tocado depois. A seção era a informação mais nova — e a
correta. Por isso a automação lê o **histórico da tarefa** (stories) para
desempatar, em vez de eleger um lado como sempre-vencedor.

## Duas camadas (uma instantânea, uma de rede de segurança)

### 1. Regras nativas do Asana — instantâneo, sem servidor *(ação do dono)*

É o que faz a mudança ser imediata. Não dá para criar por API (não existe
endpoint), então são cliques na tela — uma vez só:

`Shipping Orders` → **Personalizar** → **Regras** → **Adicionar regra** →
Regra personalizada. Para cada linha do mapa acima, duas regras:
- *Quando*: "Status da ordem" é definido como **X** → *Então*: mover para a seção **X**
- *Quando*: tarefa movida para a seção **X** → *Então*: definir "Status da ordem" como **X**

São 7 estados = 14 regras. Chato de clicar, mas é uma vez e resolve para
sempre, inclusive quando quem mexe é uma pessoa no celular.

### 2. `adminai/asana_status_sync.py` — a rede de segurança *(nosso código)*

Varre o projeto e reconcilia o que escapou (edição em massa, importação,
regra desligada). Roda em simulação por padrão — **nunca escreve sem
`--aplicar`**:

```bash
export ASANA_TOKEN=...                          # ver abaixo
python3 adminai/asana_status_sync.py            # só mostra o que faria
python3 adminai/asana_status_sync.py --aplicar  # aplica e comenta na tarefa
```

Toda alteração que ele faz vira **comentário na própria tarefa** com o
prefixo `[IA ADM]`, dizendo o que mudou e por quê — a regra do diário de
bordo que o dono definiu.

**O que falta para ele rodar sozinho no VPS:** um Personal Access Token
do Asana (o conector desta sessão não serve fora dela). Gerar em
`Asana → foto do perfil → Configurações → Apps → Gerenciar tokens de
acesso pessoal`. Guardar como variável de ambiente no serviço — **nunca
dentro do código**.

## O que já foi reconciliado em 28/08 (4 tarefas)

| Tarefa | Antes | Agora |
|---|---|---|
| 4 Pieces Hour Meters | quadro Cancelled × campo Order Created | campo → **Cancelled** (quadro venceu, comprovado pelo histórico) |
| Parking Elevator - Alibaba | campo Payment pending, sem quadro | movida para **Payment pending** |
| RV Flooring | campo Refunded, quadro Pending/Needs review | movida para **Refunded** |
| Cleanner machines - Vevor | campo Refunded, quadro Pending/Needs review | movida para **Refunded** |

Verificado por leitura de volta na API, não pelo retorno da escrita.

## Limite conhecido

O conector desta sessão **não tem permissão** para alterar configuração de
campos do projeto (deu `Access denied` ao tentar remover o `Order number`
do SUITS). Criar seções funciona; mexer em campo personalizado, não.
Então: criação/remoção de campo é sempre ação do dono na tela.
