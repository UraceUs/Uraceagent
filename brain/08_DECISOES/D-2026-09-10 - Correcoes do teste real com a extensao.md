---
tipo: decisao
data: 2026-09-10
fonte: teste real pela extensão do navegador (contas de produção)
tipo_info: DECISION
responsavel: Italo Silveira
status: ativo
---

# D-2026-09-10 — O que o teste real com a extensão encontrou, e como ficou

O dono mandou a extensão testar o Command Center contra as contas reais
(dez pontos). Oito rodaram. O que ela achou e a correção de cada coisa:

1. **Criar tarefa quebrava:** `asana_criar_do_modelo() got an unexpected
   keyword argument 'projeto_gid'` (e antes `qbo_itens_buscar() … 'texto'`).
   O agente manda campo a mais e a execução inteira caía. Agora o painel
   **descarta o que a ferramenta não aceita** (`acoes.ajustar_aos_parametros`,
   pela assinatura real da função) e registra o descarte na auditoria.
   Vale também para propostas antigas guardadas no banco.
2. **Importação fabricava cliente falso:** "Date of Birth:", "Email:",
   "Karting School", "Professional Coaching", "Lucas oil Laguna Seca".
   Rótulo do modelo, nome de serviço e nome de corrida/pista/série nunca
   viram gente (`identidade.eh_rotulo_ou_servico`), e a limpeza tira os
   que já entraram — as tarefas ficam, só perdem o vínculo errado. Isso
   também derruba a maioria dos "duplicados" que não eram a mesma pessoa.
3. **Coluna "Pending Reschedule" não sincronizava**, escondendo serviço do
   piloto. Agora **toda coluna que não é RACES** é lida com cliente.
4. **Calendário escondia corrida concluída com data futura** (F4 VIR,
   USPKS Lake Erie) e mostrava treino que vazou para a coluna RACES
   ("Pratice at Jacksonville"). Corrigido nos dois sentidos.
5. **Invoice sem número:** a conta usa numeração personalizada e os
   números não são numéricos (`6YZRN1QWN657NQM`), então não dá para
   inferir o próximo. O painel passa a usar um esquema próprio,
   sequencial e legível (`URACE-0001`, ajustável em
   `QBO_PREFIXO_INVOICE`). **Falta o dono dizer se prefere outro.**
6. **Diálogo do navegador travava a extensão.** Os treze `window.confirm`
   e `window.prompt` viraram um modal da própria página
   (`components/Perguntar.tsx`): dá para ler, Enter confirma, Esc cancela.
   O "Puxar histórico" também passou a mostrar o **resumo** na tela.
7. **Aviso "1 ação esperando aprovação" era vago.** Agora diz o que é,
   de quem, quanto e a data do serviço.
8. **Triagem:** "Payment received" ia para contas a pagar (errado, agora
   vai para Finances) e resposta automática de ausência ("unavailable
   Re:") virava e-mail de cliente sem resposta (agora é tratada sozinha).
9. **Nascimento com lixo** ("Age: 13") era gravado como data. Só data ISO
   entra; a limpeza roda a cada sincronia.

**Fica aberto (o dono decide):** o preço da invoice veio da última
invoice do cliente, não da Rate Card, e o produto "Training Program +
Tuner" não existe na Rate Card; o total do dashboard é inflado por uma
invoice antiga de $101.445,37 ("All open invoices 2024-2025"); os pontos
9 (papéis) e 10 (celular) do teste ainda não foram rodados com conta real.

Relacionado: [[D-2026-09-10 - Proposta da IA nao se repete e o valor do dono manda]].
