---
tipo: decisao
data: 2026-09-10
fonte: dono (chat, AI Command #11 e #12)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-10 — A proposta da IA não se repete depois de aprovada, e o valor que o dono disse manda

**Dono, 10/09/2026 (David Pera, filho do Nicolas, domingo 13/09):** a IA
escreveu "invoice de $500" mas a prévia veio **$0,00**; depois de ele
aprovar a tarefa no Asana, a mensagem seguinte **repropôs a mesma tarefa**;
e a instrução nova ("o mesmo valor da última invoice") **não mudou a
proposta**. *"Quando eu clicar em aprovar, ele já cria e não precisa ficar
solicitando a aprovação depois que eu já tiver passado outras instruções."*

**Causa:** o agente mandava o JSON com nomes de campo diferentes dos da
ferramenta (`valor`, `itens`, nome do item no lugar do id) e o painel só
lia `unitario`/`item_id`; e o agente não sabia o que já tinha sido
aprovado — a memória da conversa guarda o texto, não as decisões.

**Como ficou (`command_center/api/acoes.py`):**
1. **Argumentos normalizados** antes de gravar a proposta: apelidos de
   campo aceitos, item do QuickBooks resolvido pelo nome no catálogo,
   valor tirado do texto da IA quando ela citou um valor só. O que restar
   errado vira "proposta incompleta" (visível, sem botão de aprovar) e a
   IA ganha **uma** chance de corrigir na mesma conversa.
2. **Assinatura da ação** (tarefa: nome + data; invoice: cliente + data +
   total; waiver: e-mail + modelo). Igual a uma já **aprovada ou feita**
   nos últimos 3 dias → não é proposta de novo (o painel avisa "já
   aprovada em #11"). Igual a uma **pendente** → a antiga é substituída
   pela nova (a instrução mais recente manda).
3. **Estado do dia no comando:** toda mensagem ao agente leva a lista das
   ações de hoje com o status de cada uma e a regra "não reproponha o que
   está aprovado/feito; se mudou algo, proponha só o que muda".
4. O sufixo do comando passou a trazer o esquema exato da invoice e a
   frase "o valor que o dono disse manda sobre qualquer outro".

Relacionado: [[D-2026-09-09 - Aprovar e enviar; mensalidade no dia 1 com previa]], [[D-2026-09-04 - IA age a cada mudanca e aprende pelo balao]].

**Segunda rodada (10/09, 08:58):** a tarefa nasceu do modelo, mas a IA
propôs as *buscas* (cliente e item do QBO) como ações, chamou a busca
com parâmetro errado e mandou a invoice com `<id de …>`. Ficou:
5. **Contexto do painel no comando:** quando a mensagem cita um piloto
   ou responsável conhecido, o comando leva idade, responsável, últimos
   serviços, última invoice com o **id do cliente no QBO**, waiver (vale
   um ano) e o **catálogo de itens do QBO** com ids. A IA age de uma vez.
6. **Consulta não é ação:** buscar/ler/listar nunca vira proposta; o
   painel avisa e descarta.
7. **Painel resolve o que faltar:** cliente pelo espelho (última invoice
   do responsável) ou pelo QBO por e-mail; item pelo catálogo espelhado
   (`qbo_items`, atualizado a cada sincronia); `<placeholder>` conta
   como vazio.
8. Memória da IA: waiver assinada há menos de um ano não se pergunta;
   "mesmo esquema" = repetir o último serviço e o valor da última
   invoice, sem perguntar.

**Terceira rodada (10/09, tarefa vista no Asana):**
9. **Descrição padrão** da tarefa de serviço, montada pelo painel com os
   dados do piloto (datas em mês/dia/ano, nascimento, idade e aviso de
   menor, responsável, e-mail, telefone, produto/categoria, preço).
   Vale para a IA e para o botão "Nova tarefa".
10. **Campo Race = "Practice OKC"** por padrão em tarefa de treino
    ("Practice Bushnell" se a mensagem citar Bushnell; corrida não mexe).
11. **Link da invoice volta para a tarefa:** quando a invoice sai do
    QuickBooks, o painel grava o link e o valor na linha "Invoice link:"
    da descrição da tarefa do mesmo comando (ou do cliente na mesma data).
12. Palavreado: serviço novo é "criar", nunca "recriar".
13. Descrição no formato ditado pelo dono (um campo por linha, `Price:`
    abaixo de `Invoice link:` e de `Security deposit:`). O **security
    deposit** segue o mesmo procedimento: a invoice de depósito grava o
    link e o valor na linha `Security deposit:`.

**Quarta rodada (10/09, 09:07):** *"Ele tem autonomia pra fazer essas
buscas. O que eu preciso aprovar é somente o envio."* e *"quando eu
aprovo, ele não me traz resultado."*
14. **Busca executada na hora pelo painel:** consulta que o agente listar
    é executada (só leitura) e o resultado volta para ele na mesma
    conversa, numa rodada de conclusão. Nunca pede aprovação.
15. **Produto que não existe no QuickBooks é criado pelo painel** com
    nome do produto (Urace Daily, Arrive and Drive…), valor e descrição,
    e entra no catálogo espelhado. `qbo_criar_item` é SAFE.
16. **Aprovar acompanha até o fim:** a tela segue a execução e devolve o
    resultado (✓ "Invoice 1042 de $500,00 criada e enviada para…", com
    link; ✗ "Falhou: …"). Sem clicar duas vezes.
17. Histórico mostra só o que o dono escreveu; o contexto que vai ao
    agente fica em `ai_commands.prompt`.
