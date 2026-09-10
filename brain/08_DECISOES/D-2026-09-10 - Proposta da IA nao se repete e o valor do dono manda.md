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
